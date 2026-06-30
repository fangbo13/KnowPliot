/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0: in-app notification + announcement feed client.
import apiClient from './client';

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
}

export async function fetchFeed(): Promise<FeedItem[]> {
  const { data } = await apiClient.get('/notifications/');
  return data.results ?? [];
}

export async function fetchUnreadCount(): Promise<number> {
  const { data } = await apiClient.get('/notifications/unread-count/');
  return data.count ?? 0;
}

export async function markRead(id: string): Promise<void> {
  await apiClient.post(`/notifications/${id}/read/`);
}

export async function markAllRead(): Promise<void> {
  await apiClient.post('/notifications/read-all/');
}
