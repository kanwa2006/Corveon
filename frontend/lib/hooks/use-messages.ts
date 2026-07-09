'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';

import type { ApiError } from '@/lib/api/auth';
import { listMessages, streamMessage, type MessagePublic } from '@/lib/api/messages';
import { fetchStreamTicket } from '@/lib/api/stream-ticket';

const messagesKey = (chatId: string) => ['messages', chatId] as const;

export function useMessages(chatId: string) {
  return useQuery<MessagePublic[], ApiError>({
    queryKey: messagesKey(chatId),
    queryFn: () => listMessages(chatId),
  });
}

export type SendStatus = 'idle' | 'sending' | 'streaming' | 'error';

export function useSendMessage(chatId: string) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<SendStatus>('idle');
  const [draftText, setDraftText] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (content: string) => {
      setStatus('sending');
      setDraftText('');
      setErrorMessage(null);

      // Show the user's own message immediately — invalidating after the
      // stream finishes replaces this with server truth (with a real id),
      // so there's no duplicate/merge concern.
      const optimisticUser: MessagePublic = {
        id: `optimistic-${Date.now()}`,
        chat_id: chatId,
        role: 'user',
        content,
        routing_trace: null,
        created_at: new Date().toISOString(),
      };
      queryClient.setQueryData<MessagePublic[]>(messagesKey(chatId), (existing) => [
        ...(existing ?? []),
        optimisticUser,
      ]);

      let ticket: string;
      try {
        ticket = await fetchStreamTicket();
      } catch {
        setStatus('error');
        setErrorMessage('Could not start a live connection. Please try again.');
        return;
      }

      const controller = new AbortController();
      abortRef.current = controller;
      setStatus('streaming');

      await streamMessage(
        chatId,
        content,
        ticket,
        {
          onToken: (delta) => setDraftText((prev) => prev + delta),
          onDone: async () => {
            setStatus('idle');
            setDraftText('');
            await queryClient.invalidateQueries({ queryKey: messagesKey(chatId) });
          },
          onError: async (_code, message) => {
            setStatus('error');
            setErrorMessage(message);
            setDraftText('');
            await queryClient.invalidateQueries({ queryKey: messagesKey(chatId) });
          },
        },
        controller.signal,
      );
    },
    [chatId, queryClient],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const dismissError = useCallback(() => {
    setStatus('idle');
    setErrorMessage(null);
  }, []);

  return { send, cancel, dismissError, status, draftText, errorMessage };
}
