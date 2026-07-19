/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import apiClient from './client';
import type { ChatExecutionSnapshot, ChatSession, Citation, Message } from '../store/chatStore';
export type { ChatExecutionSnapshot, ExecutionSnapshot } from '../store/chatStore';

export interface CursorPage<T> {
  results: T[];
  next: string | null;
  previous: string | null;
}

interface CursorRequest {
  cursor?: string | null;
  signal?: AbortSignal;
}

export type HistoryTimeFilter = 'all' | 'today' | 'this_week' | 'this_month' | 'older';
export type HistoryStatusFilter = 'all' | 'partial' | 'recovering' | 'recovered' | 'failed' | 'terminal';

export interface SessionPageRequest extends CursorRequest {
  query?: string;
  time?: HistoryTimeFilter;
  status?: HistoryStatusFilter;
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
  /** Assistant-only server-owned execution snapshot; absent on user rows. */
  execution_snapshot?: ChatExecutionSnapshot | null;
  executionSnapshot?: ChatExecutionSnapshot | null;
  created_at?: string;
  createdAt?: string;
}

export interface ConversationShare {
  id: string;
  token: string;
  session: string;
  expires_at: string;
  revoked_at?: string | null;
  created_at?: string;
}

export interface SharedConversation {
  id: string;
  token: string;
  title: string;
  expires_at: string;
  read_only: true;
  messages: ChatMessageRecord[];
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
    ...(raw.recovery_state ? { recoveryState: raw.recovery_state } : {}),
    updatedAt: raw.updated_at ?? raw.updatedAt ?? '',  // snake_case → camelCase
  };
}

export const chatApi = {
  async getSessions(options: SessionPageRequest = {}): Promise<CursorPage<ChatSession>> {
    const params = {
      ...(options.query?.trim() ? { q: options.query.trim() } : {}),
      ...(options.time && options.time !== 'all' ? { time: options.time } : {}),
      ...(options.status && options.status !== 'all' ? { status: options.status } : {}),
      ...(options.cursor ? { cursor: cursorToken(options.cursor) } : {}),
    };
    const hasConfig = Object.keys(params).length > 0 || Boolean(options.signal);
    const { data } = hasConfig
      ? await apiClient.get('/chat/sessions/', {
          ...(Object.keys(params).length > 0 ? { params } : {}),
          ...(options.signal ? { signal: options.signal } : {}),
        })
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

  async branchMessage(
    messageId: string,
    options: { clientRequestId?: string; title?: string } = {},
  ): Promise<ChatSession> {
    const { data } = await apiClient.post(`/chat/messages/${messageId}/branch/`, {
      client_request_id: options.clientRequestId ?? crypto.randomUUID(),
      ...(options.title ? { title: options.title } : {}),
    });
    return mapSession(data);
  },

  async createShare(sessionId: string, clientRequestId: string = crypto.randomUUID()): Promise<ConversationShare> {
    const { data } = await apiClient.post(`/chat/sessions/${sessionId}/shares/`, {
      client_request_id: clientRequestId,
    });
    return data;
  },

  async listShares(sessionId: string): Promise<ConversationShare[]> {
    const { data } = await apiClient.get(`/chat/sessions/${sessionId}/shares/`);
    return data;
  },

  async revokeShare(shareId: string): Promise<void> {
    await apiClient.delete(`/chat/shares/${shareId}/`);
  },

  async getSharedConversation(token: string): Promise<SharedConversation> {
    const { data } = await apiClient.get(`/chat/shares/${token}/view/`);
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
