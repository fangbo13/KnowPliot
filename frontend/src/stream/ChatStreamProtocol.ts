import type { SSEMessage } from './SSEParser';

export type ChatProtocolVersion = 1 | 2 | 3;

export interface ChatStreamValidationContext {
  protocolVersion: ChatProtocolVersion | null;
  expectedSessionId: string;
  expectedTurnId?: string | null;
  expectedClientRequestId: string;
}

/** Safe, server-owned execution fields carried by v2 meta/replay events. */
export interface ChatExecutionSnapshotPayload {
  requested_answer_mode: 'fast' | 'deep';
  answer_mode: 'fast' | 'deep';
  requested_thinking_enabled: boolean;
  thinking_enabled: boolean;
  thinking_snapshot_known: boolean;
  thinking_budget: number | null;
  model_id: string;
  policy_fallback_code: string;
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
const SAFE_PHASES = new Set([
  'accepted',
  'queued',
  'retrieving',
  'reasoning',
  'answering',
  'saving',
  'searching',
  'generating',
  'finalizing',
]);
const FORBIDDEN_REASONING_FIELDS = new Set([
  'reasoning',
  'reasoning_content',
  'chain_of_thought',
  'raw_reasoning',
]);
const SNAPSHOT_FIELDS = new Set([
  'requested_answer_mode',
  'answer_mode',
  'requested_thinking_enabled',
  'thinking_enabled',
  'thinking_snapshot_known',
  'thinking_budget',
  'model_id',
  'policy_fallback_code',
]);

function invalid(): never {
  throw new InvalidChatStreamEventError();
}

function isRecord(value: unknown): value is Record<string, any> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function parseData(data: string): any {
  try {
    const parsed = JSON.parse(data);
    rejectForbiddenReasoningFields(parsed);
    return parsed;
  } catch {
    return invalid();
  }
}

function rejectForbiddenReasoningFields(value: unknown): void {
  if (Array.isArray(value)) {
    value.forEach(rejectForbiddenReasoningFields);
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (FORBIDDEN_REASONING_FIELDS.has(key.toLowerCase())) invalid();
    rejectForbiddenReasoningFields(child);
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

function validateExecutionSnapshot(data: unknown): asserts data is ChatExecutionSnapshotPayload {
  if (!isRecord(data)
    || (data.requested_answer_mode !== 'fast' && data.requested_answer_mode !== 'deep')
    || (data.answer_mode !== 'fast' && data.answer_mode !== 'deep')
    || typeof data.requested_thinking_enabled !== 'boolean'
    || typeof data.thinking_enabled !== 'boolean'
    || typeof data.thinking_snapshot_known !== 'boolean'
    || (data.thinking_budget !== null
      && (typeof data.thinking_budget !== 'number'
        || !Number.isSafeInteger(data.thinking_budget)
        || data.thinking_budget < 1
        || data.thinking_budget > 32768))
    || typeof data.model_id !== 'string'
    || data.model_id.length > 160
    || typeof data.policy_fallback_code !== 'string'
    || (data.policy_fallback_code !== '' && !SAFE_CODE.test(data.policy_fallback_code))
    || (!data.thinking_snapshot_known && data.thinking_budget !== null)
    || (data.thinking_snapshot_known && !data.thinking_enabled && data.thinking_budget !== null)
    || (data.thinking_snapshot_known && data.thinking_enabled && data.thinking_budget === null)) invalid();
}

function validateOptionalExecutionSnapshot(data: Record<string, any>): void {
  const nested = data.execution_snapshot;
  if (nested !== undefined) validateExecutionSnapshot(nested);
  const hasFlatSnapshotField = [...SNAPSHOT_FIELDS].some((field) => field in data);
  if (hasFlatSnapshotField) validateExecutionSnapshot(data);
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

function validateV2(
  name: string,
  data: any,
  context: ChatStreamValidationContext,
  expectedProtocol: 2 | 3 = 2,
): void {
  if (!V2_EVENTS.has(name)) invalid();
  if (name === 'meta') {
    if (!isRecord(data)
      || data.protocol_version !== expectedProtocol
      || !isUuid(data.turn_id)
      || !isUuid(data.session_id)
      || !isUuid(data.client_request_id)
      || data.session_id !== context.expectedSessionId
      || data.client_request_id !== context.expectedClientRequestId
      || (context.expectedTurnId && data.turn_id !== context.expectedTurnId)) invalid();
    validateOptionalExecutionSnapshot(data);
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
  if (protocolVersion >= 2 && !message.hasExplicitId) invalid();
  const sequence = protocolVersion >= 2
    ? sequenceOf(message.id)
    : message.id === null ? null : sequenceOf(message.id);
  const data = parseData(message.data);
  if (protocolVersion === 2 || protocolVersion === 3) {
    validateV2(message.event, data, context, protocolVersion);
  }
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
