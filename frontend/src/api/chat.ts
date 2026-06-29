import apiClient from './client';
import type { ChatSession } from '../store/chatStore';

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
    updatedAt: raw.updated_at ?? raw.updatedAt ?? '',  // snake_case → camelCase
  };
}

export const chatApi = {
  async getSessions(): Promise<ChatSession[]> {
    const { data } = await apiClient.get('/chat/sessions/');
    // Pagination disabled on backend; expect a plain array
    if (Array.isArray(data)) return data.map(mapSession);
    if (Array.isArray(data.results)) return data.results.map(mapSession);
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

  async getMessages(sessionId: string): Promise<any[]> {
    const { data } = await apiClient.get(`/chat/sessions/${sessionId}/messages/`);
    // Pagination disabled on backend; expect a plain array
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.results)) return data.results;
    throw new Error('Unexpected messages response format');
  },

  async submitFeedback(messageId: string, data: {
    rating: number;
    reason?: string;
    comment?: string;
  }): Promise<any> {
    const response = await apiClient.post(
      `/chat/messages/${messageId}/feedback/`,
      data
    );
    return response.data;
  },

  async getQuickActions(): Promise<any> {
    const { data } = await apiClient.get('/chat/quick-actions/');
    return data;
  },
};
