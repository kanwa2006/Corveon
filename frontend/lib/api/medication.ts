/**
 * Medication-Safety Engine (Phase 1: normalization + drug-drug interaction
 * detection; Phase 2: renal/dose checks, ADR-0005; Phase 3: PIP screening
 * — Beers 2023 + STOPP/START v3 — and discrepancy classification,
 * ADR-0019/ADR-0020) — streams claim-by-claim results from a direct fetch
 * against the backend (ADR-0007), authenticated with the same short-lived
 * stream ticket bridge messages.ts/evidence.ts already use (ADR-0016).
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

export type PipSource = 'beers_2023' | 'stopp_v3' | 'start_v3';
export type PipDirection = 'avoid' | 'start_consider';

export interface PipFinding {
  id: string;
  /** Null for a START-criterion finding — it flags a medication missing
   * from the current list, not one present in it (ADR-0019). */
  medication_id: string | null;
  source: PipSource;
  direction: PipDirection;
  severity: FindingSeverity;
  rule_id: string;
  drug_names: string[];
  matched_condition: string | null;
  explanation: string;
  /** Guardrail-checked plain-language rendering of `explanation`
   * (ADR-0020); null when unavailable or it failed the grounding check —
   * `explanation` is always present regardless. */
  narrative: string | null;
}

export type DiscrepancyKind = 'added' | 'omitted' | 'dose_changed' | 'frequency_changed';

export interface DiscrepancyFinding {
  id: string;
  kind: DiscrepancyKind;
  current_medication_id: string | null;
  previous_medication_id: string | null;
  rule_id: string;
  explanation: string;
  narrative: string | null;
  provenance: Record<string, unknown>;
}

/** Every field the analyze endpoint accepts besides `raw_text`, all
 * optional and independently gated (docs/API.md): the four
 * renal-only fields are all-or-nothing together and require `age_years`;
 * `age_years` alone triggers PIP screening; `previous_raw_text` triggers
 * discrepancy classification. */
export interface AnalysisParameters {
  age_years?: number;
  weight_kg?: number;
  sex?: Sex;
  serum_creatinine_mg_dl?: number;
  height_cm?: number;
  conditions?: string[];
  previous_raw_text?: string;
}

const SSE_BASE_URL = process.env.NEXT_PUBLIC_SSE_BASE_URL ?? 'http://localhost:8000';

export interface StreamMedicationAnalysisCallbacks {
  onMedication: (medication: NormalizedMedication) => void;
  onPreviousMedication: (medication: NormalizedMedication) => void;
  onInteraction: (finding: InteractionFinding) => void;
  onRenal: (finding: RenalFinding) => void;
  onPip: (finding: PipFinding) => void;
  onDiscrepancy: (finding: DiscrepancyFinding) => void;
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
  params: AnalysisParameters | null,
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
        body: JSON.stringify({ raw_text: rawText, ...params }),
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
      } else if (parsed?.event === 'previous_medication') {
        callbacks.onPreviousMedication(JSON.parse(parsed.data) as NormalizedMedication);
      } else if (parsed?.event === 'interaction') {
        callbacks.onInteraction(JSON.parse(parsed.data) as InteractionFinding);
      } else if (parsed?.event === 'renal') {
        callbacks.onRenal(JSON.parse(parsed.data) as RenalFinding);
      } else if (parsed?.event === 'pip') {
        callbacks.onPip(JSON.parse(parsed.data) as PipFinding);
      } else if (parsed?.event === 'discrepancy') {
        callbacks.onDiscrepancy(JSON.parse(parsed.data) as DiscrepancyFinding);
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
