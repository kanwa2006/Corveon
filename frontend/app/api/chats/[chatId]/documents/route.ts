import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

interface RouteParams {
  params: Promise<{ chatId: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { chatId } = await params;
  const response = await backendFetch(`/chats/${chatId}/documents`);
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { chatId } = await params;
  const formData = await request.formData();
  const response = await backendFetch(`/chats/${chatId}/documents`, {
    method: 'POST',
    body: formData,
  });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
