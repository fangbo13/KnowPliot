/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { create } from 'zustand';
import { chatApi, type ChatMessageRecord } from '../api/chat';
import { getAuthToken, getActiveSpaceId } from '../api/client';
import {
  createStreamAbortController,
  abortActiveStream,
  clearStreamOnComplete,
  hasActiveStream,
} from '../stream/StreamLifecycleManager';
import { initTokenBatcher, appendToken, flushImmediate, resetTokenBatcher } from '../stream/TokenBatchRenderer';
import { StoreSSEDecoder } from '../stream/SSEParser';
import {
  validateChatStreamMessage,
  validateRecoveryResponseIdentity,
  type ValidatedChatStreamEvent,
} from '../stream/ChatStreamProtocol';
import {
  ChatStreamV3HttpError,
  ChatStreamV3Transport,
  type AcceptedChatTurnV3,
} from '../stream/ChatStreamV3Transport';
// V4.0 DEFECT-008: BroadcastChannel cross-tab sync
import { broadcastSessionSwitch } from '../sync/crossTabSync';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: Citation[];
  confidenceScore?: number | null;
  confidenceLabel?: 'high' | 'medium' | 'low' | 'insufficient' | '';
  needsHumanReview?: boolean;
  retrievalMode?: string;
  retrievalLatencyMs?: number | null;
  /** Server-owned execution details for assistant history messages only. */
  executionSnapshot?: ChatExecutionSnapshot | null;
  execution_snapshot?: ChatExecutionSnapshot | null;
  createdAt: string;
}

export interface QualityData {
  confidence: Message['confidenceLabel'];
  score: number;
  needs_human_review: boolean;
  retrieval_mode: string;
  retrieval_latency_ms: number;
}

export interface Citation {
  source_id?: string;
  source_url?: string | null;
  document_id: string;
  document_title: string;
  page_number?: number;
  // KB/RAG audit spec P2 §A7: heading path from structure-aware chunking.
  section?: string | null;
  score: number;
  snippet?: string;
  quoted_text: string;
  // Spec §3/§4 L5: version watermark + stale badge on citation cards
  version?: number;
  updated_by?: string | null;
  updated_at?: string | null;
  stale?: boolean;
  // KB optimization spec §3.3: reference-library provenance badge
  source_library?: string | null;
}

export interface ChatSession {
  id: string;
  title: string;
  is_active: boolean;
  isPinned: boolean;
  updatedAt: string;
  recoveryState?: 'partial' | 'recovering' | 'recovered' | 'failed' | 'terminal';
}

// Words/phrases that don't make good titles
const MEANINGLESS_WORDS = new Set([
  'test', 'test test', 'hello', 'hi', 'hey', '你好', '你好吗', '嗨',
  '1', 'a', 'the', 'is', 'it', '?', '？', '。', 'test123', 'asd',
  'asdf', '123', 'abc', 'tt', 'xx',
]);

// Generate a meaningful session title from user's first message
function generateSmartTitle(content: string): string {
  const trimmed = content.trim();
  if (!trimmed) return '新对话';

  // Check if the content is meaningless
  const lower = trimmed.toLowerCase();
  if (MEANINGLESS_WORDS.has(lower)) {
    return '新对话';
  }

  // Remove trailing punctuation for cleaner titles
  let title = trimmed.replace(/[。！？.!?]+$/, '');

  // Extract meaningful content: prefer question-like phrases
  // If it's a question, take the core part (before the question mark)
  if (title.includes('?') || title.includes('？')) {
    const qIndex = Math.max(title.indexOf('?'), title.indexOf('？'));
    const core = title.substring(0, qIndex).trim();
    if (core.length >= 2) {
      title = core;
    }
  }

  // Cap title length, prefer word boundaries
  const MAX_LEN = 30;
  if (title.length > MAX_LEN) {
    // For CJK text, just truncate at MAX_LEN
    const isCJK = /[一-鿿]/.test(title);
    if (isCJK) {
      title = title.substring(0, MAX_LEN) + '…';
    } else {
      // For English, truncate at word boundary
      const truncated = title.substring(0, MAX_LEN);
      const lastSpace = truncated.lastIndexOf(' ');
      title = lastSpace > MAX_LEN * 0.6 ? truncated.substring(0, lastSpace) + '…' : truncated + '…';
    }
  }

  // If the title is too short after cleaning, fallback
  if (title.length < 2) return '新对话';

  return title;
}

// V3.5: Unified stream state machine — replaces isStreaming + thinkingPhase + connectionStatus
export type StreamPhase = 'idle' | 'connecting' | 'searching' | 'streaming' | 'completing' | 'error';
export type StreamRecoveryState = 'idle' | 'available' | 'recovering' | 'recovered' | 'failed';
export type AnswerMode = 'fast' | 'deep';
export type SafeProcessingPhase = 'accepted' | 'searching' | 'generating' | 'thinking' | 'finalizing';

/**
 * The server-owned execution snapshot attached to a Turn.  The wire contract
 * intentionally keeps the canonical snake_case names so the object can be
 * passed through meta/replay/status/history without inventing client policy.
 * `thinking_snapshot_known` is the authority for interpreting the boolean and
 * budget sentinels on migrated historical Turns.
 */
export interface ChatExecutionSnapshot {
  requested_answer_mode: AnswerMode;
  answer_mode: AnswerMode;
  requested_thinking_enabled: boolean;
  thinking_enabled: boolean;
  thinking_snapshot_known: boolean;
  thinking_budget: number | null;
  model_id: string;
  policy_fallback_code: string;
  /** Optional normalized aliases for component/test ergonomics. */
  requestedAnswerMode?: AnswerMode;
  effectiveAnswerMode?: AnswerMode;
  requestedThinkingEnabled?: boolean;
  thinkingEnabled?: boolean;
  thinkingSnapshotKnown?: boolean;
  thinkingBudget?: number | null;
  modelId?: string;
  policyFallbackCode?: string;
}

/** Alias used by consumers that call the object an effective snapshot. */
export type ExecutionSnapshot = ChatExecutionSnapshot;

/** Safe marker used when an older assistant row has no provable snapshot. */
export const LEGACY_UNKNOWN_EXECUTION_SNAPSHOT: ChatExecutionSnapshot = Object.freeze({
  requested_answer_mode: 'fast',
  answer_mode: 'fast',
  requested_thinking_enabled: false,
  thinking_enabled: false,
  thinking_snapshot_known: false,
  thinking_budget: null,
  model_id: '',
  policy_fallback_code: 'legacy_thinking_unknown',
});

export interface ProcessingTimings {
  connectionMs?: number;
  firstAnswerMs?: number;
  totalMs?: number;
}

export interface SendMessageOptions {
  answerMode?: AnswerMode;
  /** Result of the current rollout flag + server capability decision. */
  canUseDeep?: boolean;
  /** Explicit independent-thinking preference for this logical question. */
  thinkingEnabled?: boolean;
  /** Result of the current rollout flag + server capability decision. */
  canUseThinking?: boolean;
  /** Explicit user retry of the current failed deep Turn; never inferred. */
  retryClientRequestId?: string;
  /** Persisted assistant message whose answer version should be regenerated. */
  regenerateMessageId?: string;
}

export const CHAT_STREAM_TIMEOUTS = Object.freeze({
  connectionMs: 20_000,
  idleMs: 45_000,
  totalMs: 180_000,
  recoveryRequestMs: 5_000,
});

export interface SessionTurnState {
  phase: StreamPhase;
  safePhase?: SafeProcessingPhase | null;
  isLocked: boolean;
  answerMode?: AnswerMode;
  /** Requested mode retained even when server policy falls back. */
  requestedAnswerMode?: AnswerMode;
  /** Effective mode alias for read-only processing/history consumers. */
  effectiveAnswerMode?: AnswerMode;
  /** Wire-name aliases retained for stream/status contract consumers. */
  requested_answer_mode?: AnswerMode;
  effective_answer_mode?: AnswerMode;
  requestedThinkingEnabled?: boolean;
  thinkingEnabled?: boolean;
  thinkingSnapshotKnown?: boolean;
  thinkingBudget?: number | null;
  modelId?: string | null;
  policyFallbackCode?: string;
  requested_thinking_enabled?: boolean;
  thinking_enabled?: boolean;
  thinking_snapshot_known?: boolean;
  thinking_budget?: number | null;
  model_id?: string | null;
  policy_fallback_code?: string;
  executionSnapshot?: ChatExecutionSnapshot | null;
  effectiveSnapshot?: ChatExecutionSnapshot | null;
  content: string;
  citations: Citation[];
  quality: QualityData | null;
  error: string | null;
  aiStatusText: string | null;
  generationId: string | null;
  clientRequestId?: string | null;
  turnId?: string | null;
  lastEventSeq?: number;
  protocolVersion?: 1 | 2 | 3 | null;
  v3Turn?: AcceptedChatTurnV3 | null;
  capacityRetryAfterSeconds?: number | null;
  capacityRetryAtMs?: number | null;
  recoveryState?: StreamRecoveryState;
  timings?: ProcessingTimings;
  startedAtMs?: number | null;
}

interface ChatState {
  sessions: ChatSession[];
  sessionNextCursor: string | null;
  activeSessionId: string | null;
  messages: Message[];
  messageNextCursor: string | null;
  // V3.5: allMessages holds full history for sliding window; messages is the visible slice
  allMessages: Message[];
  visibleRoundCount: number;
  hasOlderMessages: boolean;
  // V3.6 MED-003: Cached round count — avoids O(n) recomputation per message
  totalRoundCount: number;
  turnsBySession: Record<string, SessionTurnState>;
  localPartialsBySession: Record<string, Message[]>;
  messageCacheBySession: Record<string, Message[]>;
  // V3.5: Unified stream phase replaces three separate fields
  streamPhase: StreamPhase;
  // V4.6: Track which session owns the stream so streaming UI only shows for matching session.
  // When user switches away during streaming, the stream continues in background; when they
  // switch back, loadMessages fetches the completed response from the server.
  streamingSessionId: string | null;
  streamContent: string;
  citations: Citation[];
  streamQuality: QualityData | null;
  isLoadingMessages: boolean;
  sendError: string | null;
  // V3.5: Send lock to prevent double-send during async gap
  isSendLocked: boolean;
  // V3.6 HIGH-002: Flag to refresh session list only after new session creation
  _pendingSessionRefresh: boolean;
  aiStatusText: string | null;

  // Actions
  setActiveSession: (id: string) => void;
  resetSession: () => void;
  addMessage: (message: Message) => void;
  updateStreamContent: (content: string) => void;
  setStreamCitations: (citations: Citation[]) => void;
  setSendError: (error: string | null) => void;
  setStreamPhase: (phase: StreamPhase) => void;
  lockSend: () => void;
  unlockSend: () => void;
  abortSessionStream: (sessionId: string) => void;
  removeSessionState: (sessionId: string) => void;
  dismissSessionError: (sessionId: string) => void;
  loadSessions: () => Promise<void>;
  loadMoreSessions: () => Promise<void>;
  loadMessages: (sessionId: string) => Promise<void>;
  loadOlderMessages: () => Promise<void>;
  sendMessage: (content: string, options?: SendMessageOptions) => Promise<void>;
  finishStreamingMessage: (messageId: string, sessionId: string, generationId?: string) => void;
  loadOlderRounds: (count: number) => void;
  setAIStatusText: (text: string | null) => void;
}

// V3.5: Sliding window helpers
function computeRounds(messages: Message[]): { id: string; messages: Message[] }[] {
  const rounds: { id: string; messages: Message[] }[] = [];
  let currentRoundMessages: Message[] = [];
  let roundIndex = 0;

  for (const msg of messages) {
    currentRoundMessages.push(msg);
    // A round ends when we see an assistant message after a user message
    if (msg.role === 'assistant' && currentRoundMessages.some(m => m.role === 'user')) {
      rounds.push({ id: `round-${roundIndex}`, messages: [...currentRoundMessages] });
      currentRoundMessages = [];
      roundIndex++;
    }
  }

  // If there are leftover messages (e.g., a user message without assistant response yet)
  if (currentRoundMessages.length > 0) {
    rounds.push({ id: `round-${roundIndex}`, messages: [...currentRoundMessages] });
  }

  return rounds;
}

function extractVisibleMessages(rounds: { id: string; messages: Message[] }[], visibleCount: number): Message[] {
  // Show the last N rounds
  const startIdx = Math.max(0, rounds.length - visibleCount);
  return rounds.slice(startIdx).flatMap(r => r.messages);
}

function idleTurn(): SessionTurnState {
  return {
    phase: 'idle',
    safePhase: null,
    isLocked: false,
    answerMode: 'fast',
    requestedAnswerMode: 'fast',
    effectiveAnswerMode: 'fast',
    requested_answer_mode: 'fast',
    effective_answer_mode: 'fast',
    requestedThinkingEnabled: false,
    thinkingEnabled: false,
    thinkingSnapshotKnown: true,
    thinkingBudget: null,
    modelId: null,
    policyFallbackCode: '',
    requested_thinking_enabled: false,
    thinking_enabled: false,
    thinking_snapshot_known: true,
    thinking_budget: null,
    model_id: null,
    policy_fallback_code: '',
    executionSnapshot: null,
    effectiveSnapshot: null,
    content: '',
    citations: [],
    quality: null,
    error: null,
    aiStatusText: null,
    generationId: null,
    clientRequestId: null,
    turnId: null,
    lastEventSeq: 0,
    protocolVersion: null,
    v3Turn: null,
    capacityRetryAfterSeconds: null,
    capacityRetryAtMs: null,
    recoveryState: 'idle',
    timings: {},
    startedAtMs: null,
  };
}

export function mapServerPhaseForUi(phase: unknown): {
  streamPhase: StreamPhase;
  safePhase: SafeProcessingPhase;
} {
  if (phase === 'accepted' || phase === 'queued') {
    return { streamPhase: 'connecting', safePhase: 'accepted' };
  }
  if (phase === 'retrieving' || phase === 'searching') {
    return { streamPhase: 'searching', safePhase: 'searching' };
  }
  if (phase === 'thinking') {
    return { streamPhase: 'streaming', safePhase: 'thinking' };
  }
  if (phase === 'saving' || phase === 'finalizing') {
    return { streamPhase: 'completing', safePhase: 'finalizing' };
  }
  return { streamPhase: 'streaming', safePhase: 'generating' };
}

function elapsedMs(startedAtMs: number | null | undefined): number | undefined {
  if (typeof startedAtMs !== 'number') return undefined;
  return Math.max(0, Date.now() - startedAtMs);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isAnswerMode(value: unknown): value is AnswerMode {
  return value === 'fast' || value === 'deep';
}

/**
 * Narrow and normalize a snapshot received from a server event/history row.
 * Unknown or malformed snapshots are ignored rather than allowing untrusted
 * execution fields to become client authority.  Legacy rows are accepted when
 * all fields are present; their `thinking_snapshot_known=false` marker is
 * preserved for the UI to render as `legacy/unknown`.
 */
export function parseChatExecutionSnapshot(value: unknown): ChatExecutionSnapshot | null {
  if (!isRecord(value)) return null;
  const field = (snake: string, camel: string): unknown => (
    value[snake] !== undefined ? value[snake] : value[camel]
  );
  const requestedMode = field('requested_answer_mode', 'requestedAnswerMode');
  const effectiveMode = field('answer_mode', 'effectiveAnswerMode');
  const requestedThinking = field('requested_thinking_enabled', 'requestedThinkingEnabled');
  const effectiveThinking = field('thinking_enabled', 'thinkingEnabled');
  const known = field('thinking_snapshot_known', 'thinkingSnapshotKnown');
  const budget = field('thinking_budget', 'thinkingBudget');
  const modelId = field('model_id', 'modelId');
  const fallback = field('policy_fallback_code', 'policyFallbackCode');

  if (!isAnswerMode(requestedMode) || !isAnswerMode(effectiveMode)
    || typeof requestedThinking !== 'boolean'
    || typeof effectiveThinking !== 'boolean'
    || typeof known !== 'boolean'
    || (budget !== null && (typeof budget !== 'number'
      || !Number.isSafeInteger(budget) || budget < 1 || budget > 32768))
    || typeof modelId !== 'string'
    || modelId.length > 160
    || typeof fallback !== 'string'
    || fallback.length > 64
    || !/^[a-z0-9_]*$/.test(fallback)
    || (!known && budget !== null)
    || (known && !effectiveThinking && budget !== null)
    || (known && effectiveThinking && budget === null)) {
    return null;
  }

  return {
    requested_answer_mode: requestedMode,
    answer_mode: effectiveMode,
    requested_thinking_enabled: requestedThinking,
    thinking_enabled: effectiveThinking,
    thinking_snapshot_known: known,
    thinking_budget: budget,
    model_id: modelId,
    policy_fallback_code: fallback,
  };
}

export const normalizeExecutionSnapshot = parseChatExecutionSnapshot;

/** Extract either the flat SSE fields or a nested history snapshot. */
function snapshotFromPayload(value: unknown): ChatExecutionSnapshot | null {
  if (!isRecord(value)) return null;
  const nested = value.execution_snapshot;
  return parseChatExecutionSnapshot(nested) ?? parseChatExecutionSnapshot(value);
}

function snapshotTurnPatch(snapshot: ChatExecutionSnapshot): Partial<SessionTurnState> {
  return {
    executionSnapshot: snapshot,
    effectiveSnapshot: snapshot,
    requestedAnswerMode: snapshot.requested_answer_mode,
    answerMode: snapshot.answer_mode,
    effectiveAnswerMode: snapshot.answer_mode,
    requested_answer_mode: snapshot.requested_answer_mode,
    effective_answer_mode: snapshot.answer_mode,
    requestedThinkingEnabled: snapshot.requested_thinking_enabled,
    thinkingEnabled: snapshot.thinking_enabled,
    thinkingSnapshotKnown: snapshot.thinking_snapshot_known,
    thinkingBudget: snapshot.thinking_budget,
    modelId: snapshot.model_id,
    policyFallbackCode: snapshot.policy_fallback_code,
    requested_thinking_enabled: snapshot.requested_thinking_enabled,
    thinking_enabled: snapshot.thinking_enabled,
    thinking_snapshot_known: snapshot.thinking_snapshot_known,
    thinking_budget: snapshot.thinking_budget,
    model_id: snapshot.model_id,
    policy_fallback_code: snapshot.policy_fallback_code,
  };
}

function legacyMirror(turn: SessionTurnState, sessionId: string | null): Partial<ChatState> {
  return {
    streamPhase: turn.phase,
    streamingSessionId: turn.isLocked ? sessionId : null,
    streamContent: turn.content,
    citations: turn.citations,
    streamQuality: turn.quality,
    sendError: turn.error,
    isSendLocked: turn.isLocked,
    aiStatusText: turn.aiStatusText,
  };
}

function withTurnUpdate(
  state: ChatState,
  sessionId: string,
  generationId: string | null,
  patch: Partial<SessionTurnState>,
): Partial<ChatState> {
  const current = state.turnsBySession[sessionId] ?? idleTurn();
  if (generationId !== null && current.generationId !== generationId) return {};
  const next = { ...current, ...patch };
  return {
    turnsBySession: { ...state.turnsBySession, [sessionId]: next },
    ...(state.activeSessionId === sessionId ? legacyMirror(next, sessionId) : {}),
  };
}

function mapApiMessage(message: ChatMessageRecord): Message {
  const executionSnapshot = message.role === 'assistant'
    ? snapshotFromPayload(message.execution_snapshot ?? message.executionSnapshot)
      ?? LEGACY_UNKNOWN_EXECUTION_SNAPSHOT
    : null;
  return {
    id: message.id || crypto.randomUUID(),
    role: message.role,
    content: message.content || '',
    citations: message.citations || [],
    confidenceScore: message.confidence_score,
    confidenceLabel: message.confidence_label,
    needsHumanReview: message.needs_human_review,
    retrievalMode: message.retrieval_mode,
    retrievalLatencyMs: message.retrieval_latency_ms,
    ...(executionSnapshot ? {
      executionSnapshot,
      execution_snapshot: executionSnapshot,
    } : {}),
    createdAt: message.created_at || message.createdAt || new Date().toISOString(),
  };
}

function sortMessagesChronologically(messages: Message[]): Message[] {
  return [...messages].sort((a, b) => {
    const aTime = Date.parse(a.createdAt);
    const bTime = Date.parse(b.createdAt);
    return Number.isNaN(aTime) || Number.isNaN(bTime) ? 0 : aTime - bTime;
  });
}

function appendUniqueById<T extends { id: string }>(existing: T[], incoming: T[]): T[] {
  const seen = new Set(existing.map((item) => item.id));
  const merged = [...existing];
  for (const item of incoming) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    merged.push(item);
  }
  return merged;
}

const LOCAL_PARTIAL_RECONCILIATION_WINDOW_MS = 5 * 60 * 1000;

function isReconciledLocalPartial(partial: Message, serverMessage: Message): boolean {
  if (partial.role !== 'assistant' || serverMessage.role !== 'assistant') return false;
  const partialContent = partial.content.trim();
  const serverContent = serverMessage.content.trim();
  if (!partialContent || !serverContent) return false;
  if (!serverContent.startsWith(partialContent) && !partialContent.startsWith(serverContent)) return false;
  const partialTime = Date.parse(partial.createdAt);
  const serverTime = Date.parse(serverMessage.createdAt);
  return Number.isFinite(partialTime)
    && Number.isFinite(serverTime)
    && Math.abs(serverTime - partialTime) <= LOCAL_PARTIAL_RECONCILIATION_WINDOW_MS;
}

const DEFAULT_VISIBLE_ROUNDS = 10;
const chatStreamV3Transport = new ChatStreamV3Transport();
const v3ResumeCallbacks = new Map<string, { generationId: string; resume: () => Promise<void> }>();
const capacityCooldownTimers = new Map<string, ReturnType<typeof setTimeout>>();

function chatStreamV3Enabled(): boolean {
  return String(import.meta.env.VITE_CHAT_STREAM_V3 ?? 'false').toLowerCase() === 'true';
}
// V3.6 MED-001 / V3.7 P1.3: Hard cap on allMessages to prevent unbounded memory growth
// V3.7: Reduced from 500 to 100 — 100 messages ≈ 50 rounds of conversation,
// sufficient for most use cases while keeping JS Heap stable.
// Messages beyond this cap are pruned from front and can be loaded via "load older".
const MAX_ALL_MESSAGES = 100;
let messageLoadSequence = 0;
let messageLoadController: AbortController | null = null;

export const useChatStore = create<ChatState>()((set, get) => ({
  sessions: [],
  sessionNextCursor: null,
  activeSessionId: null,
  messages: [],
  messageNextCursor: null,
  allMessages: [],
  visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
  hasOlderMessages: false,
  totalRoundCount: 0,
  turnsBySession: {},
  localPartialsBySession: {},
  messageCacheBySession: {},
  // V3.5: Unified stream phase (replaces isStreaming/thinkingPhase/connectionStatus)
  streamPhase: 'idle',
  streamingSessionId: null,
  streamContent: '',
  citations: [],
  streamQuality: null,
  isLoadingMessages: false,
  sendError: null,
  isSendLocked: false,
  _pendingSessionRefresh: false,
  aiStatusText: null,

  // Switching views mirrors only the target session's turn. Other sessions keep streaming,
  // and recoverable background partials remain available for a later remount.
  setActiveSession: (id) => {
    if (get().activeSessionId === id) return;

    const previousSessionId = get().activeSessionId;
    const previousTurn = previousSessionId
      ? get().turnsBySession[previousSessionId]
      : undefined;
    if (previousSessionId && previousTurn?.protocolVersion === 3 && previousTurn.isLocked) {
      chatStreamV3Transport.detach(previousSessionId);
    }

    messageLoadSequence += 1;
    messageLoadController?.abort();
    messageLoadController = null;

    const turn = get().turnsBySession[id] ?? idleTurn();
    const cachedMessages = get().messageCacheBySession[id] ?? [];
    const cachedRounds = computeRounds(cachedMessages);
    broadcastSessionSwitch(id); // V4.0 DEFECT-008: notify other tabs of session switch
    set({
      activeSessionId: id,
      messages: extractVisibleMessages(cachedRounds, DEFAULT_VISIBLE_ROUNDS),
      allMessages: cachedMessages,
      messageNextCursor: null,
      isLoadingMessages: false,
      hasOlderMessages: cachedRounds.length > DEFAULT_VISIBLE_ROUNDS,
      totalRoundCount: cachedRounds.length,
      visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
      _pendingSessionRefresh: false,
      ...legacyMirror(turn, id),
    });
    const resumable = v3ResumeCallbacks.get(id);
    if (turn.protocolVersion === 3 && turn.isLocked && resumable?.generationId === turn.generationId) {
      void resumable.resume();
    }
  },

  // Starting a new chat explicitly aborts and clears only the active session's turn.
  resetSession: () => {
    const owningSessionId = get().activeSessionId;
    let retainedOwnerTurn: SessionTurnState | null = null;
    messageLoadSequence += 1;
    messageLoadController?.abort();
    messageLoadController = null;
    if (owningSessionId) {
      const owningGeneration = get().turnsBySession[owningSessionId]?.generationId;
      if (owningGeneration) flushImmediate(owningSessionId, owningGeneration);
      const owningTurn = get().turnsBySession[owningSessionId];
      retainedOwnerTurn = owningTurn?.error
        ? { ...owningTurn, isLocked: false }
        : idleTurn();
      if (owningGeneration && owningTurn?.generationId === owningGeneration && owningTurn.content.trim()) {
        const partialMessage: Message = {
          id: `local-${owningGeneration}`,
          role: 'assistant',
          content: owningTurn.content,
          citations: owningTurn.citations,
          executionSnapshot: owningTurn.executionSnapshot ?? null,
          createdAt: new Date().toISOString(),
        };
        set((state) => ({
          localPartialsBySession: {
            ...state.localPartialsBySession,
            [owningSessionId]: appendUniqueById(
              state.localPartialsBySession[owningSessionId] ?? [],
              [partialMessage],
            ),
          },
          messageCacheBySession: {
            ...state.messageCacheBySession,
            [owningSessionId]: appendUniqueById(
              state.messageCacheBySession[owningSessionId] ?? [],
              [partialMessage],
            ).slice(-MAX_ALL_MESSAGES),
          },
        }));
      }
      if (owningTurn?.protocolVersion === 3 && owningTurn.v3Turn) {
        void chatStreamV3Transport.cancel(owningTurn.v3Turn).catch(() => undefined);
        chatStreamV3Transport.detach(owningSessionId);
        v3ResumeCallbacks.delete(owningSessionId);
      }
      abortActiveStream(owningSessionId, owningGeneration ?? undefined);
      resetTokenBatcher(owningSessionId, owningGeneration ?? undefined);
    }
    broadcastSessionSwitch(null); // V4.0 DEFECT-008: notify other tabs (null = no active session)
    set({
      activeSessionId: null,
      turnsBySession: owningSessionId
        ? { ...get().turnsBySession, [owningSessionId]: retainedOwnerTurn ?? idleTurn() }
        : get().turnsBySession,
      messages: [],
      allMessages: [],
      messageNextCursor: null,
      isLoadingMessages: false,
      streamContent: '',
      citations: [],
      streamQuality: null,
      streamPhase: 'idle',
      streamingSessionId: null,
      sendError: null,
      isSendLocked: false,
      hasOlderMessages: false,
      totalRoundCount: 0,
      visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
      _pendingSessionRefresh: false,
      aiStatusText: null,
    });
  },

  setAIStatusText: (text) => {
    const sessionId = get().activeSessionId;
    if (!sessionId) return;
    set((state) => withTurnUpdate(state, sessionId, null, { aiStatusText: text }));
  },

  // V3.6 MED-001 / V3.7 P1.3: addMessage now prunes allMessages when exceeding MAX cap
  // V4.2 SYS-V4.2-016: Removed computeRounds() from addMessage — it was redundant
  // because finishStreamingMessage() always recomputes rounds from allMessages.
  // Previously: addMessage called computeRounds() in prune path, then
  // finishStreamingMessage() called computeRounds() again = 2 calls per completed message.
  // Now: addMessage only appends/prunes raw arrays (no round computation).
  // finishStreamingMessage() is the sole point that computes rounds + visibleMessages.
  addMessage: (message) => set((state) => {
    const newAllMessages = [...state.allMessages, message];
    const sessionId = state.activeSessionId;
    const cacheMessages = sessionId
      ? [...(state.messageCacheBySession[sessionId] ?? []), message].slice(-MAX_ALL_MESSAGES)
      : null;
    const cacheUpdate = sessionId && cacheMessages
      ? { messageCacheBySession: { ...state.messageCacheBySession, [sessionId]: cacheMessages } }
      : {};
    // Prune front if exceeding cap — prevents unbounded memory growth
    // V4.2 SYS-V4.2-016: No computeRounds here — just prune raw array
    if (newAllMessages.length > MAX_ALL_MESSAGES) {
      const pruned = newAllMessages.slice(newAllMessages.length - MAX_ALL_MESSAGES);
      return {
        // V4.2 SYS-V4.2-016: messages will be recomputed in finishStreamingMessage()
        // For now, just append to visible messages (interim state during streaming)
        messages: [...state.messages, message],
        allMessages: pruned,
        hasOlderMessages: true,
        ...cacheUpdate,
      };
    }
    const newMessages = [...state.messages, message];
    return {
      messages: newMessages,
      allMessages: newAllMessages,
      ...cacheUpdate,
    };
  }),

  updateStreamContent: (content) => {
    const sessionId = get().activeSessionId;
    if (!sessionId) return;
    set((state) => withTurnUpdate(state, sessionId, null, { content }));
  },

  setStreamCitations: (citations) => {
    const sessionId = get().activeSessionId;
    if (!sessionId) return;
    set((state) => withTurnUpdate(state, sessionId, null, { citations }));
  },

  setSendError: (sendError) => {
    const sessionId = get().activeSessionId;
    if (!sessionId) return set({ sendError });
    set((state) => withTurnUpdate(state, sessionId, null, {
      error: sendError,
      ...(sendError === null && state.turnsBySession[sessionId]?.phase === 'error' ? { phase: 'idle' as const } : {}),
    }));
  },

  // V3.5: Stream phase transitions
  setStreamPhase: (phase) => {
    const sessionId = get().activeSessionId;
    if (!sessionId) return set({ streamPhase: phase });
    set((state) => withTurnUpdate(state, sessionId, null, { phase }));
  },

  // V3.5 HIGH-001: Send lock mechanism
  lockSend: () => {
    const sessionId = get().activeSessionId;
    if (!sessionId) return set({ isSendLocked: true });
    set((state) => withTurnUpdate(state, sessionId, null, { isLocked: true }));
  },
  // V3.6 LOW-001: Add dev-only warning for double-unlock detection
  unlockSend: () => {
    const sessionId = get().activeSessionId;
    if (!sessionId) return set({ isSendLocked: false });
    if (!get().turnsBySession[sessionId]?.isLocked) {
      console.warn('[chatStore] unlockSend called when isSendLocked is already false — possible double-unlock');
    }
    set((state) => withTurnUpdate(state, sessionId, null, { isLocked: false }));
  },

  abortSessionStream: (sessionId) => {
    const turn = get().turnsBySession[sessionId];
    if (turn?.protocolVersion === 3 && turn.v3Turn) {
      void chatStreamV3Transport.cancel(turn.v3Turn).catch((error) => {
        console.error('Failed to cancel v3 chat turn:', error);
      });
      chatStreamV3Transport.detach(sessionId);
    }
    abortActiveStream(sessionId);
  },

  removeSessionState: (sessionId) => {
    const turn = get().turnsBySession[sessionId];
    if (turn?.protocolVersion === 3 && turn.v3Turn) {
      void chatStreamV3Transport.cancel(turn.v3Turn).catch(() => undefined);
      chatStreamV3Transport.detach(sessionId);
      v3ResumeCallbacks.delete(sessionId);
    }
    if (hasActiveStream(sessionId)) abortActiveStream(sessionId);
    resetTokenBatcher(sessionId);
    if (get().activeSessionId === sessionId) {
      messageLoadSequence += 1;
      messageLoadController?.abort();
      messageLoadController = null;
    }
    set((state) => {
      const { [sessionId]: _turn, ...turnsBySession } = state.turnsBySession;
      const { [sessionId]: _cache, ...messageCacheBySession } = state.messageCacheBySession;
      const { [sessionId]: _partial, ...localPartialsBySession } = state.localPartialsBySession;
      const activeUpdates = state.activeSessionId === sessionId
        ? {
            activeSessionId: null,
            messages: [],
            allMessages: [],
            messageNextCursor: null,
            isLoadingMessages: false,
            hasOlderMessages: false,
            totalRoundCount: 0,
            visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
            ...legacyMirror(idleTurn(), null),
          }
        : {};
      return {
        turnsBySession,
        messageCacheBySession,
        localPartialsBySession,
        ...activeUpdates,
      };
    });
  },

  dismissSessionError: (sessionId) => {
    set((state) => withTurnUpdate(state, sessionId, null, { phase: 'idle', error: null }));
  },

  loadSessions: async () => {
    try {
      const page = await chatApi.getSessions();
      set({ sessions: page.results, sessionNextCursor: page.next });
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  },

  loadMoreSessions: async () => {
    const cursor = get().sessionNextCursor;
    if (!cursor) return;

    try {
      const page = await chatApi.getSessions({ cursor });
      set({
        sessions: appendUniqueById(get().sessions, page.results),
        sessionNextCursor: page.next,
      });
    } catch (error) {
      console.error('Failed to load more sessions:', error);
    }
  },

  loadMessages: async (sessionId: string) => {
    messageLoadController?.abort();
    const controller = new AbortController();
    messageLoadController = controller;
    const requestSequence = ++messageLoadSequence;
    set({ isLoadingMessages: true });
    try {
      const page = await chatApi.getMessages(sessionId, { signal: controller.signal });
      if (requestSequence !== messageLoadSequence || get().activeSessionId !== sessionId) return;

      const serverMessages = page.results.map(mapApiMessage);
      const localPartials = get().localPartialsBySession[sessionId] ?? [];
      const remainingLocalPartials = localPartials.filter((partial) => (
        !serverMessages.some((serverMessage) => isReconciledLocalPartial(partial, serverMessage))
      ));
      const allMessages = sortMessagesChronologically(
        appendUniqueById(serverMessages, remainingLocalPartials),
      );

      // V3.5: Sliding window — compute rounds, extract visible slice
      const rounds = computeRounds(allMessages);
      const visibleMessages = extractVisibleMessages(rounds, DEFAULT_VISIBLE_ROUNDS);
      const hasOlder = rounds.length > DEFAULT_VISIBLE_ROUNDS || page.next !== null;

      set((state) => ({
        activeSessionId: sessionId,
        allMessages,
        messages: visibleMessages,
        messageCacheBySession: {
          ...state.messageCacheBySession,
          [sessionId]: allMessages.slice(-MAX_ALL_MESSAGES),
        },
        localPartialsBySession: {
          ...state.localPartialsBySession,
          [sessionId]: remainingLocalPartials,
        },
        messageNextCursor: page.next,
        hasOlderMessages: hasOlder,
        visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
        isLoadingMessages: false,
        // V3.6 MED-003: Cache round count for efficient hasOlderMessages checks
        totalRoundCount: rounds.length,
      }));
      if (messageLoadController === controller) messageLoadController = null;
    } catch (error) {
      if (requestSequence !== messageLoadSequence || get().activeSessionId !== sessionId) return;

      console.error('Failed to load messages:', error);
      // V3.6 MED-002: Use i18n error key instead of raw string
      set((state) => ({
        isLoadingMessages: false,
        ...(state.turnsBySession[sessionId]?.error
          ? {}
          : withTurnUpdate(state, sessionId, null, { phase: 'error', error: 'error_session' })),
      }));
      if (messageLoadController === controller) messageLoadController = null;
    }
  },

  loadOlderMessages: async () => {
    const sessionId = get().activeSessionId;
    const cursor = get().messageNextCursor;
    if (!sessionId || !cursor) return;

    messageLoadController?.abort();
    const controller = new AbortController();
    messageLoadController = controller;
    const requestSequence = ++messageLoadSequence;
    set({ isLoadingMessages: true });

    try {
      const page = await chatApi.getMessages(sessionId, { cursor, signal: controller.signal });
      if (requestSequence !== messageLoadSequence || get().activeSessionId !== sessionId) return;

      const serverMessages = page.results.map(mapApiMessage);
      const localPartials = get().localPartialsBySession[sessionId] ?? [];
      const reconciledLocalIds = new Set(
        localPartials
          .filter((partial) => serverMessages.some(
            (serverMessage) => isReconciledLocalPartial(partial, serverMessage),
          ))
          .map((partial) => partial.id),
      );
      const remainingLocalPartials = localPartials.filter(
        (partial) => !reconciledLocalIds.has(partial.id),
      );
      const existingMessages = get().allMessages.filter(
        (message) => !reconciledLocalIds.has(message.id),
      );
      const allMessages = sortMessagesChronologically(
        appendUniqueById(existingMessages, serverMessages),
      );
      const rounds = computeRounds(allMessages);
      const visibleRoundCount = get().visibleRoundCount;

      set((state) => ({
        allMessages,
        messages: extractVisibleMessages(rounds, visibleRoundCount),
        messageCacheBySession: {
          ...state.messageCacheBySession,
          [sessionId]: allMessages.slice(-MAX_ALL_MESSAGES),
        },
        localPartialsBySession: {
          ...state.localPartialsBySession,
          [sessionId]: remainingLocalPartials,
        },
        messageNextCursor: page.next,
        hasOlderMessages: visibleRoundCount < rounds.length || page.next !== null,
        totalRoundCount: rounds.length,
        isLoadingMessages: false,
      }));
      if (messageLoadController === controller) messageLoadController = null;
    } catch (error) {
      if (requestSequence !== messageLoadSequence || get().activeSessionId !== sessionId) return;

      console.error('Failed to load older messages:', error);
      set((state) => ({
        isLoadingMessages: false,
        ...(state.turnsBySession[sessionId]?.error
          ? {}
          : withTurnUpdate(state, sessionId, null, { phase: 'error', error: 'error_session' })),
      }));
      if (messageLoadController === controller) messageLoadController = null;
    }
  },

  // V3.5: Load older rounds (expand sliding window)
  // V3.6 MED-003: Use cached totalRoundCount for hasOlderMessages comparison
  loadOlderRounds: (count: number) => {
    const { allMessages, visibleRoundCount, totalRoundCount, messageNextCursor } = get();
    const rounds = computeRounds(allMessages);
    const newVisibleCount = Math.min(visibleRoundCount + count, totalRoundCount);
    const visibleMessages = extractVisibleMessages(rounds, newVisibleCount);
    set({
      messages: visibleMessages,
      visibleRoundCount: newVisibleCount,
      hasOlderMessages: newVisibleCount < totalRoundCount || messageNextCursor !== null,
    });
  },

  sendMessage: async (content: string, options: SendMessageOptions = {}) => {
    const state = get();
    let sessionId = state.activeSessionId;
    const regenerateMessageId = options.regenerateMessageId;
    const isRegeneration = Boolean(regenerateMessageId);
    if (sessionId && state.turnsBySession[sessionId]?.isLocked) return;
    if (!sessionId && state.isSendLocked) return;
    if (isRegeneration && (!sessionId || !/^[0-9a-f-]{36}$/i.test(regenerateMessageId!))) {
      set({ streamPhase: 'error', sendError: 'error_session', isSendLocked: false });
      return;
    }

    const requestedMode: AnswerMode = options.answerMode === 'deep' ? 'deep' : 'fast';
    const requestedThinkingEnabled = options.thinkingEnabled === true;
    if (requestedMode === 'deep' && options.canUseDeep !== true) {
      if (sessionId) {
        set((current) => withTurnUpdate(current, sessionId!, null, {
          phase: 'error',
          safePhase: null,
          isLocked: false,
          answerMode: 'fast',
          requestedAnswerMode: 'deep',
          effectiveAnswerMode: 'fast',
          requested_answer_mode: 'deep',
          effective_answer_mode: 'fast',
          requestedThinkingEnabled: false,
          thinkingEnabled: false,
          thinkingSnapshotKnown: true,
          thinkingBudget: null,
          modelId: null,
          policyFallbackCode: '',
          requested_thinking_enabled: false,
          thinking_enabled: false,
          thinking_snapshot_known: true,
          thinking_budget: null,
          model_id: null,
          policy_fallback_code: '',
          executionSnapshot: null,
          effectiveSnapshot: null,
          error: 'error_deep_unavailable',
        }));
      } else {
        set({ streamPhase: 'error', sendError: 'error_deep_unavailable', isSendLocked: false });
      }
      return;
    }
    if (requestedThinkingEnabled && options.canUseThinking !== true) {
      if (sessionId) {
        set((current) => withTurnUpdate(current, sessionId!, null, {
          phase: 'error',
          safePhase: null,
          isLocked: false,
          answerMode: requestedMode,
          requestedAnswerMode: requestedMode,
          effectiveAnswerMode: requestedMode,
          requested_answer_mode: requestedMode,
          effective_answer_mode: requestedMode,
          requestedThinkingEnabled: true,
          thinkingEnabled: false,
          thinkingSnapshotKnown: true,
          thinkingBudget: null,
          policyFallbackCode: 'thinking_not_allowed',
          requested_thinking_enabled: true,
          thinking_enabled: false,
          thinking_snapshot_known: true,
          thinking_budget: null,
          model_id: null,
          policy_fallback_code: 'thinking_not_allowed',
          executionSnapshot: null,
          effectiveSnapshot: null,
          error: 'error_thinking_unavailable',
        }));
      } else {
        set({ streamPhase: 'error', sendError: 'error_thinking_unavailable', isSendLocked: false });
      }
      return;
    }
    const answerMode = requestedMode;
    const retryClientRequestId = options.retryClientRequestId;
    const retryTurn = sessionId && retryClientRequestId
      ? state.turnsBySession[sessionId]
      : undefined;
    const isExplicitFastRetry = Boolean(
      retryClientRequestId
      && answerMode === 'fast'
      && retryTurn?.clientRequestId === retryClientRequestId
      && (retryTurn.requestedAnswerMode
        ?? retryTurn.requested_answer_mode
        ?? retryTurn.answerMode) === 'deep'
      && (retryTurn.requestedThinkingEnabled
        ?? retryTurn.requested_thinking_enabled
        ?? false) === requestedThinkingEnabled
      && retryTurn.phase === 'error'
      && retryTurn.error
      && !retryTurn.isLocked,
    );
    if (retryClientRequestId && !isExplicitFastRetry) {
      if (sessionId) {
        set((current) => withTurnUpdate(current, sessionId!, null, {
          phase: 'error',
          isLocked: false,
          error: 'error_generic',
        }));
      } else {
        set({ streamPhase: 'error', sendError: 'error_generic', isSendLocked: false });
      }
      return;
    }

    if (!sessionId) {
      set({ isSendLocked: true, sendError: null, streamPhase: 'connecting' });
      try {
        const newSession = await chatApi.createSession({ title: generateSmartTitle(content) });
        sessionId = newSession.id;
        set({
          activeSessionId: sessionId,
          sessions: [newSession, ...get().sessions],
          // V3.6 HIGH-002: Mark that we need to refresh sessions after first message in new session
          _pendingSessionRefresh: true,
        });
      } catch (error) {
        console.error('Failed to create session:', error);
        set({ streamPhase: 'error', sendError: 'error_session', streamingSessionId: null, isSendLocked: false });
        return;
      }
    }

    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(sessionId)) {
      set((current) => withTurnUpdate(current, sessionId, null, {
        phase: 'error', isLocked: false, error: 'error_session', generationId: null,
      }));
      return;
    }

    const clientRequestId = isExplicitFastRetry
      ? retryClientRequestId!
      : crypto.randomUUID();
    const generationId = crypto.randomUUID();
    const startedAtMs = Date.now();
    set((current) => withTurnUpdate(current, sessionId, null, {
      phase: 'connecting',
      safePhase: 'accepted',
      isLocked: true,
      answerMode,
      requestedAnswerMode: answerMode,
      effectiveAnswerMode: answerMode,
      requested_answer_mode: answerMode,
      effective_answer_mode: answerMode,
      requestedThinkingEnabled,
      thinkingEnabled: requestedThinkingEnabled,
      thinkingSnapshotKnown: undefined,
      thinkingBudget: null,
      modelId: null,
      policyFallbackCode: '',
      requested_thinking_enabled: requestedThinkingEnabled,
      thinking_enabled: requestedThinkingEnabled,
      thinking_snapshot_known: undefined,
      thinking_budget: null,
      model_id: null,
      policy_fallback_code: '',
      executionSnapshot: null,
      effectiveSnapshot: null,
      content: '',
      citations: [],
      quality: null,
      error: null,
      aiStatusText: null,
      generationId,
      clientRequestId,
      turnId: isExplicitFastRetry ? retryTurn?.turnId ?? null : null,
      lastEventSeq: isExplicitFastRetry ? retryTurn?.lastEventSeq ?? 0 : 0,
      protocolVersion: null,
      recoveryState: 'idle',
      timings: {},
      startedAtMs,
    }));

    if (!isExplicitFastRetry && !isRegeneration) {
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        createdAt: new Date().toISOString(),
      };
      get().addMessage(userMessage);
    }

    const token = getAuthToken();
    // V3.5: Initialize token batch renderer for this stream
    // V4.2 SYS-V4.2-015: Changed from (fullContent: string) to incremental diff mode.
    // appendTokens mode: only passes new tokens → Zustand appends to existing streamContent
    // fullContent mode: passes complete string → Zustand replaces streamContent (for flushImmediate)
    initTokenBatcher(sessionId, generationId, (update: { appendTokens: string } | { fullContent: string }) => {
      if ('appendTokens' in update) {
        set((current) => {
          const turn = current.turnsBySession[sessionId];
          if (turn?.generationId !== generationId) return {};
          return withTurnUpdate(current, sessionId, generationId, { content: turn.content + update.appendTokens });
        });
      } else {
        set((current) => withTurnUpdate(current, sessionId, generationId, { content: update.fullContent }));
      }
    });

    const saveLocalPartial = (partialContent: string, partialCitations: Citation[]) => {
      if (!partialContent.trim()) return;
      const partialMessage: Message = {
        id: `local-${generationId}`,
        role: 'assistant',
        content: partialContent,
        citations: partialCitations,
        executionSnapshot: get().turnsBySession[sessionId]?.executionSnapshot ?? null,
        createdAt: new Date().toISOString(),
      };
      set((current) => {
        if (current.turnsBySession[sessionId]?.generationId !== generationId) return {};
        const localPartials = appendUniqueById(
          current.localPartialsBySession[sessionId] ?? [],
          [partialMessage],
        );
        const activeUpdates = current.activeSessionId === sessionId
          ? {
              messages: appendUniqueById(current.messages, [partialMessage]),
              allMessages: appendUniqueById(current.allMessages, [partialMessage]),
            }
          : {};
        return {
          localPartialsBySession: {
            ...current.localPartialsBySession,
            [sessionId]: localPartials,
          },
          messageCacheBySession: {
            ...current.messageCacheBySession,
            [sessionId]: appendUniqueById(
              current.messageCacheBySession[sessionId] ?? [],
              [partialMessage],
            ).slice(-MAX_ALL_MESSAGES),
          },
          ...activeUpdates,
        };
      });
    };

    const commitRegeneratedVersion = () => {
      if (!regenerateMessageId) return;
      set((current) => {
        const withoutOldVersion = (messages: Message[]) => messages.filter(
          (message) => message.id !== regenerateMessageId,
        );
        return {
          messages: current.activeSessionId === sessionId
            ? withoutOldVersion(current.messages)
            : current.messages,
          allMessages: current.activeSessionId === sessionId
            ? withoutOldVersion(current.allMessages)
            : current.allMessages,
          messageCacheBySession: {
            ...current.messageCacheBySession,
            [sessionId]: withoutOldVersion(current.messageCacheBySession[sessionId] ?? []),
          },
        };
      });
    };

    const finishRecoverable = (error: string | null, phase: StreamPhase = error ? 'error' : 'idle') => {
      flushImmediate(sessionId, generationId);
      const turn = get().turnsBySession[sessionId];
      if (turn?.generationId !== generationId) return;
      saveLocalPartial(turn.content, turn.citations);
      resetTokenBatcher(sessionId, generationId);
      clearStreamOnComplete(sessionId, generationId);
      set((current) => withTurnUpdate(current, sessionId, generationId, {
        phase,
        safePhase: error ? get().turnsBySession[sessionId]?.safePhase ?? null : null,
        isLocked: false,
        content: '',
        citations: [],
        quality: null,
        error,
        aiStatusText: null,
        v3Turn: error ? turn.v3Turn ?? null : null,
        recoveryState: error ? (turn.turnId ? turn.recoveryState : 'failed') : 'idle',
      }));
      if (get()._pendingSessionRefresh) {
        set({ _pendingSessionRefresh: false });
        get().loadSessions();
      }
    };

    const streamOnce = async (): Promise<boolean> => {
      const controller = createStreamAbortController(sessionId, generationId);

      // Progressive thinking phases + connection status tracking
      let connectionWatchdog: ReturnType<typeof setTimeout> | undefined;
      let eventIdleWatchdog: ReturnType<typeof setTimeout> | undefined;
      let totalWatchdog: ReturnType<typeof setTimeout> | undefined;
      let abortReason: 'connection' | 'idle' | 'total' | null = null;
      let phaseTimerSearching: ReturnType<typeof setTimeout> | undefined;
      let phaseTimerGenerating: ReturnType<typeof setTimeout> | undefined;
      let assistantContent = '';

      const clearPhaseTimers = () => {
        if (phaseTimerSearching) clearTimeout(phaseTimerSearching);
        if (phaseTimerGenerating) clearTimeout(phaseTimerGenerating);
      };

      const clearAllTimers = () => {
        if (connectionWatchdog) clearTimeout(connectionWatchdog);
        if (eventIdleWatchdog) clearTimeout(eventIdleWatchdog);
        if (totalWatchdog) clearTimeout(totalWatchdog);
        clearPhaseTimers();
      };

      const isCurrentGeneration = () => (
        get().turnsBySession[sessionId]?.generationId === generationId
      );
      const abortForTimeout = (reason: 'connection' | 'idle' | 'total') => {
        if (!isCurrentGeneration() || controller.signal.aborted) return;
        abortReason = reason;
        clearAllTimers();
        controller.abort();
      };
      const armEventIdleWatchdog = () => {
        if (eventIdleWatchdog) clearTimeout(eventIdleWatchdog);
        eventIdleWatchdog = setTimeout(() => abortForTimeout('idle'), CHAT_STREAM_TIMEOUTS.idleMs);
      };
      const markAnswerStarted = () => {
        set((current) => {
          const turn = current.turnsBySession[sessionId];
          const timings = turn?.timings ?? {};
          return withTurnUpdate(current, sessionId, generationId, {
            phase: 'streaming',
            safePhase: 'generating',
            timings: timings.firstAnswerMs === undefined
              ? { ...timings, firstAnswerMs: elapsedMs(turn?.startedAtMs) }
              : timings,
          });
        });
      };
      const applyUsageTimings = (data: Record<string, unknown>) => {
        set((current) => {
          const turn = current.turnsBySession[sessionId];
          const timings = { ...(turn?.timings ?? {}) };
          const firstAnswerMs = data.first_answer_token_ms ?? data.ttfe_ms;
          const totalMs = data.total_duration_ms ?? data.latency_ms;
          if (typeof firstAnswerMs === 'number' && Number.isFinite(firstAnswerMs)) {
            timings.firstAnswerMs = Math.max(0, firstAnswerMs);
          }
          if (typeof totalMs === 'number' && Number.isFinite(totalMs)) {
            timings.totalMs = Math.max(0, totalMs);
          }
          return withTurnUpdate(current, sessionId, generationId, { timings });
        });
      };
      let recoverInterruptedStream: (() => Promise<boolean | null>) | null = null;

      if (chatStreamV3Enabled()) {
        let v3ConsumerRunning = false;
        let v3ResumeRequested = false;
        const applyV3Event = (event: ValidatedChatStreamEvent) => {
          if (!isCurrentGeneration()) return;
          const data = event.data;
          const sequence = event.sequence!;
          switch (event.name) {
            case 'meta': {
              const snapshot = snapshotFromPayload(data);
              set((current) => withTurnUpdate(current, sessionId, generationId, {
                turnId: data.turn_id,
                protocolVersion: 3,
                recoveryState: 'available',
                ...(snapshot ? snapshotTurnPatch(snapshot) : {}),
              }));
              break;
            }
            case 'phase': {
              const phase = mapServerPhaseForUi(data.phase);
              set((current) => withTurnUpdate(current, sessionId, generationId, {
                phase: phase.streamPhase,
                safePhase: phase.safePhase,
              }));
              break;
            }
            case 'answer_delta':
              markAnswerStarted();
              assistantContent += data.text || '';
              appendToken(sessionId, generationId, data.text || '');
              break;
            case 'citations':
              set((current) => withTurnUpdate(current, sessionId, generationId, { citations: data }));
              break;
            case 'quality':
              set((current) => withTurnUpdate(current, sessionId, generationId, { quality: data }));
              break;
            case 'usage':
              applyUsageTimings(data);
              break;
            case 'done':
              set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
              flushImmediate(sessionId, generationId);
              commitRegeneratedVersion();
              v3ResumeCallbacks.delete(sessionId);
              get().finishStreamingMessage(data.message_id, data.session_id, generationId);
              return;
            case 'error':
              set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
              v3ResumeCallbacks.delete(sessionId);
              finishRecoverable('error_generic');
              return;
            case 'token':
              // Protocol 3 never emits legacy token events; validation rejects them.
              return;
          }
          set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
        };

        const resumeV3 = async () => {
          if (v3ConsumerRunning) {
            v3ResumeRequested = true;
            return;
          }
          if (!isCurrentGeneration()) return;
          if (get().activeSessionId !== sessionId) return;
          const accepted = get().turnsBySession[sessionId]?.v3Turn;
          if (!accepted) return;
          v3ConsumerRunning = true;
          set((current) => withTurnUpdate(current, sessionId, generationId, {
            phase: 'connecting',
            safePhase: 'accepted',
            recoveryState: 'recovering',
          }));
          try {
            const terminal = await chatStreamV3Transport.consume(accepted, {
              after: get().turnsBySession[sessionId]?.lastEventSeq ?? 0,
              onEvent: applyV3Event,
              signal: controller.signal,
            });
            if (terminal.kind === 'detached' && controller.signal.aborted && isCurrentGeneration()) {
              v3ResumeCallbacks.delete(sessionId);
              finishRecoverable(null, 'idle');
            }
          } catch (error) {
            if (!isCurrentGeneration()) return;
            v3ResumeCallbacks.delete(sessionId);
            const errorKey = error instanceof ChatStreamV3HttpError
              && (error.status === 401 || error.status === 403)
              ? 'error_auth'
              : 'error_network';
            finishRecoverable(errorKey);
          } finally {
            v3ConsumerRunning = false;
            if (v3ResumeRequested) {
              v3ResumeRequested = false;
              const current = get().turnsBySession[sessionId];
              if (current?.generationId === generationId
                && current.isLocked
                && get().activeSessionId === sessionId
                && v3ResumeCallbacks.has(sessionId)) {
                queueMicrotask(() => { void resumeV3(); });
              }
            }
          }
        };

        try {
          const accepted = await chatStreamV3Transport.accept({
            sessionId,
            content,
            clientRequestId,
            answerMode,
            thinkingEnabled: requestedThinkingEnabled,
            ...(regenerateMessageId ? { regenerateMessageId } : {}),
          }, controller.signal);
          set((current) => withTurnUpdate(current, sessionId, generationId, {
            phase: 'connecting',
            safePhase: 'accepted',
            protocolVersion: 3,
            turnId: accepted.turn_id,
            v3Turn: accepted,
            recoveryState: 'available',
            capacityRetryAfterSeconds: null,
            capacityRetryAtMs: null,
            timings: {
              ...(current.turnsBySession[sessionId]?.timings ?? {}),
              connectionMs: elapsedMs(current.turnsBySession[sessionId]?.startedAtMs),
            },
          }));
          v3ResumeCallbacks.set(sessionId, { generationId, resume: resumeV3 });
          await resumeV3();
          return true;
        } catch (error) {
          if (error instanceof ChatStreamV3HttpError
            && error.code === 'generation_capacity_reached') {
            const retrySeconds = Math.max(1, error.retryAfterSeconds ?? 5);
            resetTokenBatcher(sessionId, generationId);
            clearStreamOnComplete(sessionId, generationId);
            set((current) => withTurnUpdate(current, sessionId, generationId, {
              phase: 'error',
              safePhase: 'accepted',
              isLocked: true,
              error: 'error_capacity',
              capacityRetryAfterSeconds: retrySeconds,
              capacityRetryAtMs: Date.now() + retrySeconds * 1_000,
            }));
            const priorTimer = capacityCooldownTimers.get(sessionId);
            if (priorTimer) clearTimeout(priorTimer);
            capacityCooldownTimers.set(sessionId, setTimeout(() => {
              capacityCooldownTimers.delete(sessionId);
              set((current) => withTurnUpdate(current, sessionId, generationId, {
                isLocked: false,
                capacityRetryAtMs: null,
              }));
            }, retrySeconds * 1_000));
            return false;
          }
          if (error instanceof DOMException && error.name === 'AbortError') {
            finishRecoverable(null, 'idle');
            return false;
          }
          const errorKey = error instanceof ChatStreamV3HttpError
            && (error.status === 401 || error.status === 403)
            ? 'error_auth'
            : error instanceof ChatStreamV3HttpError && error.status >= 500
              ? 'error_server'
              : 'error_generic';
          finishRecoverable(errorKey);
          return false;
        }
      }

      try {
        connectionWatchdog = setTimeout(
          () => abortForTimeout('connection'),
          CHAT_STREAM_TIMEOUTS.connectionMs,
        );
        totalWatchdog = setTimeout(
          () => abortForTimeout('total'),
          CHAT_STREAM_TIMEOUTS.totalMs,
        );
        // V3.5 CRIT-001: Pass AbortController signal to fetch
        // V6.0: scope the SSE request to the active space (fetch bypasses the
        // axios interceptor, so set the header explicitly here).
        const spaceId = getActiveSpaceId();
        const sendHeaders: Record<string, string> = {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        };
        if (spaceId) sendHeaders['X-Space-Id'] = spaceId;
        const sendUrl = regenerateMessageId
          ? `/api/v1/chat/messages/${regenerateMessageId}/regenerate/`
          : `/api/v1/chat/sessions/${sessionId}/send/`;
        const response = await fetch(sendUrl, {
          method: 'POST',
          headers: sendHeaders,
          body: JSON.stringify({
            content,
            client_request_id: clientRequestId,
            answer_mode: answerMode,
            thinking_enabled: requestedThinkingEnabled,
            protocol_version: 2,
          }),
          signal: controller.signal, // V3.5: AbortController signal
        });

        if (connectionWatchdog) {
          clearTimeout(connectionWatchdog);
          connectionWatchdog = undefined;
        }

        if (!response.ok) {
          if (answerMode === 'deep' && (response.status === 403 || response.status === 409)) {
            throw new Error('deep_unavailable');
          }
          if (requestedThinkingEnabled && (response.status === 403 || response.status === 409)) {
            throw new Error('thinking_unavailable');
          }
          throw new Error(`HTTP ${response.status}`);
        }

        const responseTurnId = response.headers?.get?.('X-Chat-Turn-Id') || null;
        const responseClientRequestId = response.headers?.get?.('X-Chat-Client-Request-Id') || null;
        if (responseClientRequestId && responseClientRequestId !== clientRequestId) {
          finishRecoverable('error_generic');
          return false;
        }
        if (responseTurnId) {
          set((current) => withTurnUpdate(current, sessionId, generationId, {
            turnId: responseTurnId,
            recoveryState: 'available',
          }));
        }

        // Headers received — connection established → 'searching' phase
        set((current) => {
          const turn = current.turnsBySession[sessionId];
          return withTurnUpdate(current, sessionId, generationId, {
            phase: 'searching',
            safePhase: 'searching',
            timings: {
              ...(turn?.timings ?? {}),
              connectionMs: elapsedMs(turn?.startedAtMs),
            },
          });
        });

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        const parser = new StoreSSEDecoder();
        armEventIdleWatchdog();

        // Phase 1: After 3s of no tokens → "searching" phase (already set on connection)
        phaseTimerSearching = setTimeout(() => {
          if (get().turnsBySession[sessionId]?.generationId === generationId
            && get().turnsBySession[sessionId]?.phase === 'connecting') {
            set((current) => withTurnUpdate(current, sessionId, generationId, { phase: 'searching' }));
          }
        }, 3000);

        // Phase 2: After 8s of no tokens → "streaming" phase indicator
        phaseTimerGenerating = setTimeout(() => {
          if (get().turnsBySession[sessionId]?.generationId === generationId
            && get().turnsBySession[sessionId]?.phase === 'searching' && !assistantContent) {
            // Still waiting — keep in searching but indicate long retrieval
          }
        }, 8000);

        recoverInterruptedStream = async (): Promise<boolean | null> => {
          const turn = get().turnsBySession[sessionId];
          if (!turn?.turnId || turn.generationId !== generationId) return null;

          set((current) => withTurnUpdate(current, sessionId, generationId, {
            phase: 'connecting',
            safePhase: 'accepted',
            recoveryState: 'recovering',
          }));
          const recoveryController = createStreamAbortController(sessionId, generationId);
          const recoveryFetch = async (
            url: string,
            init: RequestInit,
          ): Promise<[Response, () => void]> => {
            const attemptController = new AbortController();
            const abortFromOwner = () => attemptController.abort();
            recoveryController.signal.addEventListener('abort', abortFromOwner, { once: true });
            if (recoveryController.signal.aborted) attemptController.abort();
            const timeout = setTimeout(() => {
              attemptController.abort();
            }, CHAT_STREAM_TIMEOUTS.recoveryRequestMs);
            let released = false;
            const release = () => {
              if (released) return;
              released = true;
              clearTimeout(timeout);
              recoveryController.signal.removeEventListener('abort', abortFromOwner);
            };
            try {
              const response = await fetch(url, { ...init, signal: attemptController.signal });
              return [response, release];
            } catch (error) {
              release();
              throw error;
            }
          };
          const recoveryHeaders: Record<string, string> = {
            Accept: 'text/event-stream',
            Authorization: `Bearer ${token}`,
          };
          const recoverySpaceId = getActiveSpaceId();
          if (recoverySpaceId) recoveryHeaders['X-Space-Id'] = recoverySpaceId;

          for (let attempt = 0; attempt < 3; attempt += 1) {
            if (get().turnsBySession[sessionId]?.generationId !== generationId) return false;
            if (attempt > 0) {
              await new Promise((resolve) => setTimeout(resolve, 100 * 2 ** (attempt - 1)));
            }
            if (get().turnsBySession[sessionId]?.generationId !== generationId) return false;

            let releaseRecoveryResponse = () => {};
            try {
              const cursor = get().turnsBySession[sessionId]?.lastEventSeq ?? 0;
              const [replayResponse, releaseReplayResponse] = await recoveryFetch(
                `/api/v1/chat/turns/${turn.turnId}/events/?after=${cursor}`,
                {
                  method: 'GET',
                  headers: { ...recoveryHeaders, 'Last-Event-ID': String(cursor) },
                  signal: recoveryController.signal,
                },
              );
              releaseRecoveryResponse = releaseReplayResponse;
              if (!replayResponse.ok) throw new Error(`HTTP ${replayResponse.status}`);
              validateRecoveryResponseIdentity(
                replayResponse.headers,
                turn.turnId,
                clientRequestId,
              );

              const replayReader = replayResponse.body?.getReader();
              if (!replayReader) throw new Error('missing recovery stream');
              const replayParser = new StoreSSEDecoder();
              const replayDecoder = new TextDecoder();
              while (true) {
                const { done, value } = await replayReader.read();
                const replayMessages = done
                  ? [...replayParser.feed(replayDecoder.decode()), ...replayParser.end()]
                  : replayParser.feed(replayDecoder.decode(value, { stream: true }));
                for (const message of replayMessages) {
                  if (get().turnsBySession[sessionId]?.generationId !== generationId) return false;
                  const event = validateChatStreamMessage(message, {
                    protocolVersion: 2,
                    expectedSessionId: sessionId,
                    expectedTurnId: turn.turnId,
                    expectedClientRequestId: clientRequestId,
                  });
                  const sequence = event.sequence!;
                  if (sequence <= (get().turnsBySession[sessionId]?.lastEventSeq ?? 0)) {
                    continue;
                  }
                  const data = event.data;
                  switch (event.name) {
                    case 'meta': {
                      const snapshot = snapshotFromPayload(data);
                      if (snapshot) {
                        set((current) => withTurnUpdate(
                          current,
                          sessionId,
                          generationId,
                          snapshotTurnPatch(snapshot),
                        ));
                      }
                      break;
                    }
                    case 'phase': {
                      const phase = mapServerPhaseForUi(data.phase);
                      set((current) => withTurnUpdate(current, sessionId, generationId, {
                        phase: phase.streamPhase,
                        safePhase: phase.safePhase,
                      }));
                      break;
                    }
                    case 'answer_delta':
                      markAnswerStarted();
                      assistantContent += data.text || '';
                      appendToken(sessionId, generationId, data.text || '');
                      break;
                    case 'citations':
                      set((current) => withTurnUpdate(current, sessionId, generationId, { citations: data }));
                      break;
                    case 'quality':
                      set((current) => withTurnUpdate(current, sessionId, generationId, { quality: data }));
                      break;
                    case 'usage':
                      applyUsageTimings(data);
                      break;
                    case 'done':
                      set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
                      flushImmediate(sessionId, generationId);
                      commitRegeneratedVersion();
                      get().finishStreamingMessage(data.message_id, data.session_id, generationId);
                      set((current) => withTurnUpdate(current, sessionId, null, { recoveryState: 'recovered' }));
                      return true;
                    case 'error':
                      set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
                      finishRecoverable('error_generic');
                      set((current) => withTurnUpdate(current, sessionId, generationId, { recoveryState: 'failed' }));
                      return false;
                  }
                  set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
                }
                if (done) break;
              }

              releaseRecoveryResponse();
              const [statusResponse, releaseStatusResponse] = await recoveryFetch(`/api/v1/chat/turns/${turn.turnId}/`, {
                method: 'GET',
                headers: { ...recoveryHeaders, Accept: 'application/json' },
                signal: recoveryController.signal,
              });
              releaseRecoveryResponse = releaseStatusResponse;
              if (!statusResponse.ok) throw new Error(`HTTP ${statusResponse.status}`);
              const statusData = await statusResponse.json();
              if (statusData.id !== turn.turnId
                || statusData.client_request_id !== clientRequestId
                || statusData.session !== sessionId) {
                finishRecoverable('error_generic');
                set((current) => withTurnUpdate(current, sessionId, generationId, { recoveryState: 'failed' }));
                return false;
              }
              if (get().turnsBySession[sessionId]?.generationId !== generationId) return false;
              const statusSnapshot = snapshotFromPayload(statusData);
              if (statusSnapshot) {
                set((current) => withTurnUpdate(
                  current,
                  sessionId,
                  generationId,
                  snapshotTurnPatch(statusSnapshot),
                ));
              }
              const statusSequence = Number(statusData.last_event_seq);
              if (Number.isSafeInteger(statusSequence) && statusSequence > 0) {
                set((current) => withTurnUpdate(current, sessionId, generationId, {
                  lastEventSeq: Math.max(current.turnsBySession[sessionId]?.lastEventSeq ?? 0, statusSequence),
                }));
              }
              if (statusData.status === 'completed' && statusData.answer) {
                const answer = mapApiMessage(statusData.answer);
                resetTokenBatcher(sessionId, generationId);
                set((current) => withTurnUpdate(current, sessionId, generationId, {
                  content: answer.content,
                  citations: answer.citations ?? [],
                  ...(answer.executionSnapshot
                    ? snapshotTurnPatch(answer.executionSnapshot)
                    : {}),
                  safePhase: 'finalizing',
                  quality: {
                    confidence: answer.confidenceLabel ?? '',
                    score: answer.confidenceScore ?? 0,
                    needs_human_review: answer.needsHumanReview ?? false,
                    retrieval_mode: answer.retrievalMode ?? '',
                    retrieval_latency_ms: answer.retrievalLatencyMs ?? 0,
                  },
                }));
                commitRegeneratedVersion();
                get().finishStreamingMessage(answer.id, sessionId, generationId);
                set((current) => withTurnUpdate(current, sessionId, null, { recoveryState: 'recovered' }));
                return true;
              }
              if (statusData.status === 'failed' || statusData.status === 'cancelled') {
                finishRecoverable('error_generic');
                set((current) => withTurnUpdate(current, sessionId, generationId, { recoveryState: 'failed' }));
                return false;
              }
            } catch (error) {
              if (error instanceof DOMException
                && error.name === 'AbortError'
                && recoveryController.signal.aborted) {
                if (get().turnsBySession[sessionId]?.generationId === generationId) {
                  finishRecoverable(null, 'idle');
                }
                return false;
              }
              if (get().turnsBySession[sessionId]?.generationId !== generationId) return false;
            } finally {
              releaseRecoveryResponse();
            }
          }

          finishRecoverable('error_timeout');
          set((current) => withTurnUpdate(current, sessionId, generationId, { recoveryState: 'failed' }));
          return false;
        };

        while (true) {
          const { done, value } = await reader.read();
          if (!done && value.length > 0) armEventIdleWatchdog();
          const messages = done
            ? [...parser.feed(decoder.decode()), ...parser.end()]
            : parser.feed(decoder.decode(value, { stream: true }));

          for (const message of messages) {
            armEventIdleWatchdog();
            const currentTurn = get().turnsBySession[sessionId];
            const event = validateChatStreamMessage(message, {
              protocolVersion: currentTurn?.protocolVersion ?? null,
              expectedSessionId: sessionId,
              expectedTurnId: currentTurn?.turnId,
              expectedClientRequestId: clientRequestId,
            });
            if (currentTurn?.protocolVersion == null) {
              set((current) => withTurnUpdate(current, sessionId, generationId, {
                protocolVersion: event.protocolVersion,
              }));
            }
            const sequence = event.sequence;
            if (sequence !== null && sequence <= (currentTurn?.lastEventSeq ?? 0)) continue;
            const data = event.data;
            {
              switch (event.name) {
                case 'meta': {
                  const snapshot = snapshotFromPayload(data);
                  set((current) => withTurnUpdate(current, sessionId, generationId, {
                    turnId: data.turn_id,
                    protocolVersion: 2,
                    recoveryState: 'available',
                    ...(snapshot ? snapshotTurnPatch(snapshot) : {}),
                  }));
                  break;
                }
                case 'phase': {
                  const phase = mapServerPhaseForUi(data.phase);
                  set((current) => withTurnUpdate(current, sessionId, generationId, {
                    phase: phase.streamPhase,
                    safePhase: phase.safePhase,
                  }));
                  break;
                }
                case 'token':
                case 'answer_delta':
                  clearPhaseTimers();
                  // V3.5: Transition to 'streaming' on first token
                  markAnswerStarted();
                  assistantContent += (event.name === 'answer_delta' ? data.text : data.token) || '';
                  // V3.5 HIGH-005: Batch token updates via rAF instead of per-token set()
                  appendToken(
                    sessionId,
                    generationId,
                    (event.name === 'answer_delta' ? data.text : data.token) || '',
                  );
                  break;
                case 'citations':
                  // V4.6 FIX: Reset the no-token stall timer on citations. Citations are
                  // emitted right after retrieval succeeds and just before the LLM starts
                  // producing tokens. Without this reset, the 30s abort timer counts
                  // retrieval time + LLM time-to-first-token together — so a slow-but-working
                  // backend (common when several conversations stream at once on the dev
                  // server) gets falsely aborted into a timeout error before the first token.
                  // Resetting here gives the LLM its own full window for time-to-first-token.
                  set((current) => withTurnUpdate(current, sessionId, generationId, { citations: data }));
                  break;
                case 'quality':
                  set((current) => withTurnUpdate(current, sessionId, generationId, { quality: data }));
                  break;
                case 'usage':
                  applyUsageTimings(data);
                  break;
                case 'done':
                  clearAllTimers();
                  if (sequence !== null) {
                    set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
                  }
                  flushImmediate(sessionId, generationId);
                  commitRegeneratedVersion();
                  get().finishStreamingMessage(data.message_id, data.session_id, generationId);
                  return true;
                case 'error':
                  clearAllTimers();
                  if (sequence !== null) {
                    set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
                  }
                  finishRecoverable('error_generic');
                  return false;
              }
              if (sequence !== null) {
                set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
              }
            }
          }

          if (done) {
            clearAllTimers();
            const recovered = await recoverInterruptedStream();
            if (recovered !== null) return recovered;
            finishRecoverable('error_network');
            return false;
          }
        }
      } catch (error) {
        clearAllTimers();

        // V3.5 CRIT-001: Handle AbortError — stream was intentionally aborted
        if (error instanceof DOMException && error.name === 'AbortError') {
          const isTimeout = abortReason !== null;
          if (abortReason && recoverInterruptedStream
            && get().turnsBySession[sessionId]?.turnId) {
            const recovered = await recoverInterruptedStream();
            if (recovered !== null) return recovered;
          }
          finishRecoverable(isTimeout ? 'error_timeout' : null, isTimeout ? 'error' : 'idle');
          return false;
        }

        console.error('Streaming error:', error);

        // P0-2: Combine streamPhase + sendError into single set() call to prevent
        // a one-frame gap where streamPhase='error' but sendError=null.
        // Previously: set({ streamPhase: 'error' }) → unlockSend() → then set({ sendError })
        // This caused a render frame with error phase but no visible error Alert.
        // Now: single atomic update ensures ChatPage always sees both values together.
        const errorMsg = (error as Error).message;
        let errorKey: string;
        if (errorMsg.includes('deep_unavailable')) {
          errorKey = 'error_deep_unavailable';
        } else if (errorMsg.includes('thinking_unavailable')) {
          errorKey = 'error_thinking_unavailable';
        } else if (errorMsg.includes('401') || errorMsg.includes('403')) {
          errorKey = 'error_auth';
        } else if (errorMsg.includes('500') || errorMsg.includes('502') || errorMsg.includes('503')) {
          errorKey = 'error_server';
        } else if (errorMsg.includes('NetworkError') || errorMsg.includes('fetch') || errorMsg.includes('Failed to fetch')) {
          errorKey = 'error_network';
        } else {
          errorKey = 'error_generic';
        }

        if (recoverInterruptedStream && get().turnsBySession[sessionId]?.turnId) {
          const recovered = await recoverInterruptedStream();
          if (recovered !== null) return recovered;
        }
        finishRecoverable(errorKey);
        return false;
      }
    };

    await streamOnce();
    // V3.6 LOW-001: All terminal paths of streamOnce guarantee unlockSend():
    // - finishStreamingMessage (success + session mismatch)
    // - AbortError handler, timeout handler, SSE error event, request errors
    // - Session creation/validation failures also call unlockSend before returning
    // No safety net needed — removed redundant double-unlock.
  },

  // V3.5 CRIT-002: Verify session ID match before committing stream data
  finishStreamingMessage: (messageId: string, sessionId: string, generationId?: string) => {
    const ownerTurn = get().turnsBySession[sessionId];
    const ownerGeneration = generationId ?? ownerTurn?.generationId;
    if (!ownerTurn || !ownerGeneration || ownerTurn.generationId !== ownerGeneration) return;

    const { content, citations, quality } = ownerTurn;

    const assistantMessage: Message = {
      id: messageId,
      role: 'assistant',
      content,
      citations,
      executionSnapshot: ownerTurn.executionSnapshot ?? LEGACY_UNKNOWN_EXECUTION_SNAPSHOT,
      execution_snapshot: ownerTurn.executionSnapshot ?? LEGACY_UNKNOWN_EXECUTION_SNAPSHOT,
      confidenceScore: quality?.score,
      confidenceLabel: quality?.confidence,
      needsHumanReview: quality?.needs_human_review,
      retrievalMode: quality?.retrieval_mode,
      retrievalLatencyMs: quality?.retrieval_latency_ms,
      createdAt: new Date().toISOString(),
    };

    set((current) => {
      const activeUpdates: Partial<ChatState> = {};
      const ownerMessages = appendUniqueById(
        current.messageCacheBySession[sessionId] ?? [],
        [assistantMessage],
      ).slice(-MAX_ALL_MESSAGES);
      if (current.activeSessionId === sessionId) {
        const newAllMessages = appendUniqueById(current.allMessages, [assistantMessage]);
        const prunedAllMessages = newAllMessages.length > MAX_ALL_MESSAGES
          ? newAllMessages.slice(newAllMessages.length - MAX_ALL_MESSAGES)
          : newAllMessages;
        const rounds = computeRounds(prunedAllMessages);
        const wasPruned = prunedAllMessages.length < newAllMessages.length;
        Object.assign(activeUpdates, {
          messages: extractVisibleMessages(rounds, current.visibleRoundCount),
          allMessages: prunedAllMessages,
          hasOlderMessages: wasPruned ? true : rounds.length > current.visibleRoundCount,
          totalRoundCount: rounds.length,
        });
      }

      return {
        ...activeUpdates,
        messageCacheBySession: {
          ...current.messageCacheBySession,
          [sessionId]: ownerMessages,
        },
        ...withTurnUpdate(current, sessionId, ownerGeneration, {
          phase: 'idle',
          safePhase: null,
          isLocked: false,
          content: '',
          citations: [],
          quality: null,
          error: null,
          aiStatusText: null,
          generationId: null,
          v3Turn: null,
          recoveryState: 'idle',
          timings: {
            ...(ownerTurn.timings ?? {}),
            totalMs: ownerTurn.timings?.totalMs ?? elapsedMs(ownerTurn.startedAtMs),
          },
        }),
      };
    });

    resetTokenBatcher(sessionId, ownerGeneration);
    clearStreamOnComplete(sessionId, ownerGeneration);
    if (get()._pendingSessionRefresh) {
      set({ _pendingSessionRefresh: false });
      get().loadSessions();
    }
  },
}));

export function setAIStatus(text: string | null) {
  useChatStore.getState().setAIStatusText(text);
}

if (typeof window !== 'undefined') {
  (window as any).setAIStatus = setAIStatus;
}

