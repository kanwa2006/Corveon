import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, fetchCurrentUser, loginUser, logoutUser, registerUser } from '@/lib/api/auth';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('lib/api/auth', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('registerUser posts to /api/auth/register and returns the created user', async () => {
    const user = {
      id: '1',
      email: 'a@b.com',
      role: 'user',
      org_id: null,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(user, 201));

    const result = await registerUser('a@b.com', 'correcthorsebattery');

    expect(fetch).toHaveBeenCalledWith(
      '/api/auth/register',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result).toEqual(user);
  });

  it('registerUser throws ApiError with a field-specific message on 422', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(
        {
          error_code: 'validation_error',
          message: 'Request validation failed.',
          details: { errors: [{ msg: 'String should have at least 12 characters' }] },
        },
        422,
      ),
    );

    await expect(registerUser('a@b.com', 'short')).rejects.toMatchObject({
      status: 422,
      errorCode: 'validation_error',
      message: 'String should have at least 12 characters',
    });
  });

  it('registerUser falls back to the generic message when no field error is present', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ error_code: 'conflict', message: 'An account with this email already exists.' }, 409),
    );

    await expect(registerUser('a@b.com', 'correcthorsebattery')).rejects.toThrow(
      'An account with this email already exists.',
    );
  });

  it('loginUser resolves silently on success', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ok: true }, 200));
    await expect(loginUser('a@b.com', 'correcthorsebattery')).resolves.toBeUndefined();
  });

  it('loginUser throws ApiError on 401', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ error_code: 'unauthorized', message: 'Incorrect email or password.' }, 401),
    );

    await expect(loginUser('a@b.com', 'wrong')).rejects.toBeInstanceOf(ApiError);
  });

  it('logoutUser posts to /api/auth/logout', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ok: true }));
    await logoutUser();
    expect(fetch).toHaveBeenCalledWith('/api/auth/logout', { method: 'POST' });
  });

  it('fetchCurrentUser returns the user profile', async () => {
    const user = {
      id: '1',
      email: 'a@b.com',
      role: 'user',
      org_id: null,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(user));

    await expect(fetchCurrentUser()).resolves.toEqual(user);
  });

  it('fetchCurrentUser throws on 401 when unauthenticated', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ error_code: 'unauthorized', message: 'Missing bearer token.' }, 401),
    );
    await expect(fetchCurrentUser()).rejects.toMatchObject({ status: 401 });
  });
});
