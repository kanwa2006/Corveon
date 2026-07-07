/**
 * Client-side calls to our OWN Next.js Route Handlers (same-origin — cookies
 * flow automatically, no manual Authorization header, no CORS). The Route
 * Handlers hold the httpOnly session cookie and proxy to the FastAPI backend.
 */

export type UserRole = 'user' | 'org-admin' | 'superadmin';

export interface UserPublic {
  id: string;
  email: string;
  role: UserRole;
  org_id: string | null;
  is_active: boolean;
  created_at: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public errorCode: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
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

export async function registerUser(email: string, password: string): Promise<UserPublic> {
  const response = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return parseOrThrow<UserPublic>(response);
}

export async function loginUser(email: string, password: string): Promise<void> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  await parseOrThrow<{ ok: true }>(response);
}

export async function logoutUser(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST' });
}

export async function fetchCurrentUser(): Promise<UserPublic> {
  const response = await fetch('/api/auth/me');
  return parseOrThrow<UserPublic>(response);
}
