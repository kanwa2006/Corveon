/**
 * Client-side calls to our own Next.js Route Handlers for chats — same BFF
 * proxy pattern established for auth (ADR-0012): same-origin, httpOnly
 * cookie flows automatically, no manual Authorization header.
 */

import { ApiError } from '@/lib/api/auth';

export interface ChatPublic {
  id: string;
  user_id: string;
  org_id: string | null;
  title: string;
  is_pinned: boolean;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatListFilters {
  search?: string;
  pinned?: boolean;
  archived?: boolean;
}

function extractMessage(data: Record<string, unknown>): string {
  const details = data.details as { errors?: Array<{ msg?: string }> } | undefined;
  const firstFieldError = details?.errors?.[0]?.msg;
  if (typeof firstFieldError === 'string') {
    return firstFieldError;
  }
  return typeof data.message === 'string'
    ? data.message
    : 'Something went wrong. Please try again.';
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }
  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      typeof data.error_code === 'string' ? data.error_code : 'unknown_error',
      extractMessage(data),
    );
  }
  return data as T;
}

function buildQuery(filters: ChatListFilters): string {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.pinned !== undefined) params.set('pinned', String(filters.pinned));
  if (filters.archived !== undefined) params.set('archived', String(filters.archived));
  const query = params.toString();
  return query ? `?${query}` : '';
}

export async function listChats(filters: ChatListFilters = {}): Promise<ChatPublic[]> {
  const response = await fetch(`/api/chats${buildQuery(filters)}`);
  return parseOrThrow<ChatPublic[]>(response);
}

export async function getChat(chatId: string): Promise<ChatPublic> {
  const response = await fetch(`/api/chats/${chatId}`);
  return parseOrThrow<ChatPublic>(response);
}

export async function createChat(title?: string): Promise<ChatPublic> {
  const response = await fetch('/api/chats', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: title ?? null }),
  });
  return parseOrThrow<ChatPublic>(response);
}

export interface ChatUpdatePayload {
  title?: string;
  is_pinned?: boolean;
  is_archived?: boolean;
}

export async function updateChat(chatId: string, payload: ChatUpdatePayload): Promise<ChatPublic> {
  const response = await fetch(`/api/chats/${chatId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseOrThrow<ChatPublic>(response);
}

export async function deleteChat(chatId: string): Promise<void> {
  const response = await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
  await parseOrThrow<void>(response);
}
