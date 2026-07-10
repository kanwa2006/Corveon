/**
 * Evidence Verification: streams claim-by-claim results from a direct fetch
 * against the backend (ADR-0007), authenticated with the same short-lived
 * stream ticket bridge messages.ts uses (ADR-0016) — POST /chats/{id}/verify
 * is a third SSE endpoint sharing that same ticket mechanism.
 */

export type SourceClass =
  | 'uploaded_document'
  | 'verified_public'
  | 'org_trusted'
  | 'ai_reasoning'
  | 'conflicting_insufficient';

export type EvidenceSourceName =
  'pubmed' | 'dailymed' | 'openfda' | 'clinicaltrials' | 'mesh' | 'rxnorm' | 'uploaded_document';

export interface EvidenceFlag {
  type: string;
  detail: string;
}

export interface EvidenceCitation {
  source: EvidenceSourceName;
  title: string;
  url: string | null;
  identifier: string | null;
  published_date: string | null;
  supports_claim: boolean;
}

export interface VerifiedClaim {
  id: string;
  ordinal: number;
  text: string;
  source_class: SourceClass;
  confidence_score: number;
  confidence_rationale: string;
  flags: EvidenceFlag[];
  citations: EvidenceCitation[];
}

export type VerificationStatus = 'pending' | 'running' | 'succeeded' | 'failed';

const SSE_BASE_URL = process.env.NEXT_PUBLIC_SSE_BASE_URL ?? 'http://localhost:8000';

export interface StreamVerificationCallbacks {
  onClaim: (claim: VerifiedClaim) => void;
  onDone: (payload: { verification_id: string; status: VerificationStatus }) => void;
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

export async function streamVerification(
  chatId: string,
  messageId: string,
  ticket: string,
  callbacks: StreamVerificationCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      `${SSE_BASE_URL}/api/v1/chats/${chatId}/verify?ticket=${encodeURIComponent(ticket)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId }),
        signal,
      },
    );
  } catch {
    callbacks.onError(
      'network_error',
      'Could not reach the verification service. Please try again.',
    );
    return;
  }

  if (!response.ok || !response.body) {
    callbacks.onError(
      'request_failed',
      'Could not reach the verification service. Please try again.',
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
      if (parsed?.event === 'claim') {
        callbacks.onClaim(JSON.parse(parsed.data) as VerifiedClaim);
      } else if (parsed?.event === 'done') {
        callbacks.onDone(JSON.parse(parsed.data));
      } else if (parsed?.event === 'error') {
        const errorPayload = JSON.parse(parsed.data) as { error_code: string; message: string };
        callbacks.onError(errorPayload.error_code, errorPayload.message);
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}
