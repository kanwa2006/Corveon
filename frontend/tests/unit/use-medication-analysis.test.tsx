import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  InteractionFinding,
  NormalizedMedication,
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
      async (_chatId, _rawText, _ticket, callbacks) => {
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

  it('transitions to the error state and surfaces the message on a degraded-mode error', async () => {
    vi.mocked(streamMedicationAnalysis).mockImplementation(
      async (_chatId, _rawText, _ticket, callbacks) => {
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

  it('reset clears medications/findings and returns to idle', async () => {
    vi.mocked(streamMedicationAnalysis).mockImplementation(
      async (_chatId, _rawText, _ticket, callbacks) => {
        callbacks.onMedication(sampleMedication);
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
    expect(result.current.findings).toEqual([]);
  });
});
