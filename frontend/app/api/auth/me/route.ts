import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

export async function GET(): Promise<NextResponse> {
  const response = await backendFetch('/auth/me');
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
