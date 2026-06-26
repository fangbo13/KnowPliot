// Crawler API module — V4.1 KB-V4.1-011~017 frontend API client.

import apiClient from './client';

export interface CrawledDocument {
  id: string;
  source_url: string;
  crawl_status: 'pending' | 'fetching' | 'parsing' | 'cleaning' | 'embedding' | 'active' | 'failed' | 'withdrawn' | 'duplicate_skipped';
  title_extracted: string;
  content_hash: string;
  copyright_status: 'unknown' | 'internal_only' | 'public_domain' | 'restricted';
  internal_only: boolean;
  robots_txt_allowed: boolean;
  raw_content_size: number;
  cleaned_content_size: number;
  error_message: string;
  submitted_by_email: string;
  document_title: string;
  submitted_at: string;
  crawled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrawlRequest {
  url: string;
  category_id?: string;
  internal_only?: boolean;
}

/** Submit a URL for crawling */
export const submitCrawl = async (data: CrawlRequest): Promise<CrawledDocument> => {
  const response = await apiClient.post('/crawl/crawl/', data);
  return response.data;
};

/** List all crawled documents */
export const listCrawledDocuments = async (): Promise<CrawledDocument[]> => {
  const response = await apiClient.get('/crawl/');
  return response.data;
};

/** Get a specific crawled document */
export const getCrawledDocument = async (id: string): Promise<CrawledDocument> => {
  const response = await apiClient.get(`/crawl/${id}/`);
  return response.data;
};

/** Withdraw (takedown) a crawled document */
export const withdrawCrawl = async (id: string, reason?: string): Promise<CrawledDocument> => {
  const response = await apiClient.post(`/crawl/${id}/withdraw/`, { reason });
  return response.data;
};

/** Bulk withdraw all crawled content from a specific URL */
export const withdrawByURL = async (url: string, reason?: string): Promise<{ detail: string; count: number }> => {
  const response = await apiClient.post('/crawl/withdraw-by-url/', { url, reason });
  return response.data;
};
