import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/server/backend-client';

interface RouteParams {
  params: Promise<{ jobId: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { jobId } = await params;
  const response = await backendFetch(`/jobs/${jobId}`);
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
