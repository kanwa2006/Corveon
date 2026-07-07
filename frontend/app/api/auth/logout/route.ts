import { NextResponse } from 'next/server';

import {
  backendJsonFetch,
  clearSessionCookies,
  getAccessCookie,
  getRefreshCookie,
} from '@/lib/server/backend-client';

export async function POST(): Promise<NextResponse> {
  const access = await getAccessCookie();
  const refresh = await getRefreshCookie();

  if (access) {
    await backendJsonFetch('/auth/logout', {
      method: 'POST',
      headers: { Authorization: `Bearer ${access}` },
      body: JSON.stringify({ refresh_token: refresh ?? null }),
    }).catch(() => {
      // Best-effort server-side revoke — the local session clears regardless.
    });
  }

  await clearSessionCookies();
  return NextResponse.json({ ok: true });
}
