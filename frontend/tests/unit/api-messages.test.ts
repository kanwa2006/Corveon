import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api/auth';
import { listMessages, streamMessage } from '@/lib/api/messages';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function sseResponse(rawBody: string, status = 202): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(rawBody));
      controller.close();
    },
  });
  return new Response(stream, { status });
}

const sampleMessage = {
  id: 'm1',
  chat_id: 'c1',
  role: 'user' as const,
  content: 'Hello',
  routing_trace: null,
  created_at: '2026-01-01T00:00:00Z',
};

describe('lib/api/messages', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('listMessages', () => {
    it('fetches the chat message history', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([sampleMessage]));
      const result = await listMessages('c1');
      expect(fetch).toHaveBeenCalledWith('/api/chats/c1/messages');
      expect(result).toEqual([sampleMessage]);
    });

    it('throws ApiError on failure', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(
        jsonResponse({ error_code: 'not_found', message: 'Chat not found.' }, 404),
      );
      await expect(listMessages('missing')).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe('streamMessage', () => {
    it('parses token events into onToken calls, in order', async () => {
      const body =
        'event: token\ndata: Hello\n\n' + 'event: token\ndata:  there\n\n'; // note the single leading space after "data:"
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onToken = vi.fn();
      const onDone = vi.fn();
      const onError = vi.fn();

      await streamMessage('c1', 'hi', 'ticket-123', { onToken, onDone, onError });

      expect(onToken).toHaveBeenNthCalledWith(1, 'Hello');
      expect(onToken).toHaveBeenNthCalledWith(2, ' there');
      expect(onDone).not.toHaveBeenCalled();
      expect(onError).not.toHaveBeenCalled();
    });

    it('parses a done event into onDone with the routing_trace payload', async () => {
      const donePayload = {
        message_id: 'm2',
        routing_trace: { path: 'fast_path', provider: 'stub', retrieved_chunks: [], duration_ms: 5, status: 'ok' },
      };
      const body = `event: done\ndata: ${JSON.stringify(donePayload)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onDone = vi.fn();
      await streamMessage('c1', 'hi', 'ticket-123', { onToken: vi.fn(), onDone, onError: vi.fn() });

      expect(onDone).toHaveBeenCalledWith(donePayload);
    });

    it('parses an error event into onError with code and message', async () => {
      const body =
        'event: error\ndata: {"error_code": "provider_unavailable", "message": "No AI provider is currently reachable."}\n\n';
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onError = vi.fn();
      await streamMessage('c1', 'hi', 'ticket-123', { onToken: vi.fn(), onDone: vi.fn(), onError });

      expect(onError).toHaveBeenCalledWith(
        'provider_unavailable',
        'No AI provider is currently reachable.',
      );
    });

    it('normalizes \\r\\n line endings (sse-starlette default)', async () => {
      const body = 'event: token\r\ndata: Hi\r\n\r\n';
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onToken = vi.fn();
      await streamMessage('c1', 'hi', 'ticket-123', { onToken, onDone: vi.fn(), onError: vi.fn() });

      expect(onToken).toHaveBeenCalledWith('Hi');
    });

    it('calls onError when the request itself fails (non-2xx, no body)', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 500 }));

      const onError = vi.fn();
      await streamMessage('c1', 'hi', 'ticket-123', { onToken: vi.fn(), onDone: vi.fn(), onError });

      expect(onError).toHaveBeenCalledWith('request_failed', expect.any(String));
    });

    it('includes the ticket as a query parameter on the direct backend request', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(''));
      await streamMessage('c1', 'hi', 'my-ticket', {
        onToken: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });
      const calledUrl = vi.mocked(fetch).mock.calls[0]?.[0] as string;
      expect(calledUrl).toContain('/chats/c1/messages');
      expect(calledUrl).toContain('ticket=my-ticket');
    });
  });
});
