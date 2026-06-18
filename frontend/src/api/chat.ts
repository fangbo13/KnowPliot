import apiClient from './client';
import type { ChatSession } from '../store/chatStore';

export const chatApi = {
  async getSessions(): Promise<ChatSession[]> {
    const { data } = await apiClient.get('/chat/sessions/');
    // Pagination disabled on backend; expect a plain array
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.results)) return data.results;
    throw new Error('Unexpected sessions response format');
  },

  async createSession(body: { title: string }): Promise<ChatSession> {
    const { data } = await apiClient.post('/chat/sessions/', body);
    return data;
  },

  async getSession(id: string): Promise<ChatSession> {
    const { data } = await apiClient.get(`/chat/sessions/${id}/`);
    return data;
  },

  async deleteSession(id: string): Promise<void> {
    await apiClient.delete(`/chat/sessions/${id}/`);
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
