import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

interface RouteParams {
  params: Promise<{ documentId: string }>;
}

export async function DELETE(
  _request: NextRequest,
  { params }: RouteParams,
): Promise<NextResponse> {
  const { documentId } = await params;
  const response = await backendFetch(`/documents/${documentId}`, { method: 'DELETE' });
  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
