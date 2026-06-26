import { create } from 'zustand';
import { chatApi } from '../api/chat';
import { getAuthToken } from '../api/client';
import {
  createStreamAbortController,
  abortActiveStream,
  clearStreamOnComplete,
} from '../stream/StreamLifecycleManager';
import { initTokenBatcher, appendToken, flushImmediate, resetTokenBatcher } from '../stream/TokenBatchRenderer';
// V4.0 DEFECT-008: BroadcastChannel cross-tab sync
import { broadcastSessionSwitch } from '../sync/crossTabSync';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: Citation[];
  createdAt: string;
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
type StreamPhase = 'idle' | 'connecting' | 'searching' | 'streaming' | 'completing' | 'error';

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: Message[];
  // V3.5: allMessages holds full history for sliding window; messages is the visible slice
  allMessages: Message[];
  visibleRoundCount: number;
  hasOlderMessages: boolean;
  // V3.6 MED-003: Cached round count — avoids O(n) recomputation per message
  totalRoundCount: number;
  // V3.5: Unified stream phase replaces three separate fields
  streamPhase: StreamPhase;
  streamContent: string;
  citations: Citation[];
  isLoadingMessages: boolean;
  sendError: string | null;
  // V3.5: Send lock to prevent double-send during async gap
  isSendLocked: boolean;
  // V3.6 HIGH-002: Flag to refresh session list only after new session creation
  _pendingSessionRefresh: boolean;
  // V4.1 BUG-003: Flag to differentiate timeout abort from user-intentional abort.
  // Set by abortInterval before controller.abort(), checked by AbortError handler.
  // When true: show timeout error toast + preserve truncated content.
  // When false (user abort / Stop button): preserve content silently, no error toast.
  _isTimeoutAbort: boolean;

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
  loadSessions: () => Promise<void>;
  loadMessages: (sessionId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  finishStreamingMessage: (messageId: string, sessionId: string) => void;
  loadOlderRounds: (count: number) => void;
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

const DEFAULT_VISIBLE_ROUNDS = 10;
// V3.6 MED-001 / V3.7 P1.3: Hard cap on allMessages to prevent unbounded memory growth
// V3.7: Reduced from 500 to 100 — 100 messages ≈ 50 rounds of conversation,
// sufficient for most use cases while keeping JS Heap stable.
// Messages beyond this cap are pruned from front and can be loaded via "load older".
const MAX_ALL_MESSAGES = 100;

export const useChatStore = create<ChatState>()((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  allMessages: [],
  visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
  hasOlderMessages: false,
  totalRoundCount: 0,
  // V3.5: Unified stream phase (replaces isStreaming/thinkingPhase/connectionStatus)
  streamPhase: 'idle',
  streamContent: '',
  citations: [],
  isLoadingMessages: false,
  sendError: null,
  isSendLocked: false,
  _pendingSessionRefresh: false,
  _isTimeoutAbort: false,

  // V3.5 CRIT-002: setActiveSession now aborts old stream + resets isStreaming
  setActiveSession: (id) => {
    abortActiveStream(); // Kill old stream to prevent data pollution
    resetTokenBatcher(); // Clear any pending token buffer
    broadcastSessionSwitch(id); // V4.0 DEFECT-008: notify other tabs of session switch
    set({
      activeSessionId: id,
      messages: [],
      allMessages: [],
      sendError: null,
      streamPhase: 'idle',
      streamContent: '',
      citations: [],
      hasOlderMessages: false,
      totalRoundCount: 0,
      visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
      _pendingSessionRefresh: false,
      _isTimeoutAbort: false,
    });
  },

  // V3.5 CRIT-002: resetSession now aborts old stream
  resetSession: () => {
    abortActiveStream(); // Kill stream on new chat
    resetTokenBatcher();
    broadcastSessionSwitch(null); // V4.0 DEFECT-008: notify other tabs (null = no active session)
    set({
      activeSessionId: null,
      messages: [],
      allMessages: [],
      streamContent: '',
      citations: [],
      streamPhase: 'idle',
      sendError: null,
      hasOlderMessages: false,
      totalRoundCount: 0,
      visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
      _pendingSessionRefresh: false,
      _isTimeoutAbort: false,
    });
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
      };
    }
    const newMessages = [...state.messages, message];
    return {
      messages: newMessages,
      allMessages: newAllMessages,
    };
  }),

  updateStreamContent: (content) => set({ streamContent: content }),

  setStreamCitations: (citations) => set({ citations }),

  setSendError: (sendError) => set({ sendError }),

  // V3.5: Stream phase transitions
  setStreamPhase: (phase) => set({ streamPhase: phase }),

  // V3.5 HIGH-001: Send lock mechanism
  lockSend: () => set({ isSendLocked: true }),
  // V3.6 LOW-001: Add dev-only warning for double-unlock detection
  unlockSend: () => {
    if (!get().isSendLocked) {
      console.warn('[chatStore] unlockSend called when isSendLocked is already false — possible double-unlock');
    }
    set({ isSendLocked: false });
  },

  loadSessions: async () => {
    try {
      const sessions = await chatApi.getSessions();
      set({ sessions });
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  },

  loadMessages: async (sessionId: string) => {
    set({ isLoadingMessages: true, sendError: null });
    try {
      const msgs = await chatApi.getMessages(sessionId);
      const allMessages: Message[] = msgs.map((m: any) => ({
        id: m.id || crypto.randomUUID(),
        role: m.role,
        content: m.content || '',
        citations: m.citations || [],
        createdAt: m.created_at || m.createdAt || new Date().toISOString(),
      }));

      // V3.5: Sliding window — compute rounds, extract visible slice
      const rounds = computeRounds(allMessages);
      const visibleMessages = extractVisibleMessages(rounds, DEFAULT_VISIBLE_ROUNDS);
      const hasOlder = rounds.length > DEFAULT_VISIBLE_ROUNDS;

      set({
        activeSessionId: sessionId,
        allMessages,
        messages: visibleMessages,
        hasOlderMessages: hasOlder,
        visibleRoundCount: DEFAULT_VISIBLE_ROUNDS,
        isLoadingMessages: false,
        // V3.6 MED-003: Cache round count for efficient hasOlderMessages checks
        totalRoundCount: rounds.length,
      });
    } catch (error) {
      console.error('Failed to load messages:', error);
      // V3.6 MED-002: Use i18n error key instead of raw string
      set({ isLoadingMessages: false, sendError: 'error_session' });
    }
  },

  // V3.5: Load older rounds (expand sliding window)
  // V3.6 MED-003: Use cached totalRoundCount for hasOlderMessages comparison
  loadOlderRounds: (count: number) => {
    const { allMessages, visibleRoundCount, totalRoundCount } = get();
    const rounds = computeRounds(allMessages);
    const newVisibleCount = Math.min(visibleRoundCount + count, totalRoundCount);
    const visibleMessages = extractVisibleMessages(rounds, newVisibleCount);
    set({
      messages: visibleMessages,
      visibleRoundCount: newVisibleCount,
      hasOlderMessages: newVisibleCount < totalRoundCount,
    });
  },

  sendMessage: async (content: string) => {
    // V4.1 BUG-002: Atomic check+lock — combine streamPhase/isSendLocked check and
    // lock into a single synchronous set() call to eliminate the gap between read and lock.
    // Previously: get().streamPhase + get().isSendLocked check → get().lockSend() → set()
    // This gap allowed double-click to fire two sendMessage calls within one render frame.
    // Now: single set({ isSendLocked: true, streamPhase: 'connecting' }) if conditions met.
    // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-002]
    const state = get();
    if (state.streamPhase !== 'idle' || state.isSendLocked) return;

    // Atomic lock: check + lock in one synchronous operation (no gap between read and write)
    set({ isSendLocked: true, sendError: null, streamPhase: 'connecting' });

    let sessionId = get().activeSessionId;
    if (!sessionId) {
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
        set({ streamPhase: 'idle', sendError: 'error_session' });
        get().unlockSend();
        return;
      }
    } else {
      // Validate sessionId format (M6: security enhancement)
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(sessionId)) {
        set({ streamPhase: 'idle', sendError: 'error_session' });
        get().unlockSend();
        return;
      }
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };
    get().addMessage(userMessage);

    const token = getAuthToken();
    const maxRetries = 2;

    // V3.5: Initialize token batch renderer for this stream
    // V4.2 SYS-V4.2-015: Changed from (fullContent: string) to incremental diff mode.
    // appendTokens mode: only passes new tokens → Zustand appends to existing streamContent
    // fullContent mode: passes complete string → Zustand replaces streamContent (for flushImmediate)
    initTokenBatcher((update: { appendTokens: string } | { fullContent: string }) => {
      if ('appendTokens' in update) {
        // V4.2 SYS-V4.2-015: Incremental append — reduces per-frame GC pressure
        set(state => ({ streamContent: state.streamContent + update.appendTokens }));
      } else {
        // V4.2 SYS-V4.2-015: Full content replacement (for flushImmediate on done/error/abort)
        set({ streamContent: update.fullContent });
      }
    });

    const streamWithRetry = async (attempt: number): Promise<boolean> => {
      // V3.5 CRIT-001: Create/recreate AbortController per attempt
      // On retry > 0, the old controller was aborted, so we need a fresh one
      const controller = createStreamAbortController(sessionId);

      // Progressive thinking phases + connection status tracking
      let abortInterval: ReturnType<typeof setInterval> | undefined;
      let phaseTimerSearching: ReturnType<typeof setTimeout> | undefined;
      let phaseTimerGenerating: ReturnType<typeof setTimeout> | undefined;

      const clearAllTimers = () => {
        if (abortInterval) clearInterval(abortInterval);
        if (phaseTimerSearching) clearTimeout(phaseTimerSearching);
        if (phaseTimerGenerating) clearTimeout(phaseTimerGenerating);
      };

      try {
        // V3.5 CRIT-001: Pass AbortController signal to fetch
        const response = await fetch(`/api/v1/chat/sessions/${sessionId}/send/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ content }),
          signal: controller.signal, // V3.5: AbortController signal
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        // Headers received — connection established → 'searching' phase
        set({ streamPhase: 'searching' });

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let assistantContent = '';
        let currentEvent = '';

        // Progressive thinking phase timers
        let lastTokenTime = Date.now();
        const ABORT_THRESHOLD = 30000; // 30s — abort stream

        // Phase 1: After 3s of no tokens → "searching" phase (already set on connection)
        phaseTimerSearching = setTimeout(() => {
          if (get().streamPhase === 'connecting') {
            set({ streamPhase: 'searching' });
          }
        }, 3000);

        // Phase 2: After 8s of no tokens → "streaming" phase indicator
        phaseTimerGenerating = setTimeout(() => {
          if (get().streamPhase === 'searching' && !assistantContent) {
            // Still waiting — keep in searching but indicate long retrieval
          }
        }, 8000);

        // Abort timer: cancel stream if no tokens for 30s
        // V4.1 BUG-003: Route abort through AbortController.abort() instead of reader.cancel().
        // reader.cancel() throws DOMException with error.name !== 'AbortError', so the catch
        // block on line ~510 does NOT match the AbortError branch. This means the preserved
        // content logic never fires for timeout-induced aborts, and truncated content is lost.
        // controller.abort() causes reader.read() to throw a proper AbortError, which IS
        // caught by the correct branch that preserves truncated content.
        // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-003]
        abortInterval = setInterval(() => {
          const elapsed = Date.now() - lastTokenTime;
          if (elapsed > ABORT_THRESHOLD && get().streamPhase !== 'idle') {
            clearAllTimers();
            // V4.1 BUG-003: Mark this as a timeout abort so the AbortError handler
            // can show appropriate feedback (timeout error toast) vs user-intentional abort
            // (Stop button — silent, preserves truncated content).
            set({ _isTimeoutAbort: true });
            controller.abort(); // V4.1 BUG-003: Use AbortController instead of reader.cancel()
            // No inline cleanup needed — AbortError catch branch will handle:
            // flushImmediate() + clearStreamOnComplete() + truncated content preservation + unlockSend
          }
        }, 3000);

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            clearAllTimers();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7);
            } else if (line.startsWith('data: ')) {
              const data = JSON.parse(line.slice(6));
              switch (currentEvent) {
                case 'token':
                  lastTokenTime = Date.now();
                  clearAllTimers();
                  // V3.5: Transition to 'streaming' on first token
                  if (get().streamPhase !== 'streaming') {
                    set({ streamPhase: 'streaming' });
                  }
                  assistantContent += data.token || '';
                  // V3.5 HIGH-005: Batch token updates via rAF instead of per-token set()
                  appendToken(data.token);
                  break;
                case 'citations':
                  get().setStreamCitations(data);
                  break;
                case 'done':
                  clearAllTimers();
                  flushImmediate(); // V3.5: Force flush remaining buffered tokens
                  get().finishStreamingMessage(data.message_id, data.session_id);
                  return true;
                case 'error':
                  clearAllTimers();
                  flushImmediate();
                  // V3.6 MED-002: Use consistent i18n error key instead of raw server string
                  set({ streamPhase: 'error', sendError: 'error_generic' });
                  get().unlockSend();
                  // Reset to idle after error is shown
                  setTimeout(() => set({ streamPhase: 'idle' }), 100);
                  return false;
              }
            }
          }
        }
        clearAllTimers();
        return true;
      } catch (error) {
        clearAllTimers();

        // V3.5 CRIT-001: Handle AbortError — stream was intentionally aborted
        if (error instanceof DOMException && error.name === 'AbortError') {
          // V4.1 BUG-003: Differentiate timeout abort vs user-intentional abort (Stop button).
          // Timeout abort: controller.abort() called by abortInterval → show timeout error toast.
          // User abort: abortActiveStream() called by Stop button → preserve content silently.
          const isTimeout = get()._isTimeoutAbort;

          // V4.0 UI-HIGH-001: Preserve already-output content as a truncated message
          // instead of discarding it. This supports both "Stop Generation" button and
          // timeout aborts — the partial AI response should remain visible.
          flushImmediate();
          clearStreamOnComplete();
          const preservedContent = get().streamContent;
          const preservedCitations = get().citations;
          if (preservedContent && preservedContent.trim()) {
            const truncatedMessage: Message = {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: preservedContent,
              citations: preservedCitations,
              createdAt: new Date().toISOString(),
            };
            get().addMessage(truncatedMessage);
          }
          // V4.1 BUG-003: Clear timeout flag after processing
          set({
            streamPhase: isTimeout ? 'error' : 'idle',
            streamContent: '',
            citations: [],
            sendError: isTimeout ? 'error_timeout' : null,
            _isTimeoutAbort: false,
          });
          get().unlockSend();
          // For timeout, reset to idle after error is shown
          if (isTimeout) {
            setTimeout(() => set({ streamPhase: 'idle' }), 100);
          }
          return false; // Return false but don't treat as error
        }

        console.error(`Streaming error (attempt ${attempt + 1}):`, error);
        if (attempt < maxRetries) {
          const delay = (attempt + 1) * 1000;
          await new Promise((resolve) => setTimeout(resolve, delay));
          return streamWithRetry(attempt + 1);
        }

        flushImmediate();

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

        set({ streamPhase: 'error', sendError: errorKey });
        get().unlockSend();

        // Reset to idle after error is shown
        setTimeout(() => set({ streamPhase: 'idle' }), 100);
        return false;
      }
    };

    await streamWithRetry(0);
    // V3.6 LOW-001: All terminal paths of streamWithRetry guarantee unlockSend():
    // - finishStreamingMessage (success + session mismatch)
    // - AbortError handler, timeout handler, SSE error event, exhausted retries
    // - Session creation/validation failures also call unlockSend before returning
    // No safety net needed — removed redundant double-unlock.
  },

  // V3.5 CRIT-002: Verify session ID match before committing stream data
  finishStreamingMessage: (messageId: string, sessionId: string) => {
    const currentSessionId = get().activeSessionId;

    // Session mismatch: stream data belongs to a different session
    // (user switched sessions while stream was running)
    if (currentSessionId !== sessionId) {
      // Discard stale stream data, clean up
      set({ streamPhase: 'idle', streamContent: '', citations: [], totalRoundCount: 0 });
      clearStreamOnComplete();
      get().unlockSend();
      return;
    }

    const { streamContent, citations } = get();

    const assistantMessage: Message = {
      id: messageId,
      role: 'assistant',
      content: streamContent,
      citations,
      createdAt: new Date().toISOString(),
    };

    // V3.5: Update both messages (visible slice) and allMessages (full history)
    const newAllMessages = [...get().allMessages, assistantMessage];
    // V3.6 MED-001 / V3.7 P1.3: Prune front if exceeding MAX cap — prevents unbounded memory growth
    const prunedAllMessages = newAllMessages.length > MAX_ALL_MESSAGES
      ? newAllMessages.slice(newAllMessages.length - MAX_ALL_MESSAGES)
      : newAllMessages;
    const rounds = computeRounds(prunedAllMessages);
    const visibleMessages = extractVisibleMessages(rounds, get().visibleRoundCount);
    const wasPruned = prunedAllMessages.length < newAllMessages.length;

    // V3.7 P1.3: Verification log — proves memory is capped during testing
    // Dev-only: can be removed before production release
    console.log(`[V3.7 P1.3] finishStreamingMessage: allMessages=${prunedAllMessages.length} (cap=${MAX_ALL_MESSAGES}), visibleMessages=${visibleMessages.length}, wasPruned=${wasPruned}`);

    set({
      messages: visibleMessages,
      allMessages: prunedAllMessages,
      streamPhase: 'idle',
      streamContent: '',
      citations: [],
      // V3.6 MED-001: If pruned, older data exists on server → always show "load older"
      hasOlderMessages: wasPruned ? true : rounds.length > get().visibleRoundCount,
      // V3.6 MED-003: Cache round count for efficient hasOlderMessages checks
      totalRoundCount: rounds.length,
    });

    clearStreamOnComplete();
    get().unlockSend();
    // V3.6 HIGH-002: Only refresh sessions after new session creation (not every message)
    if (get()._pendingSessionRefresh) {
      set({ _pendingSessionRefresh: false });
      get().loadSessions();
    }
  },
}));
