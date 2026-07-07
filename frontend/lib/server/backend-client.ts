import 'server-only';

import { cookies } from 'next/headers';

import {
  ACCESS_COOKIE,
  ACCESS_COOKIE_MAX_AGE_SECONDS,
  REFRESH_COOKIE,
  REFRESH_COOKIE_MAX_AGE_SECONDS,
  sessionCookieOptions,
} from '@/lib/session';

// Route Handlers run on the Next.js server, which reaches the FastAPI
// backend at the same address the browser would (no internal network
// between Vercel and Fly/Render in the approved topology, docs/DEPLOYMENT.md).
export const BACKEND_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000/api/v1';

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  return fetch(`${BACKEND_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init.headers },
    cache: 'no-store',
  });
}

/**
 * Calls the FastAPI backend with the caller's session cookie, transparently
 * refreshing the access token once on a 401 before giving up. Must be called
 * from within a Route Handler (needs a mutable cookie store for the retry's
 * refreshed access token).
 */
export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const cookieStore = await cookies();
  const access = cookieStore.get(ACCESS_COOKIE)?.value;

  const attempt = (token: string | undefined): Promise<Response> =>
    rawFetch(path, {
      ...init,
      headers: {
        ...init.headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

  let response = await attempt(access);

  if (response.status === 401) {
    const refresh = cookieStore.get(REFRESH_COOKIE)?.value;
    if (refresh) {
      const refreshResponse = await rawFetch('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (refreshResponse.ok) {
        const { access: newAccess } = (await refreshResponse.json()) as { access: string };
        cookieStore.set(
          ACCESS_COOKIE,
          newAccess,
          sessionCookieOptions(ACCESS_COOKIE_MAX_AGE_SECONDS),
        );
        response = await attempt(newAccess);
      }
    }
  }

  return response;
}

export async function setSessionCookies(access: string, refresh: string): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(ACCESS_COOKIE, access, sessionCookieOptions(ACCESS_COOKIE_MAX_AGE_SECONDS));
  cookieStore.set(REFRESH_COOKIE, refresh, sessionCookieOptions(REFRESH_COOKIE_MAX_AGE_SECONDS));
}

export async function clearSessionCookies(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(ACCESS_COOKIE, '', sessionCookieOptions(0));
  cookieStore.set(REFRESH_COOKIE, '', sessionCookieOptions(0));
}

export async function getAccessCookie(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(ACCESS_COOKIE)?.value;
}

export async function getRefreshCookie(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(REFRESH_COOKIE)?.value;
}

export async function backendJsonFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return rawFetch(path, init);
}
