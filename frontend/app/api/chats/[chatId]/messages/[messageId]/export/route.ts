import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

interface RouteParams {
  params: Promise<{ chatId: string; messageId: string }>;
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { chatId, messageId } = await params;
  const body = await request.text();
  const response = await backendFetch(`/chats/${chatId}/messages/${messageId}/export`, {
    method: 'POST',
    body,
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  }

  const data = await response.arrayBuffer();
  return new NextResponse(data, {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('Content-Type') ?? 'application/octet-stream',
      'Content-Disposition': response.headers.get('Content-Disposition') ?? 'attachment',
    },
  });
}
