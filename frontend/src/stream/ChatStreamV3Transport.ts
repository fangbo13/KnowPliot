import { getActiveSpaceId, getAuthToken } from '../api/client';
import { validateChatStreamMessage, validateRecoveryResponseIdentity, type ValidatedChatStreamEvent } from './ChatStreamProtocol';
import { StoreSSEDecoder } from './SSEParser';

export interface AcceptedChatTurnV3 {
  turn_id: string;
  session_id: string;
  client_request_id: string;
  status: 'accepted' | 'completed';
  events_url: string;
  status_url: string;
  cancel_url: string;
}

export interface V3SendRequest {
  sessionId: string;
  content: string;
  clientRequestId: string;
  answerMode: 'fast' | 'deep';
  thinkingEnabled: boolean;
  regenerateMessageId?: string;
  /** Session-level reference-library selection; undefined = leave unchanged. */
  selectedLibraryIds?: string[];
}

export interface ConsumeV3Options {
  after: number;
  onEvent: (event: ValidatedChatStreamEvent) => void;
  signal?: AbortSignal;
}

export type V3Terminal =
  | { kind: 'done'; event: ValidatedChatStreamEvent; after: number }
  | { kind: 'error'; event: ValidatedChatStreamEvent; after: number }
  | { kind: 'detached'; after: number };

interface ChatStreamV3TransportOptions {
  fetch?: typeof fetch;
  baseUrl?: string;
  getAuthToken?: () => string | null;
  getSpaceId?: () => string | null;
  sleep?: (delayMs: number) => Promise<void>;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SAFE_CODE = /^[a-z0-9_]{1,64}$/;
const RECONNECT_DELAYS = [1_000, 2_000, 4_000, 8_000] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isSafeRelativeApiUrl(value: unknown): value is string {
  return typeof value === 'string'
    && value.startsWith('/api/')
    && !value.startsWith('//')
    && !value.includes('\\');
}

function validateAccepted(
  value: unknown,
  expectedSessionId: string,
  expectedClientRequestId: string,
): AcceptedChatTurnV3 {
  if (!isRecord(value)
    || typeof value.turn_id !== 'string'
    || !UUID.test(value.turn_id)
    || value.session_id !== expectedSessionId
    || value.client_request_id !== expectedClientRequestId
    || (value.status !== 'accepted' && value.status !== 'completed')
    || !isSafeRelativeApiUrl(value.events_url)
    || !isSafeRelativeApiUrl(value.status_url)
    || !isSafeRelativeApiUrl(value.cancel_url)) {
    throw new Error('invalid_chat_v3_acceptance');
  }
  return value as unknown as AcceptedChatTurnV3;
}

async function safeJson(response: Response): Promise<Record<string, unknown>> {
  try {
    const value = await response.json();
    return isRecord(value) ? value : {};
  } catch {
    return {};
  }
}

export class ChatStreamV3HttpError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfterSeconds: number | null;

  constructor(status: number, code: string, retryAfterSeconds: number | null = null) {
    super(code);
    this.name = 'ChatStreamV3HttpError';
    this.status = status;
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export class ChatStreamV3Transport {
  private readonly request: typeof fetch;
  private readonly baseUrl: string;
  private readonly token: () => string | null;
  private readonly spaceId: () => string | null;
  private readonly sleep: (delayMs: number) => Promise<void>;
  private readonly consumers = new Map<string, AbortController>();

  constructor(options: ChatStreamV3TransportOptions = {}) {
    this.request = options.fetch ?? ((input, init) => fetch(input, init));
    this.baseUrl = (options.baseUrl ?? '/api/v1').replace(/\/$/, '');
    this.token = options.getAuthToken ?? getAuthToken;
    this.spaceId = options.getSpaceId ?? getActiveSpaceId;
    this.sleep = options.sleep ?? ((delayMs) => new Promise((resolve) => setTimeout(resolve, delayMs)));
  }

  async accept(request: V3SendRequest, signal?: AbortSignal): Promise<AcceptedChatTurnV3> {
    const url = request.regenerateMessageId
      ? `${this.baseUrl}/chat/messages/${request.regenerateMessageId}/regenerate/`
      : `${this.baseUrl}/chat/sessions/${request.sessionId}/send/`;
    const response = await this.request(url, {
      method: 'POST',
      headers: this.headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        content: request.content,
        client_request_id: request.clientRequestId,
        answer_mode: request.answerMode,
        thinking_enabled: request.thinkingEnabled,
        protocol_version: 3,
        ...(request.selectedLibraryIds !== undefined
          ? { selected_library_ids: request.selectedLibraryIds }
          : {}),
      }),
      signal,
    });
    if (response.status === 429) {
      const data = await safeJson(response);
      const bodyRetry = data.retry_after_seconds;
      const headerRetry = Number(response.headers.get('Retry-After'));
      const retryAfterSeconds = typeof bodyRetry === 'number' && Number.isFinite(bodyRetry)
        ? Math.max(0, Math.floor(bodyRetry))
        : Number.isFinite(headerRetry) ? Math.max(0, Math.floor(headerRetry)) : null;
      const code = data.code === 'generation_capacity_reached'
        ? data.code
        : 'generation_capacity_reached';
      throw new ChatStreamV3HttpError(429, code, retryAfterSeconds);
    }
    if (response.status !== 202) {
      const data = await safeJson(response);
      const code = typeof data.code === 'string' && SAFE_CODE.test(data.code)
        ? data.code
        : `http_${response.status}`;
      throw new ChatStreamV3HttpError(response.status, code);
    }
    return validateAccepted(
      await safeJson(response),
      request.sessionId,
      request.clientRequestId,
    );
  }

  async consume(turn: AcceptedChatTurnV3, options: ConsumeV3Options): Promise<V3Terminal> {
    this.detach(turn.session_id);
    const controller = new AbortController();
    this.consumers.set(turn.session_id, controller);
    const abortFromOwner = () => controller.abort();
    options.signal?.addEventListener('abort', abortFromOwner, { once: true });
    if (options.signal?.aborted) controller.abort();
    let cursor = Math.max(0, Math.floor(options.after));
    let reconnectIndex = 0;

    try {
      while (!controller.signal.aborted) {
        const url = `${turn.events_url}${turn.events_url.includes('?') ? '&' : '?'}after=${cursor}`;
        let response: Response;
        try {
          response = await this.request(url, {
            method: 'GET',
            headers: this.headers({
              Accept: 'text/event-stream',
              'Last-Event-ID': String(cursor),
            }),
            signal: controller.signal,
          });
        } catch (error) {
          if (controller.signal.aborted) return { kind: 'detached', after: cursor };
          if (reconnectIndex >= RECONNECT_DELAYS.length) throw error;
          await this.sleep(RECONNECT_DELAYS[reconnectIndex]);
          reconnectIndex += 1;
          continue;
        }
        if (response.status === 401 || response.status === 403) {
          throw new ChatStreamV3HttpError(response.status, 'stream_access_revoked');
        }
        if (!response.ok || !response.body) {
          if (reconnectIndex >= RECONNECT_DELAYS.length) {
            throw new ChatStreamV3HttpError(response.status, `http_${response.status}`);
          }
          await this.sleep(RECONNECT_DELAYS[reconnectIndex]);
          reconnectIndex += 1;
          continue;
        }
        validateRecoveryResponseIdentity(response.headers, turn.turn_id, turn.client_request_id);

        const reader = response.body.getReader();
        const cancelReader = () => { void reader.cancel(); };
        controller.signal.addEventListener('abort', cancelReader, { once: true });
        const decoder = new TextDecoder();
        const parser = new StoreSSEDecoder();
        try {
          while (!controller.signal.aborted) {
            const { done, value } = await reader.read();
            const messages = done
              ? [...parser.feed(decoder.decode()), ...parser.end()]
              : parser.feed(decoder.decode(value, { stream: true }));
            for (const message of messages) {
              const event = validateChatStreamMessage(message, {
                protocolVersion: 3,
                expectedSessionId: turn.session_id,
                expectedTurnId: turn.turn_id,
                expectedClientRequestId: turn.client_request_id,
              });
              const sequence = event.sequence!;
              if (sequence <= cursor) continue;
              cursor = sequence;
              options.onEvent(event);
              if (event.name === 'done') return { kind: 'done', event, after: cursor };
              if (event.name === 'error') return { kind: 'error', event, after: cursor };
            }
            if (done) break;
          }
        } finally {
          controller.signal.removeEventListener('abort', cancelReader);
          if (controller.signal.aborted) await reader.cancel().catch(() => undefined);
          else reader.releaseLock();
        }
        if (controller.signal.aborted) return { kind: 'detached', after: cursor };
        if (reconnectIndex >= RECONNECT_DELAYS.length) {
          throw new ChatStreamV3HttpError(0, 'stream_reconnect_exhausted');
        }
        await this.sleep(RECONNECT_DELAYS[reconnectIndex]);
        reconnectIndex += 1;
      }
      return { kind: 'detached', after: cursor };
    } catch (error) {
      if (controller.signal.aborted) return { kind: 'detached', after: cursor };
      throw error;
    } finally {
      options.signal?.removeEventListener('abort', abortFromOwner);
      if (this.consumers.get(turn.session_id) === controller) {
        this.consumers.delete(turn.session_id);
      }
    }
  }

  async cancel(turn: AcceptedChatTurnV3): Promise<void> {
    const response = await this.request(turn.cancel_url, {
      method: 'POST',
      headers: this.headers({ 'Content-Type': 'application/json' }),
      body: '{}',
    });
    if (response.status !== 202) {
      throw new ChatStreamV3HttpError(response.status, `http_${response.status}`);
    }
  }

  detach(sessionId: string): void {
    this.consumers.get(sessionId)?.abort();
    this.consumers.delete(sessionId);
  }

  private headers(extra: Record<string, string>): Record<string, string> {
    const headers = { ...extra };
    const token = this.token();
    const spaceId = this.spaceId();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (spaceId) headers['X-Space-Id'] = spaceId;
    return headers;
  }
}
