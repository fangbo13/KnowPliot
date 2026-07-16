import type { SSEMessage } from './SSEParser';

export type ChatProtocolVersion = 1 | 2;

export interface ChatStreamValidationContext {
  protocolVersion: ChatProtocolVersion | null;
  expectedSessionId: string;
  expectedTurnId?: string | null;
  expectedClientRequestId: string;
}

export interface ValidatedChatStreamEvent {
  name: string;
  data: any;
  sequence: number | null;
  protocolVersion: ChatProtocolVersion;
}

export class InvalidChatStreamEventError extends Error {
  constructor() {
    super('invalid_chat_stream_event');
    this.name = 'InvalidChatStreamEventError';
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SAFE_CODE = /^[a-z0-9_]{1,64}$/;
const V1_EVENTS = new Set(['token', 'citations', 'quality', 'done', 'error']);
const V2_EVENTS = new Set(['meta', 'phase', 'answer_delta', 'citations', 'quality', 'usage', 'done', 'error']);
const SAFE_PHASES = new Set(['accepted', 'retrieving', 'reasoning', 'answering', 'saving']);

function invalid(): never {
  throw new InvalidChatStreamEventError();
}

function isRecord(value: unknown): value is Record<string, any> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function parseData(data: string): any {
  try {
    return JSON.parse(data);
  } catch {
    return invalid();
  }
}

function sequenceOf(id: string | null): number {
  if (!id || !/^\d+$/.test(id)) return invalid();
  const sequence = Number(id);
  if (!Number.isSafeInteger(sequence) || sequence <= 0) return invalid();
  return sequence;
}

function isUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value);
}

function validateCitations(data: unknown): void {
  if (!Array.isArray(data)) invalid();
  for (const citation of data) {
    if (!isRecord(citation)
      || typeof citation.document_id !== 'string'
      || typeof citation.document_title !== 'string'
      || typeof citation.score !== 'number'
      || typeof citation.quoted_text !== 'string'
      || (citation.page_number != null && typeof citation.page_number !== 'number')) invalid();
  }
}

function validateQuality(data: unknown): void {
  if (!isRecord(data)
    || (data.score != null && typeof data.score !== 'number')
    || (data.confidence != null && typeof data.confidence !== 'string')
    || (data.needs_human_review != null && typeof data.needs_human_review !== 'boolean')
    || (data.retrieval_mode != null && typeof data.retrieval_mode !== 'string')
    || (data.retrieval_latency_ms != null && typeof data.retrieval_latency_ms !== 'number')) invalid();
}

function validateV1(name: string, data: any, context: ChatStreamValidationContext): void {
  if (!V1_EVENTS.has(name)) invalid();
  if (name === 'token' && (!isRecord(data) || typeof data.token !== 'string')) invalid();
  if (name === 'citations') validateCitations(data);
  if (name === 'quality') validateQuality(data);
  if (name === 'error' && !isRecord(data)) invalid();
  if (name === 'done') {
    if (!isRecord(data)
      || !isUuid(data.message_id)
      || data.session_id !== context.expectedSessionId
      || (data.turn_id != null && data.turn_id !== context.expectedTurnId)
      || (data.client_request_id != null && data.client_request_id !== context.expectedClientRequestId)) invalid();
  }
}

function validateV2(name: string, data: any, context: ChatStreamValidationContext): void {
  if (!V2_EVENTS.has(name)) invalid();
  if (name === 'meta') {
    if (!isRecord(data)
      || data.protocol_version !== 2
      || !isUuid(data.turn_id)
      || !isUuid(data.session_id)
      || !isUuid(data.client_request_id)
      || data.session_id !== context.expectedSessionId
      || data.client_request_id !== context.expectedClientRequestId
      || (context.expectedTurnId && data.turn_id !== context.expectedTurnId)) invalid();
  } else if (name === 'phase') {
    if (!isRecord(data) || !SAFE_PHASES.has(data.phase)) invalid();
  } else if (name === 'answer_delta') {
    if (!isRecord(data) || typeof data.text !== 'string') invalid();
  } else if (name === 'citations') {
    validateCitations(data);
  } else if (name === 'quality') {
    validateQuality(data);
  } else if (name === 'usage') {
    if (!isRecord(data)
      || (data.output_tokens != null && typeof data.output_tokens !== 'number')
      || (data.latency_ms != null && typeof data.latency_ms !== 'number')) invalid();
  } else if (name === 'error') {
    if (!isRecord(data) || typeof data.code !== 'string' || !SAFE_CODE.test(data.code)
      || typeof data.retryable !== 'boolean') invalid();
  } else if (name === 'done') {
    if (!isRecord(data)
      || !isUuid(data.message_id)
      || !isUuid(data.session_id)
      || !isUuid(data.turn_id)
      || !isUuid(data.client_request_id)
      || data.session_id !== context.expectedSessionId
      || data.turn_id !== context.expectedTurnId
      || data.client_request_id !== context.expectedClientRequestId) invalid();
  }
}

export function validateChatStreamMessage(
  message: SSEMessage,
  context: ChatStreamValidationContext,
): ValidatedChatStreamEvent {
  const protocolVersion = context.protocolVersion
    ?? (message.event === 'meta' ? 2 : message.id === null ? 1 : invalid());
  if (protocolVersion === 2 && !message.hasExplicitId) invalid();
  const sequence = protocolVersion === 2
    ? sequenceOf(message.id)
    : message.id === null ? null : sequenceOf(message.id);
  const data = parseData(message.data);
  if (protocolVersion === 2) validateV2(message.event, data, context);
  else validateV1(message.event, data, context);
  return { name: message.event, data, sequence, protocolVersion };
}

export function validateRecoveryResponseIdentity(
  headers: Headers,
  expectedTurnId: string,
  expectedClientRequestId: string,
): { turnId: string; clientRequestId: string } {
  const turnId = headers.get('X-Chat-Turn-Id');
  const clientRequestId = headers.get('X-Chat-Client-Request-Id');
  if (turnId !== expectedTurnId || clientRequestId !== expectedClientRequestId) invalid();
  return { turnId, clientRequestId };
}
