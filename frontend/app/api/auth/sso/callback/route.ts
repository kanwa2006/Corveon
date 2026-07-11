import { NextRequest, NextResponse } from 'next/server';

import { backendJsonFetch, setSessionCookies } from '@/lib/server/backend-client';

export async function GET(request: NextRequest): Promise<NextResponse> {
  const code = request.nextUrl.searchParams.get('code');
  const state = request.nextUrl.searchParams.get('state');

  if (!code || !state) {
    return NextResponse.redirect(new URL('/login?error=sso_failed', request.url));
  }

  const response = await backendJsonFetch(
    `/auth/sso/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
  );

  if (!response.ok) {
    return NextResponse.redirect(new URL('/login?error=sso_failed', request.url));
  }

  const data = (await response.json()) as { access: string; refresh: string };
  await setSessionCookies(data.access, data.refresh);
  return NextResponse.redirect(new URL('/dashboard', request.url));
}
