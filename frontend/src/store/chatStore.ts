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
import { SSEParser } from '../stream/SSEParser';
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
  document_id: string;
  document_title: string;
  page_number?: number;
  score: number;
  quoted_text: string;
}

export interface ChatSession {
  id: string;
  title: string;
  is_active: boolean;
  isPinned: boolean;
  updatedAt: string;
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

export interface SessionTurnState {
  phase: StreamPhase;
  isLocked: boolean;
  content: string;
  citations: Citation[];
  quality: QualityData | null;
  error: string | null;
  aiStatusText: string | null;
  generationId: string | null;
  clientRequestId?: string | null;
  turnId?: string | null;
  lastEventSeq?: number;
  protocolVersion?: 1 | 2 | null;
  recoveryState?: StreamRecoveryState;
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
  sendMessage: (content: string) => Promise<void>;
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
    isLocked: false,
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
    recoveryState: 'idle',
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

  abortSessionStream: (sessionId) => { abortActiveStream(sessionId); },

  removeSessionState: (sessionId) => {
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

  sendMessage: async (content: string) => {
    const state = get();
    let sessionId = state.activeSessionId;
    if (sessionId && state.turnsBySession[sessionId]?.isLocked) return;
    if (!sessionId && state.isSendLocked) return;

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

    const clientRequestId = crypto.randomUUID();
    const generationId = crypto.randomUUID();
    set((current) => withTurnUpdate(current, sessionId, null, {
      phase: 'connecting',
      isLocked: true,
      content: '',
      citations: [],
      quality: null,
      error: null,
      aiStatusText: null,
      generationId,
      clientRequestId,
      turnId: null,
      lastEventSeq: 0,
      protocolVersion: null,
      recoveryState: 'idle',
    }));

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };
    get().addMessage(userMessage);

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

    const finishRecoverable = (error: string | null, phase: StreamPhase = error ? 'error' : 'idle') => {
      flushImmediate(sessionId, generationId);
      const turn = get().turnsBySession[sessionId];
      if (turn?.generationId !== generationId) return;
      saveLocalPartial(turn.content, turn.citations);
      resetTokenBatcher(sessionId, generationId);
      clearStreamOnComplete(sessionId, generationId);
      set((current) => withTurnUpdate(current, sessionId, generationId, {
        phase,
        isLocked: false,
        content: '',
        citations: [],
        quality: null,
        error,
        aiStatusText: null,
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
      let abortReason: 'connection' | 'idle' | null = null;
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
        clearPhaseTimers();
      };

      const isCurrentGeneration = () => (
        get().turnsBySession[sessionId]?.generationId === generationId
      );
      const abortForTimeout = (reason: 'connection' | 'idle') => {
        if (!isCurrentGeneration() || controller.signal.aborted) return;
        abortReason = reason;
        clearAllTimers();
        controller.abort();
      };
      const armEventIdleWatchdog = () => {
        if (eventIdleWatchdog) clearTimeout(eventIdleWatchdog);
        eventIdleWatchdog = setTimeout(() => abortForTimeout('idle'), 30_000);
      };
      let recoverInterruptedStream: (() => Promise<boolean | null>) | null = null;

      try {
        connectionWatchdog = setTimeout(() => abortForTimeout('connection'), 30_000);
        // V3.5 CRIT-001: Pass AbortController signal to fetch
        // V6.0: scope the SSE request to the active space (fetch bypasses the
        // axios interceptor, so set the header explicitly here).
        const spaceId = getActiveSpaceId();
        const sendHeaders: Record<string, string> = {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        };
        if (spaceId) sendHeaders['X-Space-Id'] = spaceId;
        const response = await fetch(`/api/v1/chat/sessions/${sessionId}/send/`, {
          method: 'POST',
          headers: sendHeaders,
          body: JSON.stringify({
            content,
            client_request_id: clientRequestId,
            answer_mode: 'fast',
            protocol_version: 2,
          }),
          signal: controller.signal, // V3.5: AbortController signal
        });

        if (connectionWatchdog) {
          clearTimeout(connectionWatchdog);
          connectionWatchdog = undefined;
        }

        if (!response.ok) {
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
        set((current) => withTurnUpdate(current, sessionId, generationId, { phase: 'searching' }));

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        const parser = new SSEParser();
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
            }, 5_000);
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
              const replayTurnId: string = replayResponse.headers?.get?.('X-Chat-Turn-Id') || turn.turnId;
              const replayClientId = replayResponse.headers?.get?.('X-Chat-Client-Request-Id') || clientRequestId;
              if (replayTurnId !== turn.turnId || replayClientId !== clientRequestId) {
                finishRecoverable('error_generic');
                set((current) => withTurnUpdate(current, sessionId, generationId, { recoveryState: 'failed' }));
                return false;
              }

              const replayReader = replayResponse.body?.getReader();
              if (!replayReader) throw new Error('missing recovery stream');
              const replayParser = new SSEParser();
              const replayDecoder = new TextDecoder();
              while (true) {
                const { done, value } = await replayReader.read();
                const replayMessages = done
                  ? [...replayParser.feed(replayDecoder.decode()), ...replayParser.end()]
                  : replayParser.feed(replayDecoder.decode(value, { stream: true }));
                for (const message of replayMessages) {
                  if (get().turnsBySession[sessionId]?.generationId !== generationId) return false;
                  const sequence = message.id && /^\d+$/.test(message.id) ? Number(message.id) : null;
                  if (sequence === null || sequence <= (get().turnsBySession[sessionId]?.lastEventSeq ?? 0)) {
                    continue;
                  }
                  const data = JSON.parse(message.data);
                  switch (message.event) {
                    case 'meta':
                      if (data.turn_id !== turn.turnId
                        || data.session_id !== sessionId
                        || data.client_request_id !== clientRequestId
                        || data.protocol_version !== 2) {
                        finishRecoverable('error_generic');
                        set((current) => withTurnUpdate(current, sessionId, generationId, { recoveryState: 'failed' }));
                        return false;
                      }
                      break;
                    case 'phase':
                      set((current) => withTurnUpdate(current, sessionId, generationId, {
                        phase: data.phase === 'answering' ? 'streaming' : data.phase === 'saving' ? 'completing' : 'searching',
                      }));
                      break;
                    case 'answer_delta':
                      set((current) => withTurnUpdate(current, sessionId, generationId, { phase: 'streaming' }));
                      assistantContent += data.text || '';
                      appendToken(sessionId, generationId, data.text || '');
                      break;
                    case 'citations':
                      set((current) => withTurnUpdate(current, sessionId, generationId, { citations: data }));
                      break;
                    case 'quality':
                      set((current) => withTurnUpdate(current, sessionId, generationId, { quality: data }));
                      break;
                    case 'done':
                      if (data.session_id !== sessionId
                        || (data.turn_id && data.turn_id !== turn.turnId)
                        || (data.client_request_id && data.client_request_id !== clientRequestId)) {
                        finishRecoverable('error_generic');
                        set((current) => withTurnUpdate(current, sessionId, generationId, { recoveryState: 'failed' }));
                        return false;
                      }
                      set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
                      flushImmediate(sessionId, generationId);
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
                  quality: {
                    confidence: answer.confidenceLabel ?? '',
                    score: answer.confidenceScore ?? 0,
                    needs_human_review: answer.needsHumanReview ?? false,
                    retrieval_mode: answer.retrievalMode ?? '',
                    retrieval_latency_ms: answer.retrievalLatencyMs ?? 0,
                  },
                }));
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
            : [
                ...parser.feed(decoder.decode(value, { stream: true })),
                ...parser.flushLegacyEvent(),
              ];

          for (const message of messages) {
            armEventIdleWatchdog();
            const sequence = message.id && /^\d+$/.test(message.id) ? Number(message.id) : null;
            const currentTurn = get().turnsBySession[sessionId];
            if (sequence !== null && sequence <= (currentTurn?.lastEventSeq ?? 0)) continue;
            const data = JSON.parse(message.data);
            {
              switch (message.event) {
                case 'meta': {
                  const knownTurnId = get().turnsBySession[sessionId]?.turnId;
                  if (data.protocol_version !== 2
                    || data.session_id !== sessionId
                    || data.client_request_id !== clientRequestId
                    || (knownTurnId && data.turn_id !== knownTurnId)) {
                    finishRecoverable('error_generic');
                    return false;
                  }
                  set((current) => withTurnUpdate(current, sessionId, generationId, {
                    turnId: data.turn_id,
                    protocolVersion: 2,
                    recoveryState: 'available',
                  }));
                  break;
                }
                case 'phase': {
                  const phase: StreamPhase = data.phase === 'answering'
                    ? 'streaming'
                    : data.phase === 'saving'
                      ? 'completing'
                      : 'searching';
                  set((current) => withTurnUpdate(current, sessionId, generationId, { phase }));
                  break;
                }
                case 'token':
                case 'answer_delta':
                  if (get().turnsBySession[sessionId]?.protocolVersion === null) {
                    set((current) => withTurnUpdate(current, sessionId, generationId, {
                      protocolVersion: message.event === 'answer_delta' ? 2 : 1,
                    }));
                  }
                  clearPhaseTimers();
                  // V3.5: Transition to 'streaming' on first token
                  if (get().turnsBySession[sessionId]?.phase !== 'streaming') {
                    set((current) => withTurnUpdate(current, sessionId, generationId, { phase: 'streaming' }));
                  }
                  assistantContent += (message.event === 'answer_delta' ? data.text : data.token) || '';
                  // V3.5 HIGH-005: Batch token updates via rAF instead of per-token set()
                  appendToken(
                    sessionId,
                    generationId,
                    (message.event === 'answer_delta' ? data.text : data.token) || '',
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
                  break;
                case 'done':
                  clearAllTimers();
                  if (data.session_id !== sessionId
                    || (data.turn_id && data.turn_id !== get().turnsBySession[sessionId]?.turnId)
                    || (data.client_request_id && data.client_request_id !== clientRequestId)) {
                    finishRecoverable('error_generic');
                    return false;
                  }
                  if (sequence !== null) {
                    set((current) => withTurnUpdate(current, sessionId, generationId, { lastEventSeq: sequence }));
                  }
                  flushImmediate(sessionId, generationId);
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
          if (abortReason === 'idle' && recoverInterruptedStream) {
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
        if (errorMsg.includes('401') || errorMsg.includes('403')) {
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
          isLocked: false,
          content: '',
          citations: [],
          quality: null,
          error: null,
          aiStatusText: null,
          generationId: null,
          recoveryState: 'idle',
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

