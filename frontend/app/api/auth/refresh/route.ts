import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { backendJsonFetch, getRefreshCookie } from '@/lib/server/backend-client';
import { ACCESS_COOKIE, ACCESS_COOKIE_MAX_AGE_SECONDS, sessionCookieOptions } from '@/lib/session';

export async function POST(): Promise<NextResponse> {
  const refresh = await getRefreshCookie();
  if (!refresh) {
    return NextResponse.json(
      { error_code: 'unauthorized', message: 'No session.' },
      { status: 401 },
    );
  }

  const response = await backendJsonFetch('/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refresh }),
  });
  const data = await response.json();

  if (!response.ok) {
    return NextResponse.json(data, { status: response.status });
  }

  const cookieStore = await cookies();
  cookieStore.set(ACCESS_COOKIE, data.access, sessionCookieOptions(ACCESS_COOKIE_MAX_AGE_SECONDS));
  return NextResponse.json({ ok: true });
}
