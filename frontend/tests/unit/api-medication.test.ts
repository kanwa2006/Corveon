import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { streamMedicationAnalysis } from '@/lib/api/medication';

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

describe('lib/api/medication', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('streamMedicationAnalysis', () => {
    it('parses medication events into onMedication calls, in order', async () => {
      const medOne = {
        id: 'm1',
        raw_text: 'metformin 500mg',
        name: 'Metformin',
        rxcui: '6809',
        dose: '500mg',
        route: null,
        frequency: null,
      };
      const medTwo = { ...medOne, id: 'm2', name: 'Aspirin', rxcui: '1191' };
      const body =
        `event: medication\ndata: ${JSON.stringify(medOne)}\n\n` +
        `event: medication\ndata: ${JSON.stringify(medTwo)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onMedication = vi.fn();
      await streamMedicationAnalysis('c1', 'metformin and aspirin', 'ticket-123', {
        onMedication,
        onInteraction: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onMedication).toHaveBeenNthCalledWith(1, medOne);
      expect(onMedication).toHaveBeenNthCalledWith(2, medTwo);
    });

    it('parses an interaction event into onInteraction', async () => {
      const finding = {
        id: 'f1',
        medication_a_id: 'm1',
        medication_b_id: 'm2',
        severity: 'major',
        source: 'ddinter',
        rule_id: 'rule-1',
        explanation: 'Increased bleeding risk.',
        provenance: { snapshot_id: 's1' },
      };
      const body = `event: interaction\ndata: ${JSON.stringify(finding)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onInteraction = vi.fn();
      await streamMedicationAnalysis('c1', 'warfarin and aspirin', 'ticket-123', {
        onMedication: vi.fn(),
        onInteraction,
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onInteraction).toHaveBeenCalledWith(finding);
    });

    it('parses a done event into onDone', async () => {
      const body = 'event: done\ndata: {"status": "succeeded"}\n\n';
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onDone = vi.fn();
      await streamMedicationAnalysis('c1', 'metformin', 'ticket-123', {
        onMedication: vi.fn(),
        onInteraction: vi.fn(),
        onDone,
        onError: vi.fn(),
      });

      expect(onDone).toHaveBeenCalledOnce();
    });

    it('parses an error event into onError with code and message', async () => {
      const body =
        'event: error\ndata: {"error_code": "provider_unavailable", "message": "No AI provider is currently reachable."}\n\n';
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onError = vi.fn();
      await streamMedicationAnalysis('c1', 'metformin', 'ticket-123', {
        onMedication: vi.fn(),
        onInteraction: vi.fn(),
        onDone: vi.fn(),
        onError,
      });

      expect(onError).toHaveBeenCalledWith(
        'provider_unavailable',
        'No AI provider is currently reachable.',
      );
    });

    it('normalizes \\r\\n line endings (sse-starlette default)', async () => {
      const body = 'event: done\r\ndata: {"status": "succeeded"}\r\n\r\n';
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onDone = vi.fn();
      await streamMedicationAnalysis('c1', 'metformin', 'ticket-123', {
        onMedication: vi.fn(),
        onInteraction: vi.fn(),
        onDone,
        onError: vi.fn(),
      });

      expect(onDone).toHaveBeenCalledOnce();
    });

    it('calls onError when the request itself fails (non-2xx, no body)', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 500 }));

      const onError = vi.fn();
      await streamMedicationAnalysis('c1', 'metformin', 'ticket-123', {
        onMedication: vi.fn(),
        onInteraction: vi.fn(),
        onDone: vi.fn(),
        onError,
      });

      expect(onError).toHaveBeenCalledWith('request_failed', expect.any(String));
    });

    it('includes the ticket and raw_text on the direct backend request', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(''));
      await streamMedicationAnalysis('c1', 'metformin 500mg', 'my-ticket', {
        onMedication: vi.fn(),
        onInteraction: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      const [calledUrl, calledInit] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
      expect(calledUrl).toContain('/chats/c1/medications/analyze');
      expect(calledUrl).toContain('ticket=my-ticket');
      expect(calledInit.body).toBe(JSON.stringify({ raw_text: 'metformin 500mg' }));
    });
  });
});
