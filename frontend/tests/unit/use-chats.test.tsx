import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useUpdateChat } from '@/lib/hooks/use-chats';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const sampleChat = {
  id: 'chat-1',
  user_id: 'u1',
  org_id: null,
  title: 'Original title',
  is_pinned: false,
  is_archived: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('useUpdateChat', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it(
    'does not throw when both a list cache entry AND a detail cache entry ' +
      'exist for the same chat (regression: setQueriesData with a bare ' +
      "['chats'] key previously matched the detail cache too, and calling " +
      '.map() on that single-object entry crashed onMutate, silently ' +
      'preventing the PATCH request from ever being sent)',
    async () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      });

      // Seed exactly the two cache shapes the real app produces: a chats
      // list (array) and a chat detail (single object) for the same chat.
      queryClient.setQueryData(['chats', 'list', {}], [sampleChat]);
      queryClient.setQueryData(['chats', 'detail', 'chat-1'], sampleChat);

      vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ...sampleChat, title: 'Renamed' }));

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => useUpdateChat(), { wrapper });

      result.current.mutate({ chatId: 'chat-1', payload: { title: 'Renamed' } });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      // The real bug: this fetch call never happened because onMutate threw.
      expect(fetch).toHaveBeenCalledWith(
        '/api/chats/chat-1',
        expect.objectContaining({ method: 'PATCH' }),
      );

      const listCache = queryClient.getQueryData(['chats', 'list', {}]);
      expect(listCache).toEqual([{ ...sampleChat, title: 'Renamed' }]);

      const detailCache = queryClient.getQueryData(['chats', 'detail', 'chat-1']);
      expect(detailCache).toMatchObject({ title: 'Renamed' });
    },
  );
});
