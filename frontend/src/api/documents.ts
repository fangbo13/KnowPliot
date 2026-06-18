import apiClient from './client';

export const documentApi = {
  async getDocuments(params?: { category?: string; status?: string; page?: number }): Promise<any> {
    const { data } = await apiClient.get('/documents/', { params });
    return data;
  },

  async uploadDocument(file: File, title: string, category?: string): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);
    if (category) formData.append('category', category);

    const { data } = await apiClient.post('/documents/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async getDocument(id: string): Promise<any> {
    const { data } = await apiClient.get(`/documents/${id}/`);
    return data;
  },

  async updateDocument(id: string, body: Record<string, unknown>): Promise<any> {
    const { data } = await apiClient.patch(`/documents/${id}/`, body);
    return data;
  },

  async deleteDocument(id: string): Promise<void> {
    await apiClient.delete(`/documents/${id}/`);
  },

  async reindexDocument(id: string): Promise<any> {
    const { data } = await apiClient.post(`/documents/${id}/reindex/`);
    return data;
  },

  async getChunks(documentId: string): Promise<any> {
    const { data } = await apiClient.get(`/documents/${documentId}/chunks/`);
    return data;
  },

  async getCategories(): Promise<any> {
    const { data } = await apiClient.get('/documents/categories/');
    return data;
  },

  async createCategory(body: { name: string; slug: string; description?: string }): Promise<any> {
    const { data } = await apiClient.post('/documents/categories/', body);
    return data;
  },
};
