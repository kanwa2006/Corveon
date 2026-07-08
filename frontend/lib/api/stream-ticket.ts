/**
 * Mints a short-lived stream ticket (ADR-0016) via our own Route Handler
 * (cookie-authenticated, same-origin) so the browser can open an SSE
 * connection directly against the backend (ADR-0007) without ever exposing
 * the real session-backing access token.
 */

import { ApiError } from '@/lib/api/auth';

export async function fetchStreamTicket(): Promise<string> {
  const response = await fetch('/api/stream-ticket', { method: 'POST' });
  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      typeof data.error_code === 'string' ? data.error_code : 'unknown_error',
      'Could not start a live connection. Please try again.',
    );
  }
  return data.ticket as string;
}
