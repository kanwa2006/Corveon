import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { StreamVerificationCallbacks, VerifiedClaim } from '@/lib/api/evidence';
import { useEvidenceVerification } from '@/lib/hooks/use-evidence-verification';

vi.mock('@/lib/api/stream-ticket', () => ({
  fetchStreamTicket: vi.fn(),
}));

vi.mock('@/lib/api/evidence', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/evidence')>('@/lib/api/evidence');
  return { ...actual, streamVerification: vi.fn() };
});

import { streamVerification } from '@/lib/api/evidence';
import { fetchStreamTicket } from '@/lib/api/stream-ticket';

const sampleClaim: VerifiedClaim = {
  id: 'c1',
  ordinal: 0,
  text: 'Metformin is first-line therapy for type 2 diabetes.',
  source_class: 'verified_public',
  confidence_score: 82,
  confidence_rationale: 'Base 70 for verified_public evidence; ...',
  flags: [],
  citations: [],
};

describe('useEvidenceVerification', () => {
  beforeEach(() => {
    vi.mocked(fetchStreamTicket).mockResolvedValue('a-ticket');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('streams claims into state and transitions to done', async () => {
    let capturedCallbacks: StreamVerificationCallbacks | undefined;
    vi.mocked(streamVerification).mockImplementation(
      async (_chatId, _messageId, _ticket, callbacks) => {
        capturedCallbacks = callbacks;
        callbacks.onClaim(sampleClaim);
        callbacks.onDone({ verification_id: 'v1', status: 'succeeded' });
      },
    );

    const { result } = renderHook(() => useEvidenceVerification('c1'));

    await act(async () => {
      await result.current.verify('m1');
    });

    expect(capturedCallbacks).toBeDefined();
    expect(result.current.claims).toEqual([sampleClaim]);
    expect(result.current.status).toBe('done');
  });

  it('transitions to the error state and surfaces the message on a degraded-mode error', async () => {
    vi.mocked(streamVerification).mockImplementation(
      async (_chatId, _messageId, _ticket, callbacks) => {
        await callbacks.onError('provider_unavailable', 'No AI provider is currently reachable.');
      },
    );

    const { result } = renderHook(() => useEvidenceVerification('c1'));

    await act(async () => {
      await result.current.verify('m1');
    });

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.errorMessage).toBe('No AI provider is currently reachable.');
  });

  it('sets status to error without ever streaming when the ticket fetch fails', async () => {
    vi.mocked(fetchStreamTicket).mockRejectedValueOnce(new Error('network down'));

    const { result } = renderHook(() => useEvidenceVerification('c1'));

    await act(async () => {
      await result.current.verify('m1');
    });

    expect(streamVerification).not.toHaveBeenCalled();
    expect(result.current.status).toBe('error');
  });

  it('reset clears claims and returns to idle', async () => {
    vi.mocked(streamVerification).mockImplementation(
      async (_chatId, _messageId, _ticket, callbacks) => {
        callbacks.onClaim(sampleClaim);
        callbacks.onDone({ verification_id: 'v1', status: 'succeeded' });
      },
    );

    const { result } = renderHook(() => useEvidenceVerification('c1'));

    await act(async () => {
      await result.current.verify('m1');
    });
    expect(result.current.claims).toHaveLength(1);

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.claims).toEqual([]);
  });
});
