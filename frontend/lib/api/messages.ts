/**
 * Messages: list via our own Route Handler (cookie-authenticated, ADR-0012);
 * sending streams token-by-token from a direct fetch against the backend
 * (ADR-0007), authenticated with a short-lived stream ticket (ADR-0016) —
 * native EventSource can't be used here since sending a message is a POST.
 */

import { ApiError } from '@/lib/api/auth';

export type MessageRole = 'user' | 'assistant';

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  document_filename: string;
  ordinal: number;
  similarity: number;
}

export interface RoutingTrace {
  path: 'fast_path' | 'rag_grounded';
  provider: string | null;
  retrieved_chunks: RetrievedChunk[];
  duration_ms: number;
  status: 'ok' | 'provider_unavailable';
}

export interface MessagePublic {
  id: string;
  chat_id: string;
  role: MessageRole;
  content: string;
  routing_trace: RoutingTrace | null;
  created_at: string;
}

export async function listMessages(chatId: string): Promise<MessagePublic[]> {
  const response = await fetch(`/api/chats/${chatId}/messages`);
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    throw new ApiError(
      response.status,
      typeof data.error_code === 'string' ? data.error_code : 'unknown_error',
      'Could not load this conversation.',
    );
  }
  return (await response.json()) as MessagePublic[];
}

const SSE_BASE_URL = process.env.NEXT_PUBLIC_SSE_BASE_URL ?? 'http://localhost:8000';

export interface StreamMessageCallbacks {
  onToken: (delta: string) => void;
  onDone: (payload: { message_id: string; routing_trace: RoutingTrace | null }) => void;
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

export async function streamMessage(
  chatId: string,
  content: string,
  ticket: string,
  callbacks: StreamMessageCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      `${SSE_BASE_URL}/api/v1/chats/${chatId}/messages?ticket=${encodeURIComponent(ticket)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
        signal,
      },
    );
  } catch {
    callbacks.onError('network_error', 'Could not reach the assistant. Please try again.');
    return;
  }

  if (!response.ok || !response.body) {
    callbacks.onError('request_failed', 'Could not reach the assistant. Please try again.');
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
      if (parsed?.event === 'token') {
        callbacks.onToken(parsed.data);
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
