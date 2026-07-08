/**
 * Documents + jobs: listing/upload/delete go through our own Route Handlers
 * (cookie-authenticated, ADR-0012); job-progress events use a direct
 * EventSource against the backend (ADR-0007), authenticated with a
 * short-lived stream ticket (ADR-0016) — EventSource is a GET, so unlike
 * messages it doesn't need the manual fetch-stream parsing.
 */

import { ApiError } from '@/lib/api/auth';

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface DocumentPublic {
  id: string;
  chat_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: DocumentStatus;
  page_count: number | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface JobPublic {
  id: string;
  status: JobStatus;
  progress_stage: string | null;
  error: string | null;
}

async function parseOrThrow<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }
  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      typeof data.error_code === 'string' ? data.error_code : 'unknown_error',
      typeof data.message === 'string' ? data.message : fallbackMessage,
    );
  }
  return data as T;
}

export async function listDocuments(chatId: string): Promise<DocumentPublic[]> {
  const response = await fetch(`/api/chats/${chatId}/documents`);
  return parseOrThrow<DocumentPublic[]>(response, 'Could not load documents.');
}

export async function uploadDocument(chatId: string, file: File): Promise<{ job_id: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`/api/chats/${chatId}/documents`, {
    method: 'POST',
    body: formData,
  });
  return parseOrThrow<{ job_id: string }>(response, 'Upload failed. Please try again.');
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(`/api/documents/${documentId}`, { method: 'DELETE' });
  await parseOrThrow<void>(response, 'Could not delete this document.');
}

export async function getJob(jobId: string): Promise<JobPublic> {
  const response = await fetch(`/api/jobs/${jobId}`);
  return parseOrThrow<JobPublic>(response, 'Could not load job status.');
}

const SSE_BASE_URL = process.env.NEXT_PUBLIC_SSE_BASE_URL ?? 'http://localhost:8000';

const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set(['succeeded', 'failed']);

export interface JobEventCallbacks {
  onStage: (job: JobPublic) => void;
  onNotFound: () => void;
  onConnectionError: () => void;
}

export function subscribeToJobEvents(
  jobId: string,
  ticket: string,
  callbacks: JobEventCallbacks,
): () => void {
  const source = new EventSource(
    `${SSE_BASE_URL}/api/v1/jobs/${jobId}/events?ticket=${encodeURIComponent(ticket)}`,
  );

  source.addEventListener('stage', (event) => {
    const job = JSON.parse((event as MessageEvent).data) as JobPublic;
    callbacks.onStage(job);
    if (TERMINAL_STATUSES.has(job.status)) {
      source.close();
    }
  });

  source.addEventListener('error', (event) => {
    // A custom named "error" SSE event (business-logic failure) always
    // carries a data payload; EventSource's own generic connection-error
    // event never does — this is how we tell them apart.
    const data = (event as MessageEvent).data as string | undefined;
    if (data) {
      callbacks.onNotFound();
    } else {
      callbacks.onConnectionError();
    }
    source.close();
  });

  return () => source.close();
}
