import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

export async function POST(): Promise<NextResponse> {
  const response = await backendFetch('/auth/stream-ticket', { method: 'POST' });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
