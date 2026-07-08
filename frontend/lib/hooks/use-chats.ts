'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { ApiError } from '@/lib/api/auth';
import {
  createChat,
  deleteChat,
  getChat,
  listChats,
  updateChat,
  type ChatListFilters,
  type ChatPublic,
  type ChatUpdatePayload,
} from '@/lib/api/chats';

const CHATS_KEY = ['chats'] as const;
const CHATS_LIST_KEY = [...CHATS_KEY, 'list'] as const;
const chatsListKey = (filters: ChatListFilters) => [...CHATS_LIST_KEY, filters] as const;
const chatDetailKey = (chatId: string) => [...CHATS_KEY, 'detail', chatId] as const;

export function useChats(filters: ChatListFilters = {}) {
  return useQuery<ChatPublic[], ApiError>({
    queryKey: chatsListKey(filters),
    queryFn: () => listChats(filters),
  });
}

export function useChat(chatId: string) {
  return useQuery<ChatPublic, ApiError>({
    queryKey: chatDetailKey(chatId),
    queryFn: () => getChat(chatId),
    retry: false,
  });
}

export function useCreateChat() {
  const queryClient = useQueryClient();
  return useMutation<ChatPublic, ApiError, string | undefined>({
    mutationFn: (title) => createChat(title),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: CHATS_KEY });
    },
  });
}

interface UpdateChatVars {
  chatId: string;
  payload: ChatUpdatePayload;
}

interface UpdateChatContext {
  previousDetail: ChatPublic | undefined;
}

export function useUpdateChat() {
  const queryClient = useQueryClient();

  return useMutation<ChatPublic, ApiError, UpdateChatVars, UpdateChatContext>({
    mutationFn: ({ chatId, payload }) => updateChat(chatId, payload),
    onMutate: async ({ chatId, payload }) => {
      await queryClient.cancelQueries({ queryKey: CHATS_KEY });
      const previousDetail = queryClient.getQueryData<ChatPublic>(chatDetailKey(chatId));

      const patch = (chat: ChatPublic): ChatPublic => ({ ...chat, ...payload });

      // Scoped to CHATS_LIST_KEY, not the bare CHATS_KEY prefix — the latter
      // also matches the single-object detail cache (chatDetailKey), and
      // calling .map() on that would throw, silently aborting the mutation
      // before it ever reaches the network (caught the hard way: mutate()
      // never issued a request at all, with no console error surfaced).
      queryClient.setQueriesData<ChatPublic[]>({ queryKey: CHATS_LIST_KEY }, (chats) =>
        chats?.map((chat) => (chat.id === chatId ? patch(chat) : chat)),
      );
      queryClient.setQueryData<ChatPublic>(chatDetailKey(chatId), (chat) =>
        chat ? patch(chat) : chat,
      );

      return { previousDetail };
    },
    onError: (_err, { chatId }, context) => {
      if (context?.previousDetail) {
        queryClient.setQueryData(chatDetailKey(chatId), context.previousDetail);
      }
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: CHATS_KEY });
    },
  });
}

export function useDeleteChat() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (chatId) => deleteChat(chatId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: CHATS_KEY });
    },
  });
}
