'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { ApiError } from '@/lib/api/auth';
import {
  deleteSsoConfig,
  getSsoConfig,
  startSso,
  upsertSsoConfig,
  type SsoConfigPublic,
  type SsoConfigUpsertPayload,
} from '@/lib/api/sso';

const SSO_CONFIG_KEY = ['org', 'sso-config'] as const;

export function useStartSso() {
  return useMutation<{ redirect_url: string }, ApiError, string>({
    mutationFn: (email) => startSso(email),
  });
}

export function useSsoConfig() {
  return useQuery<SsoConfigPublic | null, ApiError>({
    queryKey: SSO_CONFIG_KEY,
    queryFn: getSsoConfig,
  });
}

export function useUpsertSsoConfig() {
  const queryClient = useQueryClient();
  return useMutation<SsoConfigPublic, ApiError, SsoConfigUpsertPayload>({
    mutationFn: (payload) => upsertSsoConfig(payload),
    onSuccess: (config) => {
      queryClient.setQueryData(SSO_CONFIG_KEY, config);
    },
  });
}

export function useDeleteSsoConfig() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: deleteSsoConfig,
    onSuccess: () => {
      queryClient.setQueryData(SSO_CONFIG_KEY, null);
    },
  });
}
