/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../client';
import {
  ALLOWED_DOCUMENT_EXTENSIONS,
  documentApi,
  extractDownloadFilename,
  isSupportedDocumentFile,
} from '../documents';

describe('protected document download client', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('requests the protected endpoint as a blob and returns its server filename', async () => {
    const blob = new Blob(['protected source'], { type: 'text/plain' });
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition': 'attachment; filename="protected-source.txt"',
      },
    });

    const result = await documentApi.downloadDocument('document-id', 'Fallback title');

    expect(get).toHaveBeenCalledWith(
      '/documents/document-id/download/',
      { responseType: 'blob' },
    );
    expect(result).toEqual({
      blob,
      filename: 'protected-source.txt',
    });
  });

  it('decodes RFC 5987 filenames and strips path components', () => {
    expect(
      extractDownloadFilename(
        "attachment; filename*=UTF-8''reports%2FQuarter%20One.pdf",
        'fallback.pdf',
      ),
    ).toBe('Quarter One.pdf');
  });

  it('uses a safe title fallback when the server omits a filename', () => {
    expect(extractDownloadFilename(undefined, '../Unsafe title')).toBe('Unsafe title');
  });
});

describe('document upload policy client', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('exposes exactly the current-version extension policy', () => {
    expect(ALLOWED_DOCUMENT_EXTENSIONS).toEqual([
      '.pdf',
      '.docx',
      '.html',
      '.htm',
      '.txt',
      '.md',
      '.markdown',
    ]);
  });

  it('rejects legacy Office and spreadsheet extensions', () => {
    expect(isSupportedDocumentFile('report.doc')).toBe(false);
    expect(isSupportedDocumentFile('data.csv')).toBe(false);
    expect(isSupportedDocumentFile('data.xlsx')).toBe(false);
    expect(isSupportedDocumentFile('slides.pptx')).toBe(false);
    expect(isSupportedDocumentFile('guide.markdown')).toBe(true);
  });

  it('uploads through the shared API client with server-derived metadata', async () => {
    const file = Object.assign(
      new Blob(['KnowPilot upload'], { type: 'text/plain' }),
      { name: 'policy.txt', lastModified: 0 },
    ) as File;
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { id: 'document-id', file_type: 'txt' },
    });

    await documentApi.uploadDocument(file);

    expect(post).toHaveBeenCalledTimes(1);
    const [url, body, config] = post.mock.calls[0];
    expect(url).toBe('/documents/');
    expect(body).toBeInstanceOf(FormData);
    expect(((body as FormData).get('file') as File).size).toBe(file.size);
    expect((body as FormData).has('title')).toBe(false);
    expect((body as FormData).has('file_type')).toBe(false);
    expect((body as FormData).has('file_size')).toBe(false);
    expect(config).toBeUndefined();
  });
});
