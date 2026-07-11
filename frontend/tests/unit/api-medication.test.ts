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
      await streamMedicationAnalysis('c1', 'metformin and aspirin', null, 'ticket-123', {
        onMedication,
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
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
      await streamMedicationAnalysis('c1', 'warfarin and aspirin', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction,
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onInteraction).toHaveBeenCalledWith(finding);
    });

    it('parses a renal event into onRenal', async () => {
      const finding = {
        id: 'r1',
        medication_id: 'm1',
        crcl_ml_min: 12.7,
        egfr_ml_min: 17.9,
        threshold_ml_min: 30.0,
        severity: 'major',
        rule_id: 'renal_threshold:apixaban',
        explanation: 'Both equations are below threshold.',
      };
      const body = `event: renal\ndata: ${JSON.stringify(finding)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onRenal = vi.fn();
      await streamMedicationAnalysis('c1', 'apixaban 5mg', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal,
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onRenal).toHaveBeenCalledWith(finding);
    });

    it('parses a done event into onDone', async () => {
      const body = 'event: done\ndata: {"status": "succeeded"}\n\n';
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onDone = vi.fn();
      await streamMedicationAnalysis('c1', 'metformin', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
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
      await streamMedicationAnalysis('c1', 'metformin', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
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
      await streamMedicationAnalysis('c1', 'metformin', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
        onDone,
        onError: vi.fn(),
      });

      expect(onDone).toHaveBeenCalledOnce();
    });

    it('calls onError when the request itself fails (non-2xx, no body)', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 500 }));

      const onError = vi.fn();
      await streamMedicationAnalysis('c1', 'metformin', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
        onDone: vi.fn(),
        onError,
      });

      expect(onError).toHaveBeenCalledWith('request_failed', expect.any(String));
    });

    it('includes the ticket and raw_text on the direct backend request when renal params are omitted', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(''));
      await streamMedicationAnalysis('c1', 'metformin 500mg', null, 'my-ticket', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      const [calledUrl, calledInit] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
      expect(calledUrl).toContain('/chats/c1/medications/analyze');
      expect(calledUrl).toContain('ticket=my-ticket');
      expect(calledInit.body).toBe(JSON.stringify({ raw_text: 'metformin 500mg' }));
    });

    it('includes renal parameters in the request body when supplied', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(''));
      await streamMedicationAnalysis(
        'c1',
        'apixaban 5mg',
        {
          age_years: 85,
          weight_kg: 50,
          sex: 'male',
          serum_creatinine_mg_dl: 3.0,
          height_cm: 170,
        },
        'my-ticket',
        {
          onMedication: vi.fn(),
          onPreviousMedication: vi.fn(),
          onInteraction: vi.fn(),
          onRenal: vi.fn(),
          onPip: vi.fn(),
          onDiscrepancy: vi.fn(),
          onDone: vi.fn(),
          onError: vi.fn(),
        },
      );

      const [, calledInit] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
      expect(calledInit.body).toBe(
        JSON.stringify({
          raw_text: 'apixaban 5mg',
          age_years: 85,
          weight_kg: 50,
          sex: 'male',
          serum_creatinine_mg_dl: 3.0,
          height_cm: 170,
        }),
      );
    });

    it('parses a previous_medication event into onPreviousMedication', async () => {
      const medication = {
        id: 'p1',
        raw_text: 'metformin 500mg',
        name: 'Metformin',
        rxcui: '6809',
        dose: '500mg',
        route: null,
        frequency: null,
      };
      const body = `event: previous_medication\ndata: ${JSON.stringify(medication)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onPreviousMedication = vi.fn();
      await streamMedicationAnalysis('c1', 'metformin 1000mg', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication,
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onPreviousMedication).toHaveBeenCalledWith(medication);
    });

    it('parses a pip event into onPip', async () => {
      const finding = {
        id: 'pip1',
        medication_id: 'm1',
        source: 'beers_2023',
        direction: 'avoid',
        severity: 'major',
        rule_id: 'beers_2023:CRIT-1',
        drug_names: ['diphenhydramine'],
        matched_condition: null,
        explanation: 'AGS Beers Criteria 2023: avoid diphenhydramine.',
        narrative: null,
      };
      const body = `event: pip\ndata: ${JSON.stringify(finding)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onPip = vi.fn();
      await streamMedicationAnalysis('c1', 'diphenhydramine 25mg', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip,
        onDiscrepancy: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onPip).toHaveBeenCalledWith(finding);
    });

    it('parses a discrepancy event into onDiscrepancy', async () => {
      const finding = {
        id: 'd1',
        kind: 'added',
        current_medication_id: 'm1',
        previous_medication_id: null,
        rule_id: 'discrepancy:added',
        explanation: 'Lisinopril appears in the current list but not the previous one.',
        narrative: null,
        provenance: { name: 'lisinopril', rxcui: null },
      };
      const body = `event: discrepancy\ndata: ${JSON.stringify(finding)}\n\n`;
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(body));

      const onDiscrepancy = vi.fn();
      await streamMedicationAnalysis('c1', 'lisinopril 10mg', null, 'ticket-123', {
        onMedication: vi.fn(),
        onPreviousMedication: vi.fn(),
        onInteraction: vi.fn(),
        onRenal: vi.fn(),
        onPip: vi.fn(),
        onDiscrepancy,
        onDone: vi.fn(),
        onError: vi.fn(),
      });

      expect(onDiscrepancy).toHaveBeenCalledWith(finding);
    });

    it('includes conditions and previous_raw_text in the request body when supplied', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(sseResponse(''));
      await streamMedicationAnalysis(
        'c1',
        'metformin 1000mg',
        {
          age_years: 78,
          conditions: ['heart failure'],
          previous_raw_text: 'metformin 500mg',
        },
        'my-ticket',
        {
          onMedication: vi.fn(),
          onPreviousMedication: vi.fn(),
          onInteraction: vi.fn(),
          onRenal: vi.fn(),
          onPip: vi.fn(),
          onDiscrepancy: vi.fn(),
          onDone: vi.fn(),
          onError: vi.fn(),
        },
      );

      const [, calledInit] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
      expect(calledInit.body).toBe(
        JSON.stringify({
          raw_text: 'metformin 1000mg',
          age_years: 78,
          conditions: ['heart failure'],
          previous_raw_text: 'metformin 500mg',
        }),
      );
    });
  });
});
