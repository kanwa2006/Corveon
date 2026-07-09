import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api/auth';
import { deleteDocument, getJob, listDocuments, uploadDocument } from '@/lib/api/documents';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const sampleDocument = {
  id: 'd1',
  chat_id: 'c1',
  filename: 'notes.pdf',
  mime_type: 'application/pdf',
  size_bytes: 1024,
  status: 'ready' as const,
  page_count: 1,
  error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('lib/api/documents', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('listDocuments fetches the chat document list', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([sampleDocument]));
    const result = await listDocuments('c1');
    expect(fetch).toHaveBeenCalledWith('/api/chats/c1/documents');
    expect(result).toEqual([sampleDocument]);
  });

  it('uploadDocument posts a multipart FormData body with the file', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ job_id: 'j1' }, 202));
    const file = new File([new Blob(['%PDF-1.4'])], 'doc.pdf', { type: 'application/pdf' });

    const result = await uploadDocument('c1', file);

    expect(fetch).toHaveBeenCalledWith(
      '/api/chats/c1/documents',
      expect.objectContaining({ method: 'POST' }),
    );
    const callArgs = vi.mocked(fetch).mock.calls[0]?.[1] as RequestInit;
    expect(callArgs.body).toBeInstanceOf(FormData);
    expect((callArgs.body as FormData).get('file')).toBe(file);
    expect(result).toEqual({ job_id: 'j1' });
  });

  it('uploadDocument throws ApiError on validation failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ error_code: 'validation_error', message: 'Only PDF uploads are supported.' }, 422),
    );
    const file = new File([new Blob(['not a pdf'])], 'notes.txt', { type: 'text/plain' });
    await expect(uploadDocument('c1', file)).rejects.toBeInstanceOf(ApiError);
  });

  it('deleteDocument sends a DELETE and resolves on 204', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(deleteDocument('d1')).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith('/api/documents/d1', { method: 'DELETE' });
  });

  it('getJob fetches job status', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ id: 'j1', status: 'succeeded', progress_stage: 'complete', error: null }),
    );
    const result = await getJob('j1');
    expect(fetch).toHaveBeenCalledWith('/api/jobs/j1');
    expect(result.status).toBe('succeeded');
  });
});
