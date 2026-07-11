/**
 * Medication-Safety Engine (Phase 1: normalization + drug-drug interaction
 * detection; Phase 2: renal/dose checks, ADR-0005) — streams claim-by-claim
 * results from a direct fetch against the backend (ADR-0007), authenticated
 * with the same short-lived stream ticket bridge messages.ts/evidence.ts
 * already use (ADR-0016).
 */

export interface NormalizedMedication {
  id: string;
  raw_text: string;
  name: string;
  rxcui: string | null;
  dose: string | null;
  route: string | null;
  frequency: string | null;
}

export type FindingSeverity = 'major' | 'moderate' | 'minor' | 'unclassified';
export type InteractionSource = 'ddinter' | 'openfda_label';

export interface InteractionFinding {
  id: string;
  medication_a_id: string;
  medication_b_id: string;
  severity: FindingSeverity;
  source: InteractionSource;
  rule_id: string;
  explanation: string;
  provenance: Record<string, unknown>;
}

export type Sex = 'male' | 'female';

/** All five fields are required together — the backend rejects a partial
 * set rather than silently skipping renal checks (an honest "insufficient
 * data" state, ADR-0005, applies only to omitting all of them). */
export interface RenalParameters {
  age_years: number;
  weight_kg: number;
  sex: Sex;
  serum_creatinine_mg_dl: number;
  height_cm: number;
}

export interface RenalFinding {
  id: string;
  medication_id: string;
  crcl_ml_min: number;
  egfr_ml_min: number;
  threshold_ml_min: number;
  severity: FindingSeverity;
  rule_id: string;
  explanation: string;
}

const SSE_BASE_URL = process.env.NEXT_PUBLIC_SSE_BASE_URL ?? 'http://localhost:8000';

export interface StreamMedicationAnalysisCallbacks {
  onMedication: (medication: NormalizedMedication) => void;
  onInteraction: (finding: InteractionFinding) => void;
  onRenal: (finding: RenalFinding) => void;
  onDone: () => void;
  onError: (errorCode: string, message: string) => void;
}

function parseSseBlock(rawBlock: string): { event: string; data: string } | null {
  let eventType = 'message';
  const dataLines: string[] = [];
  for (const line of rawBlock.split('\n')) {
    if (line.startsWith('event:')) {
      eventType = line.slice('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).replace(/^ /, ''));
    }
  }
  return dataLines.length > 0 ? { event: eventType, data: dataLines.join('\n') } : null;
}

export async function streamMedicationAnalysis(
  chatId: string,
  rawText: string,
  renalParams: RenalParameters | null,
  ticket: string,
  callbacks: StreamMedicationAnalysisCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      `${SSE_BASE_URL}/api/v1/chats/${chatId}/medications/analyze?ticket=${encodeURIComponent(ticket)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_text: rawText, ...renalParams }),
        signal,
      },
    );
  } catch {
    callbacks.onError(
      'network_error',
      'Could not reach the medication-safety service. Please try again.',
    );
    return;
  }

  if (!response.ok || !response.body) {
    callbacks.onError(
      'request_failed',
      'Could not reach the medication-safety service. Please try again.',
    );
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    // Normalize \r\n (sse-starlette's default line ending) before splitting
    // on the blank-line record separator.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const rawBlock = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseSseBlock(rawBlock);
      if (parsed?.event === 'medication') {
        callbacks.onMedication(JSON.parse(parsed.data) as NormalizedMedication);
      } else if (parsed?.event === 'interaction') {
        callbacks.onInteraction(JSON.parse(parsed.data) as InteractionFinding);
      } else if (parsed?.event === 'renal') {
        callbacks.onRenal(JSON.parse(parsed.data) as RenalFinding);
      } else if (parsed?.event === 'done') {
        callbacks.onDone();
      } else if (parsed?.event === 'error') {
        const errorPayload = JSON.parse(parsed.data) as { error_code: string; message: string };
        callbacks.onError(errorPayload.error_code, errorPayload.message);
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}
