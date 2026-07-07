'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  ApiError,
  fetchCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
  type UserPublic,
} from '@/lib/api/auth';

const CURRENT_USER_KEY = ['auth', 'me'] as const;

export function useCurrentUser() {
  return useQuery<UserPublic, ApiError>({
    queryKey: CURRENT_USER_KEY,
    queryFn: fetchCurrentUser,
    retry: false,
  });
}

export function useRegister() {
  return useMutation<UserPublic, ApiError, { email: string; password: string }>({
    mutationFn: ({ email, password }) => registerUser(email, password),
  });
}

export function useLogin() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, { email: string; password: string }>({
    mutationFn: ({ email, password }) => loginUser(email, password),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: CURRENT_USER_KEY });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, void>({
    mutationFn: logoutUser,
    onSuccess: () => {
      queryClient.setQueryData(CURRENT_USER_KEY, null);
    },
  });
}
