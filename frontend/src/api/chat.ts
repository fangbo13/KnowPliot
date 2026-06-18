import apiClient from './client';
import type { ChatSession } from '../store/chatStore';

export const chatApi = {
  async getSessions(): Promise<ChatSession[]> {
    const { data } = await apiClient.get('/chat/sessions/');
    return data.results || data;
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
    return data.results || data;
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
