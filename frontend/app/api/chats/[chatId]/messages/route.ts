import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

interface RouteParams {
  params: Promise<{ chatId: string }>;
}

// Only GET is proxied here — sending a message streams via a direct fetch
// against the backend with a stream ticket (ADR-0007/ADR-0016), not through
// this Route Handler (see lib/api/messages.ts).
export async function GET(_request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { chatId } = await params;
  const response = await backendFetch(`/chats/${chatId}/messages`);
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
