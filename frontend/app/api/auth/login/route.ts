import { NextResponse } from 'next/server';

import { backendJsonFetch, setSessionCookies } from '@/lib/server/backend-client';

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const response = await backendJsonFetch('/auth/login', { method: 'POST', body });
  const data = await response.json();

  if (!response.ok) {
    return NextResponse.json(data, { status: response.status });
  }

  await setSessionCookies(data.access, data.refresh);
  return NextResponse.json({ ok: true }, { status: 200 });
}
