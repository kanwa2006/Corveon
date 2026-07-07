/**
 * Shared session-cookie constants. No server-only guard here — this module
 * is imported by both middleware.ts (Edge runtime) and the server-only
 * backend client, so it must stay free of Node-specific APIs.
 */

export const ACCESS_COOKIE = 'corveon_access';
export const REFRESH_COOKIE = 'corveon_refresh';

// Mirror the backend's default TTLs (docs/ENVIRONMENT.md). The JWT's own
// `exp` claim is the real source of truth — these just bound how long the
// browser retains an (possibly already-expired) cookie before dropping it.
export const ACCESS_COOKIE_MAX_AGE_SECONDS = 900; // 15 min
export const REFRESH_COOKIE_MAX_AGE_SECONDS = 1_209_600; // 14 days

export function sessionCookieOptions(maxAgeSeconds: number): {
  httpOnly: true;
  secure: boolean;
  sameSite: 'lax';
  path: '/';
  maxAge: number;
} {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: maxAgeSeconds,
  };
}
