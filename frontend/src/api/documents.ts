/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import apiClient from './client';

export const ALLOWED_DOCUMENT_EXTENSIONS = [
  '.pdf',
  '.docx',
  '.html',
  '.htm',
  '.txt',
  '.md',
  '.markdown',
] as const;

export function isSupportedDocumentFile(filename: string): boolean {
  const lowerName = filename.toLowerCase();
  return ALLOWED_DOCUMENT_EXTENSIONS.some((extension) =>
    lowerName.endsWith(extension),
  );
}

function safeBasename(value: string): string {
  const basename = value.replace(/\\/g, '/').split('/').pop() || '';
  const cleaned = basename.replace(/[\u0000-\u001f\u007f]/g, '').trim();
  return cleaned || 'document';
}

export function extractDownloadFilename(
  contentDisposition: string | undefined,
  fallback: string,
): string {
  if (contentDisposition) {
    const encodedMatch = contentDisposition.match(
      /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i,
    );
    if (encodedMatch?.[1]) {
      const encoded = encodedMatch[1].trim().replace(/^["']|["']$/g, '');
      try {
        return safeBasename(decodeURIComponent(encoded));
      } catch {
        return safeBasename(encoded);
      }
    }

    const plainMatch = contentDisposition.match(
      /filename\s*=\s*(?:"([^"]+)"|([^;]+))/i,
    );
    const plain = plainMatch?.[1] || plainMatch?.[2];
    if (plain) {
      return safeBasename(plain.trim());
    }
  }

  return safeBasename(fallback);
}

export const documentApi = {
  async getDocuments(params?: { category?: string; status?: string; page?: number }): Promise<any> {
    const { data } = await apiClient.get('/documents/', { params });
    return data;
  },

  async uploadDocument(file: File, title?: string, category?: string): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    if (title?.trim()) formData.append('title', title.trim());
    if (category) formData.append('category', category);

    const { data } = await apiClient.post('/documents/', formData);
    return data;
  },

  // KB-12-Features §7: Create document from text (JSON body, no file upload)
  async createFromText(body: { title: string; text_content: string; category?: string }): Promise<any> {
    const { data } = await apiClient.post('/documents/', body);
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
    await apiClient.delete(`/documents/${id}/?hard=true`);
  },

  async archiveDocument(id: string): Promise<void> {
    await apiClient.delete(`/documents/${id}/`);
  },

  async downloadDocument(
    id: string,
    fallbackTitle: string,
  ): Promise<{ blob: Blob; filename: string }> {
    const response = await apiClient.get(`/documents/${id}/download/`, {
      responseType: 'blob',
    });
    return {
      blob: response.data,
      filename: extractDownloadFilename(
        response.headers['content-disposition'],
        fallbackTitle,
      ),
    };
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

  // KB-12-Features §1: Version endpoint methods

  async editTextContent(id: string, text: string): Promise<any> {
    const { data } = await apiClient.patch(`/documents/${id}/text/`, {
      text_content: text,
    });
    return data;
  },

  async previewDiff(id: string, text: string): Promise<any> {
    const { data } = await apiClient.post(`/documents/${id}/preview-diff/`, {
      text_content: text,
    });
    return data;
  },

  async createVersion(
    id: string,
    body: { text_content: string; effective_from?: string; reason?: string },
  ): Promise<any> {
    const { data } = await apiClient.post(`/documents/${id}/versions/`, body, {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    return data;
  },

  async rollbackVersion(
    id: string,
    body: { target_version_id?: string; effective_from?: string; reason?: string },
  ): Promise<any> {
    const { data } = await apiClient.post(`/documents/${id}/rollback/`, body, {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    return data;
  },

  async getVersions(id: string): Promise<any> {
    const { data } = await apiClient.get(`/documents/${id}/versions/`);
    return data;
  },

  // KB-12-Features §8: Document template methods

  async getDocumentTemplates(): Promise<any> {
    const { data } = await apiClient.get('/documents/document-templates/');
    return data;
  },

  async getDocumentTemplate(slug: string): Promise<any> {
    const { data } = await apiClient.get(`/documents/document-templates/${slug}/`);
    return data;
  },

  // KB-12-Features §9: Word/PDF→Markdown conversion

  async convertToMarkdown(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await apiClient.post('/documents/convert/', formData);
    return data;
  },

  // KB-12-Features §11: Batch upload methods

  async batchUpload(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('zip_file', file);
    const { data } = await apiClient.post('/documents/batch/upload/', formData);
    return data;
  },

  async getBatchResult(id: string): Promise<any> {
    const { data } = await apiClient.get(`/documents/batch/result/${id}/`);
    return data;
  },
};
