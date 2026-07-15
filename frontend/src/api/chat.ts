/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import apiClient from './client';
import type { ChatSession, Citation, Message } from '../store/chatStore';

export interface CursorPage<T> {
  results: T[];
  next: string | null;
  previous: string | null;
}

interface CursorRequest {
  cursor?: string | null;
  signal?: AbortSignal;
}

function cursorToken(cursor: string): string {
  try {
    return new URL(cursor, 'http://localhost').searchParams.get('cursor') ?? cursor;
  } catch {
    return cursor;
  }
}

export interface ChatMessageRecord {
  id?: string;
  role: Message['role'];
  content?: string;
  citations?: Citation[];
  confidence_score?: number | null;
  confidence_label?: Message['confidenceLabel'];
  needs_human_review?: boolean;
  retrieval_mode?: string;
  retrieval_latency_ms?: number | null;
  created_at?: string;
  createdAt?: string;
}

/**
 * Map a raw backend session object (snake_case keys) to the frontend ChatSession
 * interface (camelCase keys). The backend serializer returns updated_at, created_at,
 * is_active, etc. — the frontend expects updatedAt, is_active (kept as-is for parity).
 *
 * Without this mapping, s.updatedAt would be undefined, causing all sessions to fall
 * into the '30days' fallback group in getDateGroupKey().
 */
function mapSession(raw: any): ChatSession {
  return {
    id: raw.id,
    title: raw.title,
    is_active: raw.is_active,
    isPinned: Boolean(raw.is_pinned),
    updatedAt: raw.updated_at ?? raw.updatedAt ?? '',  // snake_case → camelCase
  };
}

export const chatApi = {
  async getSessions(options: CursorRequest = {}): Promise<CursorPage<ChatSession>> {
    const { data } = options.cursor
      ? await apiClient.get('/chat/sessions/', { params: { cursor: cursorToken(options.cursor) } })
      : await apiClient.get('/chat/sessions/');
    if (Array.isArray(data)) {
      return { results: data.map(mapSession), next: null, previous: null };
    }
    if (Array.isArray(data.results)) {
      return {
        results: data.results.map(mapSession),
        next: data.next ?? null,
        previous: data.previous ?? null,
      };
    }
    throw new Error('Unexpected sessions response format');
  },

  async createSession(body: { title: string }): Promise<ChatSession> {
    const { data } = await apiClient.post('/chat/sessions/', body);
    return mapSession(data);
  },

  async getSession(id: string): Promise<ChatSession> {
    const { data } = await apiClient.get(`/chat/sessions/${id}/`);
    return mapSession(data);
  },

  async deleteSession(id: string): Promise<void> {
    await apiClient.delete(`/chat/sessions/${id}/`);
  },

  async renameSession(id: string, title: string): Promise<ChatSession> {
    const { data } = await apiClient.patch(`/chat/sessions/${id}/`, { title });
    return mapSession(data);
  },

  async pinSession(id: string, isPinned: boolean): Promise<ChatSession> {
    const { data } = await apiClient.patch(`/chat/sessions/${id}/`, {
      is_pinned: isPinned,
    });
    return mapSession(data);
  },

  async exportSession(id: string, format: 'markdown' | 'html'): Promise<Blob> {
    const { data } = await apiClient.get(`/chat/sessions/${id}/export/`, {
      params: { format },
      responseType: 'blob',
    });
    return data;
  },

  async getMessages(
    sessionId: string,
    options: CursorRequest = {},
  ): Promise<CursorPage<ChatMessageRecord>> {
    const url = `/chat/sessions/${sessionId}/messages/`;
    const config = options.cursor || options.signal
      ? {
          ...(options.cursor ? { params: { cursor: cursorToken(options.cursor) } } : {}),
          ...(options.signal ? { signal: options.signal } : {}),
        }
      : null;
    const { data } = config
      ? await apiClient.get(url, config)
      : await apiClient.get(url);
    if (Array.isArray(data)) {
      return { results: data, next: null, previous: null };
    }
    if (Array.isArray(data.results)) {
      return {
        results: data.results,
        next: data.next ?? null,
        previous: data.previous ?? null,
      };
    }
    throw new Error('Unexpected messages response format');
  },

  async getFeedback(messageId: string): Promise<any> {
    const { data } = await apiClient.get(`/chat/messages/${messageId}/feedback/`);
    return data.feedback;
  },

  async submitFeedback(messageId: string, data: {
    type?: 'helpful' | 'unhelpful' | 'incorrect' | 'outdated' | 'missing_source';
    rating?: number;
    reason?: string;
    comment?: string;
    suggested_source?: string;
    flag_for_review?: boolean;
  }): Promise<any> {
    const response = await apiClient.post(
      `/chat/messages/${messageId}/feedback/`,
      data
    );
    return response.data;
  },

  async updateFeedback(messageId: string, data: {
    type: 'helpful' | 'unhelpful' | 'incorrect' | 'outdated' | 'missing_source';
    comment?: string;
    suggested_source?: string;
    flag_for_review?: boolean;
  }): Promise<any> {
    const response = await apiClient.put(`/chat/messages/${messageId}/feedback/`, data);
    return response.data;
  },

  async withdrawFeedback(messageId: string): Promise<any> {
    const response = await apiClient.delete(`/chat/messages/${messageId}/feedback/`);
    return response.data;
  },

  async getQuickActions(): Promise<any> {
    const { data } = await apiClient.get('/chat/quick-actions/');
    return data;
  },
};
