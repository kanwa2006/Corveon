import { NextResponse } from 'next/server';

import { backendJsonFetch } from '@/lib/server/backend-client';

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const response = await backendJsonFetch('/auth/sso/start', { method: 'POST', body });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
