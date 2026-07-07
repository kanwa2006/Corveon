import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

export async function GET(request: NextRequest): Promise<NextResponse> {
  const search = request.nextUrl.search;
  const response = await backendFetch(`/chats${search}`);
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.text();
  const response = await backendFetch('/chats', { method: 'POST', body });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
