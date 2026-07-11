import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

export async function GET(): Promise<NextResponse> {
  const response = await backendFetch('/org/sso-config');
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.text();
  const response = await backendFetch('/org/sso-config', { method: 'POST', body });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function DELETE(): Promise<NextResponse> {
  const response = await backendFetch('/org/sso-config', { method: 'DELETE' });
  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
