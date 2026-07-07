import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api/auth';
import { createChat, deleteChat, getChat, listChats, updateChat } from '@/lib/api/chats';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const sampleChat = {
  id: '1',
  user_id: 'u1',
  org_id: null,
  title: 'Sample',
  is_pinned: false,
  is_archived: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('lib/api/chats', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('listChats fetches /api/chats with no query string when no filters given', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([sampleChat]));
    const result = await listChats();
    expect(fetch).toHaveBeenCalledWith('/api/chats');
    expect(result).toEqual([sampleChat]);
  });

  it('listChats builds a query string from filters', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([]));
    await listChats({ search: 'renal', pinned: true, archived: false });
    const calledUrl = vi.mocked(fetch).mock.calls[0]?.[0];
    expect(calledUrl).toContain('search=renal');
    expect(calledUrl).toContain('pinned=true');
    expect(calledUrl).toContain('archived=false');
  });

  it('getChat fetches the specific chat', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(sampleChat));
    const result = await getChat('1');
    expect(fetch).toHaveBeenCalledWith('/api/chats/1');
    expect(result).toEqual(sampleChat);
  });

  it('getChat throws ApiError on 404', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ error_code: 'not_found', message: 'Chat not found.' }, 404),
    );
    await expect(getChat('missing')).rejects.toBeInstanceOf(ApiError);
  });

  it('createChat posts with the given title', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(sampleChat, 201));
    const result = await createChat('Sample');
    expect(fetch).toHaveBeenCalledWith(
      '/api/chats',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ title: 'Sample' }),
      }),
    );
    expect(result).toEqual(sampleChat);
  });

  it('createChat posts null title when omitted', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ...sampleChat, title: 'New chat' }, 201));
    await createChat();
    expect(fetch).toHaveBeenCalledWith(
      '/api/chats',
      expect.objectContaining({ body: JSON.stringify({ title: null }) }),
    );
  });

  it('updateChat sends a PATCH with the partial payload', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ...sampleChat, is_pinned: true }));
    const result = await updateChat('1', { is_pinned: true });
    expect(fetch).toHaveBeenCalledWith(
      '/api/chats/1',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ is_pinned: true }) }),
    );
    expect(result.is_pinned).toBe(true);
  });

  it('deleteChat sends a DELETE and resolves on 204 with no body', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(deleteChat('1')).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith('/api/chats/1', { method: 'DELETE' });
  });

  it('deleteChat throws ApiError when the delete is rejected', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ error_code: 'not_found', message: 'Chat not found.' }, 404),
    );
    await expect(deleteChat('missing')).rejects.toBeInstanceOf(ApiError);
  });
});
