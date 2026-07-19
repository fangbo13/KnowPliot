/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0: in-app notification + announcement feed client.
import apiClient, { coalescedGet } from './client';

export interface FeedItem {
  id: string;
  kind: 'notification' | 'announcement';
  type: string;
  title: string;
  body: string;
  level: 'info' | 'success' | 'warning' | 'error' | string;
  link: string;
  version: string;
  is_read: boolean;
  created_at: string | null;
  action_kind: 'space_invitation' | 'space_access_request' | 'resource_deleted' | string | null;
  resource_type: 'space_invitation' | 'space_access_request' | string | null;
  resource_id: string | null;
  resource_version: number | null;
  allowed_actions: string[];
  action_state: 'none' | 'available' | 'actioned' | 'stale';
  deep_link: string;
}

export async function fetchFeed(signal?: AbortSignal): Promise<FeedItem[]> {
  const { data } = await coalescedGet<{ results?: FeedItem[] } | FeedItem[]>(
    '/notifications/',
    signal ? { signal } : undefined,
  );
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  throw new Error('invalid_notifications_response');
}

export async function fetchUnreadCount(signal?: AbortSignal): Promise<number> {
  const { data } = await coalescedGet<{ count?: unknown }>('/notifications/unread-count/', signal ? { signal } : undefined);
  if (!data || typeof data.count !== 'number' || !Number.isFinite(data.count)) {
    throw new Error('invalid_notifications_count_response');
  }
  return data.count;
}

export async function markRead(id: string): Promise<void> {
  await apiClient.post(`/notifications/${id}/read/`);
}

export async function markAllRead(): Promise<void> {
  await apiClient.post('/notifications/read-all/');
}

export async function actOnNotification(
  item: FeedItem,
  action: string,
  extra: Record<string, unknown> = {},
): Promise<unknown> {
  if (
    item.kind !== 'notification'
    || item.action_state !== 'available'
    || !item.allowed_actions.includes(action)
    || item.resource_version == null
  ) {
    throw new Error('notification_action_not_available');
  }
  const { data } = await apiClient.post(
    `/notifications/${item.id}/actions/${action}/`,
    { expected_resource_version: item.resource_version, ...extra },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  );
  return data;
}

/** Only same-origin route paths authored by the server may reach the router. */
export function safeNotificationPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return null;
  try {
    const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin;
    const parsed = new URL(value, origin);
    if (parsed.origin !== origin) return null;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}
