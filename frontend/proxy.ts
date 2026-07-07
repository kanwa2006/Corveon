import { NextResponse, type NextRequest } from 'next/server';

import { ACCESS_COOKIE, REFRESH_COOKIE } from '@/lib/session';

/**
 * Presence-only session check for UX routing. This is NOT the authorization
 * boundary — every actual API call still requires a valid, non-expired,
 * non-revoked bearer token verified by the FastAPI backend regardless of
 * what this middleware decides. It only redirects users to the right page.
 */
const PROTECTED_PREFIXES = ['/dashboard'];
const AUTH_PAGE_PREFIXES = ['/login', '/register'];

export function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;
  const hasSession = Boolean(
    request.cookies.get(ACCESS_COOKIE)?.value ?? request.cookies.get(REFRESH_COOKIE)?.value,
  );

  const isProtected = PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  const isAuthPage = AUTH_PAGE_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  if (isProtected && !hasSession) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('next', pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isAuthPage && hasSession) {
    return NextResponse.redirect(new URL('/dashboard', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/login', '/register'],
};
