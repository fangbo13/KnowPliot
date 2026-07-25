/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import axios, {
  type AxiosRequestConfig,
  type AxiosResponse,
} from 'axios';

/**
 * The API error vocabulary is deliberately kept outside individual pages.
 * Navigation code can therefore distinguish an aborted request from a server
 * throttle without guessing from a translated message or an empty payload.
 */
export const MAX_RETRY_AFTER_SECONDS = 120;

export interface RateLimitDetails {
  code: 'rate_limited';
  retryAfterSeconds: number | null;
}

export type ApiErrorCategory =
  | 'abort'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'rate_limited'
  | 'server'
  | 'timeout'
  | 'network'
  | 'unknown';

type ErrorLike = {
  code?: unknown;
  apiCode?: unknown;
  response?: {
    status?: unknown;
    data?: unknown;
    headers?: unknown;
  };
  rateLimit?: unknown;
  name?: unknown;
  message?: unknown;
};

function asErrorLike(error: unknown): ErrorLike {
  return error && typeof error === 'object' ? error as ErrorLike : {};
}

function headerValue(headers: unknown, name: string): unknown {
  if (!headers || typeof headers !== 'object') return undefined;
  const candidate = headers as {
    get?: (key: string) => unknown;
    [key: string]: unknown;
  };
  if (typeof candidate.get === 'function') {
    const value = candidate.get(name);
    if (value !== undefined && value !== null) return value;
  }
  return candidate[name] ?? candidate[name.toLowerCase()]
    ?? candidate[name.toUpperCase()];
}

function recordValue(value: unknown, key: string): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  return (value as Record<string, unknown>)[key];
}

/** Parse Retry-After seconds/date and clamp it to the client contract. */
export function parseRetryAfter(
  value: unknown,
  now = Date.now(),
): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, Math.min(MAX_RETRY_AFTER_SECONDS, Math.ceil(value)));
  }
  if (typeof value !== 'string' || !value.trim()) return null;
  const trimmed = value.trim();
  const seconds = Number(trimmed);
  if (Number.isFinite(seconds)) {
    return Math.max(0, Math.min(MAX_RETRY_AFTER_SECONDS, Math.ceil(seconds)));
  }
  const timestamp = Date.parse(trimmed);
  if (!Number.isFinite(timestamp)) return null;
  return Math.max(0, Math.min(MAX_RETRY_AFTER_SECONDS, Math.ceil((timestamp - now) / 1000)));
}

/** Return a stable rate-limit code and bounded Retry-After value. */
export function getRateLimitDetails(error: unknown, now = Date.now()): RateLimitDetails | null {
  const candidate = asErrorLike(error);
  const status = candidate.response?.status;
  const responseData = candidate.response?.data;
  const responseCode = recordValue(responseData, 'code');
  const isRateLimited = status === 429
    || responseCode === 'rate_limited'
    || candidate.apiCode === 'rate_limited'
    || (candidate.rateLimit && typeof candidate.rateLimit === 'object');
  if (!isRateLimited) return null;

  const retryHeader = headerValue(candidate.response?.headers, 'Retry-After');
  const retryBody = recordValue(responseData, 'retry_after')
    ?? recordValue(responseData, 'retry_after_seconds');
  const prior = candidate.rateLimit;
  const priorSeconds = prior && typeof prior === 'object'
    ? (prior as { retryAfterSeconds?: unknown }).retryAfterSeconds
    : undefined;
  return {
    code: 'rate_limited',
    retryAfterSeconds: parseRetryAfter(
      retryHeader ?? retryBody ?? priorSeconds,
      now,
    ),
  };
}

export function getApiErrorCode(error: unknown): string | null {
  const candidate = asErrorLike(error);
  const rateLimit = getRateLimitDetails(error);
  if (rateLimit) return rateLimit.code;
  if (typeof candidate.apiCode === 'string' && candidate.apiCode) return candidate.apiCode;
  const bodyCode = recordValue(candidate.response?.data, 'code');
  if (typeof bodyCode === 'string' && bodyCode) return bodyCode;
  return null;
}

export function isAbortError(error: unknown): boolean {
  if (axios.isCancel(error)) return true;
  const candidate = asErrorLike(error);
  return candidate.name === 'AbortError'
    || candidate.code === 'ERR_CANCELED'
    || candidate.code === 'ABORT_ERR';
}

/** Classify transport failures without coupling UI to Axios internals. */
export function classifyApiError(error: unknown): ApiErrorCategory {
  if (isAbortError(error)) return 'abort';
  const candidate = asErrorLike(error);
  const status = typeof candidate.response?.status === 'number'
    ? candidate.response.status
    : null;
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 429 || getRateLimitDetails(error)) return 'rate_limited';
  if (status != null && status >= 500) return 'server';
  if (candidate.code === 'ECONNABORTED' || candidate.code === 'ETIMEDOUT') return 'timeout';
  if (!candidate.response) return 'network';
  return 'unknown';
}

function annotateRateLimit(error: unknown): unknown {
  const details = getRateLimitDetails(error);
  if (!details || !error || typeof error !== 'object') return error;
  const candidate = error as { apiCode?: unknown; rateLimit?: unknown };
  candidate.apiCode = details.code;
  candidate.rateLimit = details;
  return error;
}

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token + active space to requests
apiClient.interceptors.request.use((config) => {
  try {
    const saved = localStorage.getItem('ey-auth');
    if (saved) {
      const { token } = JSON.parse(saved);
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
  } catch {
    // ignore
  }
  // V6.0: scope every request to the active knowledge space. The backend reads
  // X-Space-Id and isolates documents / sessions / retrieval to that space.
  const spaceId = getActiveSpaceId();
  if (spaceId) {
    config.headers['X-Space-Id'] = spaceId;
  }
  // When sending FormData, remove the default JSON Content-Type so the browser
  // attaches the correct multipart/form-data boundary automatically.
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type'];
    delete config.headers.common?.['Content-Type'];
  }
  return config;
});

// Handle 401 responses
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('ey-auth');
      window.location.href = '/login';
    }
    annotateRateLimit(error);
    return Promise.reject(error);
  }
);

/**
 * Get the current auth token from localStorage.
 * Use this for non-axios requests (e.g., fetch, SSE, Upload components).
 */
export function getAuthToken(): string {
  try {
    const saved = localStorage.getItem('ey-auth');
    if (saved) {
      const { token } = JSON.parse(saved);
      return token || '';
    }
  } catch {
    // ignore
  }
  return '';
}

/** localStorage key holding the active knowledge space id (V6.0). */
export const ACTIVE_SPACE_KEY = 'ey-active-space';

/**
 * Current active space id, used to scope API requests. Returns '' when none is
 * selected (the backend then falls back to the user's default space).
 * Use this for non-axios requests (e.g. SSE fetch) which bypass the interceptor.
 */
export function getActiveSpaceId(): string {
  try {
    return localStorage.getItem(ACTIVE_SPACE_KEY) || '';
  } catch {
    return '';
  }
}

type CoalescedGetEntry<T> = {
  controller: AbortController;
  promise: Promise<AxiosResponse<T>>;
  activeSubscribers: number;
  settled: boolean;
};

const inFlightGets = new Map<string, CoalescedGetEntry<unknown>>();
let ambientRequestSignal: AbortSignal | undefined;

/**
 * Supply a route-owned signal without changing legacy API call signatures.
 * API methods synchronously create their Axios request before the callback
 * returns, so the signal is captured by the request config while mocked or
 * older callers still observe their original argument list.
 */
export function withRequestSignal<T>(signal: AbortSignal, callback: () => T): T {
  const previous = ambientRequestSignal;
  ambientRequestSignal = signal;
  try {
    return callback();
  } finally {
    ambientRequestSignal = previous;
  }
}

export function getRequestSignal(): AbortSignal | undefined {
  return ambientRequestSignal;
}

function stableSerialize(value: unknown): string {
  if (value === undefined) return '';
  if (value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return JSON.stringify(value);
  }
  if (value instanceof URLSearchParams) {
    return stableSerialize([...value.entries()].sort(([a], [b]) => a.localeCompare(b)));
  }
  if (Array.isArray(value)) return `[${value.map(stableSerialize).join(',')}]`;
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).filter((key) => key !== 'signal').sort().map((key) => (
      `${JSON.stringify(key)}:${stableSerialize(record[key])}`
    )).join(',')}}`;
  }
  return JSON.stringify(String(value));
}

function authFingerprint(): string {
  const token = getAuthToken();
  return token ? `${token.length}:${token.slice(-12)}` : 'anonymous';
}

/**
 * Build the cache key for one logical GET resource. The active auth/scope are
 * part of the key so a response cannot leak across users or spaces during a
 * rapid route switch. AbortSignal itself is intentionally excluded.
 */
export function logicalGetKey(url: string, config?: AxiosRequestConfig): string {
  return [
    'GET',
    url,
    stableSerialize(config?.params),
    stableSerialize(config?.headers),
    config?.responseType ?? '',
    getActiveSpaceId(),
    authFingerprint(),
  ].join('|');
}

function createAbortError(): Error {
  if (typeof DOMException !== 'undefined') return new DOMException('The operation was aborted.', 'AbortError');
  const error = new Error('The operation was aborted.');
  error.name = 'AbortError';
  return error;
}

function detachSubscriber<T>(entry: CoalescedGetEntry<T>): void {
  entry.activeSubscribers = Math.max(0, entry.activeSubscribers - 1);
  if (entry.activeSubscribers === 0 && !entry.settled) entry.controller.abort();
}

function subscribeToGet<T>(entry: CoalescedGetEntry<T>, signal?: AbortSignal): Promise<AxiosResponse<T>> {
  if (!signal) return entry.promise;
  if (signal.aborted) return Promise.reject(createAbortError());

  entry.activeSubscribers += 1;
  return new Promise<AxiosResponse<T>>((resolve, reject) => {
    let detached = false;
    const cleanup = () => signal.removeEventListener('abort', onAbort);
    const onAbort = () => {
      if (detached) return;
      detached = true;
      cleanup();
      detachSubscriber(entry);
      reject(createAbortError());
    };
    signal.addEventListener('abort', onAbort, { once: true });
    entry.promise.then(
      (response) => {
        if (detached) return;
        detached = true;
        cleanup();
        detachSubscriber(entry);
        resolve(response);
      },
      (error: unknown) => {
        if (detached) return;
        detached = true;
        cleanup();
        detachSubscriber(entry);
        reject(error);
      },
    );
  });
}

/**
 * Coalesce identical in-flight GETs while preserving a route caller's
 * cancellation semantics. Each signal gets its own subscriber promise; the
 * shared transport is aborted only after every signal-backed subscriber has
 * detached. Callers without a signal retain the historical Axios call shape.
 */
export function coalescedGet<T = unknown>(
  url: string,
  config?: AxiosRequestConfig,
  options?: { preserveSignal?: boolean },
): Promise<AxiosResponse<T>> {
  const signal = config?.signal as AbortSignal | undefined;
  if (signal?.aborted) return Promise.reject(createAbortError());

  const key = logicalGetKey(url, config);
  let entry = inFlightGets.get(key) as CoalescedGetEntry<T> | undefined;
  // Once the last subscriber leaves, detachSubscriber aborts the shared
  // transport. Axios may not settle that transport until a later microtask;
  // a replacement route read must not attach to the already-aborted entry in
  // that window or it will inherit the cancellation and render stale data.
  if (entry?.controller.signal.aborted && !entry.settled) {
    if (inFlightGets.get(key) === entry) inFlightGets.delete(key);
    entry = undefined;
  }
  if (!entry) {
    const controller = new AbortController();
    const transportConfig = signal && !options?.preserveSignal
      ? { ...config, signal: controller.signal }
      : config;
    // Preserve one-argument calls for existing API consumers/tests where no
    // request config is needed. Config-bearing calls remain byte-for-byte
    // equivalent apart from the internal signal above.
    const request = transportConfig === undefined
      ? apiClient.get<T>(url)
      : apiClient.get<T>(url, transportConfig);
    const promise = request.finally(() => {
      entry!.settled = true;
      if (inFlightGets.get(key) === entry) inFlightGets.delete(key);
    });
    entry = {
      controller,
      promise,
      activeSubscribers: 0,
      settled: false,
    };
    inFlightGets.set(key, entry);
    // A route may detach every subscriber before the transport rejects. Keep
    // the shared rejection observed so it never becomes an unhandled promise.
    void promise.catch(() => undefined);
  }
  return subscribeToGet(entry, signal);
}

/** Test and logout hook: no response from an old identity may be reused. */
export function clearInFlightGets(): void {
  for (const entry of inFlightGets.values()) entry.controller.abort();
  inFlightGets.clear();
}

export default apiClient;
