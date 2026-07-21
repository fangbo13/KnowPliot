// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient, {
  clearInFlightGets,
  classifyApiError,
  coalescedGet,
  getApiErrorCode,
  getRateLimitDetails,
  isAbortError,
  logicalGetKey,
  parseRetryAfter,
} from '../client';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('request reliability contract', () => {
  afterEach(() => {
    clearInFlightGets();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('coalesces identical in-flight GETs and clears the entry after settlement', async () => {
    const request = deferred<{ data: { results: string[] } }>();
    const get = vi.spyOn(apiClient, 'get').mockReturnValue(request.promise as any);

    const first = coalescedGet<{ results: string[] }>('/spaces/');
    const second = coalescedGet<{ results: string[] }>('/spaces/');
    expect(get).toHaveBeenCalledTimes(1);
    request.resolve({ data: { results: ['one'] } });
    await expect(first).resolves.toMatchObject({ data: { results: ['one'] } });
    await expect(second).resolves.toMatchObject({ data: { results: ['one'] } });

    await coalescedGet('/spaces/');
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('detaches an aborted route subscriber without cancelling another subscriber', async () => {
    const request = deferred<{ data: { value: string } }>();
    const get = vi.spyOn(apiClient, 'get').mockReturnValue(request.promise as any);
    const firstController = new AbortController();
    const secondController = new AbortController();

    const first = coalescedGet<{ value: string }>('/spaces/space-1/', { signal: firstController.signal });
    const second = coalescedGet<{ value: string }>('/spaces/space-1/', { signal: secondController.signal });
    firstController.abort();
    await expect(first.catch((error) => {
      expect(isAbortError(error)).toBe(true);
      throw error;
    })).rejects.toBeDefined();
    expect((get.mock.calls[0]?.[1] as { signal: AbortSignal }).signal.aborted).toBe(false);

    request.resolve({ data: { value: 'fresh' } });
    await expect(second).resolves.toMatchObject({ data: { value: 'fresh' } });
  });

  it('aborts the shared transport once every route subscriber leaves', async () => {
    const request = deferred<{ data: { value: string } }>();
    const get = vi.spyOn(apiClient, 'get').mockReturnValue(request.promise as any);
    const firstController = new AbortController();
    const secondController = new AbortController();
    const first = coalescedGet('/spaces/space-2/', { signal: firstController.signal });
    const second = coalescedGet('/spaces/space-2/', { signal: secondController.signal });
    firstController.abort();
    secondController.abort();
    await expect(first.catch((error) => {
      expect(isAbortError(error)).toBe(true);
      throw error;
    })).rejects.toBeDefined();
    await expect(second.catch((error) => {
      expect(isAbortError(error)).toBe(true);
      throw error;
    })).rejects.toBeDefined();
    expect((get.mock.calls[0]?.[1] as { signal: AbortSignal }).signal.aborted).toBe(true);
    request.reject(new Error('transport aborted'));
  });

  it('starts a fresh GET instead of joining an aborted transport awaiting settlement', async () => {
    const abandonedRequest = deferred<{ data: { value: string } }>();
    const replacementRequest = deferred<{ data: { value: string } }>();
    const get = vi.spyOn(apiClient, 'get')
      .mockReturnValueOnce(abandonedRequest.promise as any)
      .mockReturnValueOnce(replacementRequest.promise as any);
    const abandonedController = new AbortController();
    const replacementController = new AbortController();

    const abandoned = coalescedGet<{ value: string }>('/spaces/space-3/', {
      signal: abandonedController.signal,
    });
    abandonedController.abort();
    await expect(abandoned).rejects.toSatisfy(isAbortError);

    const replacement = coalescedGet<{ value: string }>('/spaces/space-3/', {
      signal: replacementController.signal,
    });
    expect(get).toHaveBeenCalledTimes(2);

    replacementRequest.resolve({ data: { value: 'replacement' } });
    await expect(replacement).resolves.toMatchObject({ data: { value: 'replacement' } });
    abandonedRequest.reject(new Error('transport aborted'));
  });

  it('normalizes bounded Retry-After and exposes the stable rate-limited code', () => {
    expect(parseRetryAfter('7')).toBe(7);
    expect(parseRetryAfter('999')).toBe(120);
    expect(parseRetryAfter('not-a-date')).toBeNull();
    const error = {
      response: {
        status: 429,
        headers: { 'retry-after': '9' },
        data: { code: 'rate_limited' },
      },
    };
    expect(getApiErrorCode(error)).toBe('rate_limited');
    expect(getRateLimitDetails(error)).toEqual({ code: 'rate_limited', retryAfterSeconds: 9 });
    expect(classifyApiError(error)).toBe('rate_limited');
    expect(classifyApiError({ response: { status: 403 } })).toBe('forbidden');
    expect(classifyApiError({ code: 'ECONNABORTED' })).toBe('timeout');
  });

  it('includes auth and active-space identity in logical resource keys', () => {
    localStorage.setItem('ey-auth', JSON.stringify({ token: 'token-a' }));
    localStorage.setItem('ey-active-space', 'space-a');
    const first = logicalGetKey('/spaces/', { params: { q: 'x' } });
    localStorage.setItem('ey-active-space', 'space-b');
    const second = logicalGetKey('/spaces/', { params: { q: 'x' } });
    expect(first).not.toBe(second);
  });
});
