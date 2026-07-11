import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  DiscrepancyFinding,
  InteractionFinding,
  NormalizedMedication,
  PipFinding,
  RenalFinding,
  StreamMedicationAnalysisCallbacks,
} from '@/lib/api/medication';
import { useMedicationAnalysis } from '@/lib/hooks/use-medication-analysis';

vi.mock('@/lib/api/stream-ticket', () => ({
  fetchStreamTicket: vi.fn(),
}));

vi.mock('@/lib/api/medication', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/medication')>('@/lib/api/medication');
  return { ...actual, streamMedicationAnalysis: vi.fn() };
});

import { streamMedicationAnalysis } from '@/lib/api/medication';
import { fetchStreamTicket } from '@/lib/api/stream-ticket';

const sampleMedication: NormalizedMedication = {
  id: 'm1',
  raw_text: 'metformin 500mg',
  name: 'Metformin',
  rxcui: '6809',
  dose: '500mg',
  route: null,
  frequency: null,
};

const sampleFinding: InteractionFinding = {
  id: 'f1',
  medication_a_id: 'm1',
  medication_b_id: 'm2',
  severity: 'major',
  source: 'ddinter',
  rule_id: 'rule-1',
  explanation: 'Increased bleeding risk.',
  provenance: {},
};

const sampleRenalFinding: RenalFinding = {
  id: 'r1',
  medication_id: 'm1',
  crcl_ml_min: 12.7,
  egfr_ml_min: 17.9,
  threshold_ml_min: 30.0,
  severity: 'major',
  rule_id: 'renal_threshold:apixaban',
  explanation: 'Both equations are below threshold.',
};

const samplePipFinding: PipFinding = {
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

const sampleDiscrepancyFinding: DiscrepancyFinding = {
  id: 'd1',
  kind: 'added',
  current_medication_id: 'm1',
  previous_medication_id: null,
  rule_id: 'discrepancy:added',
  explanation: 'Metformin appears in the current list but not the previous one.',
  narrative: null,
  provenance: { name: 'metformin', rxcui: null },
};

describe('useMedicationAnalysis', () => {
  beforeEach(() => {
    vi.mocked(fetchStreamTicket).mockResolvedValue('a-ticket');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('streams medications and findings into state and transitions to done', async () => {
    let capturedCallbacks: StreamMedicationAnalysisCallbacks | undefined;
    vi.mocked(streamMedicationAnalysis).mockImplementation(
      async (_chatId, _rawText, _renalParams, _ticket, callbacks) => {
        capturedCallbacks = callbacks;
        callbacks.onMedication(sampleMedication);
        callbacks.onInteraction(sampleFinding);
        callbacks.onDone();
      },
    );

    const { result } = renderHook(() => useMedicationAnalysis('c1'));

    await act(async () => {
      await result.current.analyze('metformin 500mg');
    });

    expect(capturedCallbacks).toBeDefined();
    expect(result.current.medications).toEqual([sampleMedication]);
    expect(result.current.findings).toEqual([sampleFinding]);
    expect(result.current.status).toBe('done');
  });

  it('streams renal findings into state and passes renal params through', async () => {
    let capturedRenalParams: unknown;
    vi.mocked(streamMedicationAnalysis).mockImplementation(
      async (_chatId, _rawText, renalParams, _ticket, callbacks) => {
        capturedRenalParams = renalParams;
        callbacks.onRenal(sampleRenalFinding);
        callbacks.onDone();
      },
    );

    const { result } = renderHook(() => useMedicationAnalysis('c1'));
    const renalParams = {
      age_years: 85,
      weight_kg: 50,
      sex: 'male' as const,
      serum_creatinine_mg_dl: 3.0,
      height_cm: 170,
    };

    await act(async () => {
      await result.current.analyze('apixaban 5mg', renalParams);
    });

    expect(capturedRenalParams).toEqual(renalParams);
    expect(result.current.renalFindings).toEqual([sampleRenalFinding]);
  });

  it('streams PIP findings into state', async () => {
    vi.mocked(streamMedicationAnalysis).mockImplementation(
      async (_chatId, _rawText, _params, _ticket, callbacks) => {
        callbacks.onPip(samplePipFinding);
        callbacks.onDone();
      },
    );

    const { result } = renderHook(() => useMedicationAnalysis('c1'));

    await act(async () => {
      await result.current.analyze('diphenhydramine 25mg', { age_years: 78 });
    });

    expect(result.current.pipFindings).toEqual([samplePipFinding]);
  });

  it('streams previous-list medications and discrepancy findings into state', async () => {
    vi.mocked(streamMedicationAnalysis).mockImplementation(
      async (_chatId, _rawText, _params, _ticket, callbacks) => {
        callbacks.onPreviousMedication(sampleMedication);
        callbacks.onDiscrepancy(sampleDiscrepancyFinding);
        callbacks.onDone();
      },
    );

    const { result } = renderHook(() => useMedicationAnalysis('c1'));

    await act(async () => {
      await result.current.analyze('metformin 1000mg', { previous_raw_text: 'metformin 500mg' });
    });

    expect(result.current.previousMedications).toEqual([sampleMedication]);
    expect(result.current.discrepancyFindings).toEqual([sampleDiscrepancyFinding]);
  });

  it('transitions to the error state and surfaces the message on a degraded-mode error', async () => {
    vi.mocked(streamMedicationAnalysis).mockImplementation(
      async (_chatId, _rawText, _renalParams, _ticket, callbacks) => {
        await callbacks.onError('provider_unavailable', 'No AI provider is currently reachable.');
      },
    );

    const { result } = renderHook(() => useMedicationAnalysis('c1'));

    await act(async () => {
      await result.current.analyze('metformin 500mg');
    });

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.errorMessage).toBe('No AI provider is currently reachable.');
  });

  it('sets status to error without ever streaming when the ticket fetch fails', async () => {
    vi.mocked(fetchStreamTicket).mockRejectedValueOnce(new Error('network down'));

    const { result } = renderHook(() => useMedicationAnalysis('c1'));

    await act(async () => {
      await result.current.analyze('metformin 500mg');
    });

    expect(streamMedicationAnalysis).not.toHaveBeenCalled();
    expect(result.current.status).toBe('error');
  });

  it('reset clears all medication/finding state and returns to idle', async () => {
    vi.mocked(streamMedicationAnalysis).mockImplementation(
      async (_chatId, _rawText, _params, _ticket, callbacks) => {
        callbacks.onMedication(sampleMedication);
        callbacks.onPreviousMedication(sampleMedication);
        callbacks.onRenal(sampleRenalFinding);
        callbacks.onPip(samplePipFinding);
        callbacks.onDiscrepancy(sampleDiscrepancyFinding);
        callbacks.onDone();
      },
    );

    const { result } = renderHook(() => useMedicationAnalysis('c1'));

    await act(async () => {
      await result.current.analyze('metformin 500mg');
    });
    expect(result.current.medications).toHaveLength(1);

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.medications).toEqual([]);
    expect(result.current.previousMedications).toEqual([]);
    expect(result.current.findings).toEqual([]);
    expect(result.current.renalFindings).toEqual([]);
    expect(result.current.pipFindings).toEqual([]);
    expect(result.current.discrepancyFindings).toEqual([]);
  });
});
