/**
 * Client-side calls for Enterprise SSO (ADR-0025) — same BFF proxy pattern
 * established for auth (ADR-0012). `startSso` is unauthenticated (the user
 * isn't logged in yet); the sso-config calls are authenticated and org-admin
 * only, same as chats.ts.
 */

import { ApiError } from '@/lib/api/auth';

export interface SsoConfigPublic {
  id: string;
  org_id: string;
  provider_type: string;
  issuer: string;
  client_id: string;
  email_domain: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SsoConfigUpsertPayload {
  issuer: string;
  client_id: string;
  client_secret: string;
  email_domain: string;
}

function extractMessage(data: Record<string, unknown>): string {
  const details = data.details as { errors?: Array<{ msg?: string }> } | undefined;
  const firstFieldError = details?.errors?.[0]?.msg;
  if (typeof firstFieldError === 'string') {
    return firstFieldError;
  }
  return typeof data.message === 'string'
    ? data.message
    : 'Something went wrong. Please try again.';
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }
  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      typeof data.error_code === 'string' ? data.error_code : 'unknown_error',
      extractMessage(data),
    );
  }
  return data as T;
}

export async function startSso(email: string): Promise<{ redirect_url: string }> {
  const response = await fetch('/api/auth/sso/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return parseOrThrow<{ redirect_url: string }>(response);
}

export async function getSsoConfig(): Promise<SsoConfigPublic | null> {
  const response = await fetch('/api/org/sso-config');
  if (response.status === 404) {
    return null;
  }
  return parseOrThrow<SsoConfigPublic>(response);
}

export async function upsertSsoConfig(
  payload: SsoConfigUpsertPayload,
): Promise<SsoConfigPublic> {
  const response = await fetch('/api/org/sso-config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseOrThrow<SsoConfigPublic>(response);
}

export async function deleteSsoConfig(): Promise<void> {
  const response = await fetch('/api/org/sso-config', { method: 'DELETE' });
  await parseOrThrow<void>(response);
}
