import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { StreamMessageCallbacks } from '@/lib/api/messages';
import { useSendMessage } from '@/lib/hooks/use-messages';

vi.mock('@/lib/api/stream-ticket', () => ({
  fetchStreamTicket: vi.fn(),
}));

vi.mock('@/lib/api/messages', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/messages')>('@/lib/api/messages');
  return { ...actual, streamMessage: vi.fn() };
});

import { fetchStreamTicket } from '@/lib/api/stream-ticket';
import { streamMessage } from '@/lib/api/messages';

describe('useSendMessage', () => {
  beforeEach(() => {
    vi.mocked(fetchStreamTicket).mockResolvedValue('a-ticket');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  function wrapper() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const Wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    return { queryClient, Wrapper };
  }

  it('optimistically adds the user message, then streams tokens into draftText', async () => {
    let capturedCallbacks: StreamMessageCallbacks | undefined;
    vi.mocked(streamMessage).mockImplementation(async (_chatId, _content, _ticket, callbacks) => {
      capturedCallbacks = callbacks;
      callbacks.onToken('Hello');
      callbacks.onToken(' world');
    });

    const { queryClient, Wrapper } = wrapper();
    const { result } = renderHook(() => useSendMessage('c1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.send('What treats a cold?');
    });

    expect(capturedCallbacks).toBeDefined();
    const cached = queryClient.getQueryData<Array<{ role: string; content: string }>>([
      'messages',
      'c1',
    ]);
    expect(cached?.[0]).toMatchObject({ role: 'user', content: 'What treats a cold?' });
    expect(result.current.draftText).toBe('Hello world');
  });

  it('transitions to the error state and surfaces the message when no provider is available', async () => {
    vi.mocked(streamMessage).mockImplementation(async (_chatId, _content, _ticket, callbacks) => {
      await callbacks.onError('provider_unavailable', 'No AI provider is currently reachable.');
    });

    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useSendMessage('c1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.send('hi');
    });

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.errorMessage).toBe('No AI provider is currently reachable.');
    expect(result.current.draftText).toBe('');
  });

  it('sets status to error without ever streaming when the ticket fetch fails', async () => {
    vi.mocked(fetchStreamTicket).mockRejectedValueOnce(new Error('network down'));

    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useSendMessage('c1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.send('hi');
    });

    expect(streamMessage).not.toHaveBeenCalled();
    expect(result.current.status).toBe('error');
  });
});
