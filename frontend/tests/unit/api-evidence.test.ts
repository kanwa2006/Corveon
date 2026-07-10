import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { streamVerification } from '@/lib/api/evidence';

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

describe('lib/api/evidence', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('streamVerification', () => {
    it('parses claim events into onClaim calls, in order', async () => {
      const claimOne = {
        id: 'c1',
        ordinal: 0,
        text: 'Metformin is first-line therapy.',
        source_class: 'verified_public',
        confidence_score: 82,
        confidence_rationale: 'Base 70 ...',
        flags: [],
        citations: [],
      };
      const claimTwo = { ...claimOne, id: 'c2', ordinal: 1 };
      const body =
        `event: claim\ndata: ${JSON.stringify(claimOne)}\n\n` +
        `event: claim\ndata: ${JSON.stringify(claimTwo)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onClaim = vi.fn();
      await streamVerification('c1', 'm1', 'ticket-123', {
        onClaim,
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onClaim).toHaveBeenNthCalledWith(1, claimOne);
      expect(onClaim).toHaveBeenNthCalledWith(2, claimTwo);
    });

    it('parses a done event into onDone with the verification_id and status', async () => {
      const donePayload = { verification_id: 'v1', status: 'succeeded' };
      const body = `event: done\ndata: ${JSON.stringify(donePayload)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onDone = vi.fn();
      await streamVerification('c1', 'm1', 'ticket-123', {
        onClaim: vi.fn(),
        onDone,
        onError: vi.fn(),
      });

      expect(onDone).toHaveBeenCalledWith(donePayload);
    });

    it('parses an error event into onError with code and message', async () => {
      const body =
        'event: error\ndata: {"error_code": "provider_unavailable", "message": "No AI provider is currently reachable."}\n\n';
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onError = vi.fn();
      await streamVerification('c1', 'm1', 'ticket-123', {
        onClaim: vi.fn(),
        onDone: vi.fn(),
        onError,
      });

      expect(onError).toHaveBeenCalledWith(
        'provider_unavailable',
        'No AI provider is currently reachable.',
      );
    });

    it('normalizes \\r\\n line endings (sse-starlette default)', async () => {
      const claim = {
        id: 'c1',
        ordinal: 0,
        text: 'A claim.',
        source_class: 'ai_reasoning',
        confidence_score: 30,
        confidence_rationale: 'Base 30 ...',
        flags: [],
        citations: [],
      };
      const body = `event: claim\r\ndata: ${JSON.stringify(claim)}\r\n\r\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onClaim = vi.fn();
      await streamVerification('c1', 'm1', 'ticket-123', {
        onClaim,
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onClaim).toHaveBeenCalledWith(claim);
    });

    it('calls onError when the request itself fails (non-2xx, no body)', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 500 }));

      const onError = vi.fn();
      await streamVerification('c1', 'm1', 'ticket-123', {
        onClaim: vi.fn(),
        onDone: vi.fn(),
        onError,
      });

      expect(onError).toHaveBeenCalledWith('request_failed', expect.any(String));
    });

    it('includes the ticket and message_id on the direct backend request', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(''));
      await streamVerification('c1', 'm1', 'my-ticket', {
        onClaim: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      const [calledUrl, calledInit] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
      expect(calledUrl).toContain('/chats/c1/verify');
      expect(calledUrl).toContain('ticket=my-ticket');
      expect(calledInit.body).toBe(JSON.stringify({ message_id: 'm1' }));
    });
  });
});
