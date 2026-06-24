import { create } from 'zustand';
import { chatApi } from '../api/chat';
import { getAuthToken } from '../api/client';

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

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: Message[];
  isStreaming: boolean;
  streamContent: string;
  citations: Citation[];
  isLoadingMessages: boolean;
  sendError: string | null;
  // P0-1/P0-2: Progressive thinking indicator & SSE connection feedback
  thinkingPhase: 'connecting' | 'searching' | 'generating';
  connectionStatus: 'idle' | 'connecting' | 'streaming' | 'error' | 'fallback';

  // Actions
  setActiveSession: (id: string) => void;
  resetSession: () => void;
  addMessage: (message: Message) => void;
  updateStreamContent: (content: string) => void;
  setStreaming: (isStreaming: boolean) => void;
  setStreamCitations: (citations: Citation[]) => void;
  setSendError: (error: string | null) => void;
  setThinkingPhase: (phase: 'connecting' | 'searching' | 'generating') => void;
  setConnectionStatus: (status: 'idle' | 'connecting' | 'streaming' | 'error' | 'fallback') => void;
  loadSessions: () => Promise<void>;
  loadMessages: (sessionId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  finishStreamingMessage: (messageId: string, sessionId: string) => void;
}

export const useChatStore = create<ChatState>()((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  isStreaming: false,
  streamContent: '',
  citations: [],
  isLoadingMessages: false,
  sendError: null,
  thinkingPhase: 'connecting',
  connectionStatus: 'idle',

  setActiveSession: (id) => set({ activeSessionId: id, messages: [], sendError: null }),

  resetSession: () => set({ activeSessionId: null, messages: [], streamContent: '', citations: [], isStreaming: false, sendError: null }),

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message],
  })),

  updateStreamContent: (content) => set({ streamContent: content }),

  setStreaming: (isStreaming) => set({
    isStreaming,
    streamContent: '',
    citations: [],
    // P0-1/P0-2: reset connection state when streaming ends
    ...(isStreaming ? {} : { thinkingPhase: 'connecting', connectionStatus: 'idle' }),
  }),

  setStreamCitations: (citations) => set({ citations }),

  setSendError: (sendError) => set({ sendError }),

  setThinkingPhase: (phase) => set({ thinkingPhase: phase }),
  setConnectionStatus: (status) => set({ connectionStatus: status }),

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
      const messages: Message[] = msgs.map((m: any) => ({
        id: m.id || crypto.randomUUID(),
        role: m.role,
        content: m.content || '',
        citations: m.citations || [],
        createdAt: m.created_at || m.createdAt || new Date().toISOString(),
      }));
      set({ activeSessionId: sessionId, messages, isLoadingMessages: false });
    } catch (error) {
      console.error('Failed to load messages:', error);
      set({ isLoadingMessages: false, sendError: 'Failed to load messages' });
    }
  },

  sendMessage: async (content: string) => {
    const { activeSessionId, isStreaming } = get();

    if (isStreaming) return;

    set({ sendError: null });
    get().setStreaming(true);
    // P0-1/P0-2: Instant feedback — show thinking indicator immediately, not after 10s
    get().setThinkingPhase('connecting');
    get().setConnectionStatus('connecting');

    let sessionId = activeSessionId;
    if (!sessionId) {
      try {
        const newSession = await chatApi.createSession({ title: generateSmartTitle(content) });
        sessionId = newSession.id;
        set({
          activeSessionId: sessionId,
          sessions: [newSession, ...get().sessions],
        });
      } catch (error) {
        console.error('Failed to create session:', error);
        set({ isStreaming: false, sendError: 'Failed to start conversation' });
        return;
      }
    } else {
      // Validate sessionId format (M6: security enhancement)
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(sessionId)) {
        set({ isStreaming: false, sendError: 'Invalid session ID format' });
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

    const streamWithRetry = async (attempt: number): Promise<boolean> => {
      // P0-1/P0-2: Progressive thinking phases + connection status tracking
      // Replaces old 10s THINKING_THRESHOLD + thinkingShown injection into streamContent
      let abortInterval: ReturnType<typeof setInterval> | undefined;
      let phaseTimerSearching: ReturnType<typeof setTimeout> | undefined;
      let phaseTimerGenerating: ReturnType<typeof setTimeout> | undefined;
      let fallbackTimer: ReturnType<typeof setTimeout> | undefined;

      const clearAllTimers = () => {
        if (abortInterval) clearInterval(abortInterval);
        if (phaseTimerSearching) clearTimeout(phaseTimerSearching);
        if (phaseTimerGenerating) clearTimeout(phaseTimerGenerating);
        if (fallbackTimer) clearTimeout(fallbackTimer);
      };

      try {
        const response = await fetch(`/api/v1/chat/sessions/${sessionId}/send/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ content }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        // P0-2: Headers received — connection established
        get().setConnectionStatus('streaming');

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let assistantContent = '';
        let currentEvent = '';

        // P0-1/P0-2: Progressive thinking phase timers
        let lastTokenTime = Date.now();
        const ABORT_THRESHOLD = 30000; // 30s — abort stream (unchanged)

        // Phase 1: After 3s of no tokens → "searching" phase
        phaseTimerSearching = setTimeout(() => {
          if (get().isStreaming && get().thinkingPhase === 'connecting') {
            get().setThinkingPhase('searching');
          }
        }, 3000);

        // Phase 2: After 8s of no tokens → "generating" phase
        phaseTimerGenerating = setTimeout(() => {
          if (get().isStreaming && get().thinkingPhase === 'searching') {
            get().setThinkingPhase('generating');
          }
        }, 8000);

        // P0-2: Fallback detection — if 5s with no tokens after connection, indicate slow connection
        fallbackTimer = setTimeout(() => {
          if (get().isStreaming && get().connectionStatus === 'streaming' && !assistantContent) {
            get().setConnectionStatus('fallback');
            get().setThinkingPhase('searching'); // Skip to more informative phase
          }
        }, 5000);

        // Abort timer: cancel stream if no tokens for 30s
        abortInterval = setInterval(() => {
          const elapsed = Date.now() - lastTokenTime;
          if (elapsed > ABORT_THRESHOLD && get().isStreaming) {
            clearAllTimers();
            reader.cancel();
            get().setStreaming(false);
            get().setConnectionStatus('error');
            set({ sendError: 'Stream timed out — no response for 30 seconds' });
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
                  // P0-1: First token received — clear all timers and thinking state
                  clearAllTimers();
                  assistantContent += data.token || '';
                  get().updateStreamContent(assistantContent);
                  break;
                case 'citations':
                  get().setStreamCitations(data);
                  break;
                case 'done':
                  clearAllTimers();
                  get().setConnectionStatus('idle');
                  get().finishStreamingMessage(data.message_id, data.session_id);
                  return true;
                case 'error':
                  clearAllTimers();
                  get().setConnectionStatus('error');
                  console.error('Stream error:', data.error);
                  get().setStreaming(false);
                  set({ sendError: data.error || 'Stream error occurred' });
                  return false;
              }
            }
          }
        }
        clearAllTimers();
        return true;
      } catch (error) {
        clearAllTimers();
        console.error(`Streaming error (attempt ${attempt + 1}):`, error);
        if (attempt < maxRetries) {
          const delay = (attempt + 1) * 1000;
          await new Promise((resolve) => setTimeout(resolve, delay));
          return streamWithRetry(attempt + 1);
        }
        get().setStreaming(false);
        get().setConnectionStatus('error');
        const errorMsg = (error as Error).message;
        if (errorMsg.includes('401') || errorMsg.includes('403')) {
          set({ sendError: 'error_auth' });
        } else if (errorMsg.includes('500') || errorMsg.includes('502') || errorMsg.includes('503')) {
          set({ sendError: 'error_server' });
        } else if (errorMsg.includes('NetworkError') || errorMsg.includes('fetch') || errorMsg.includes('Failed to fetch')) {
          set({ sendError: 'error_network' });
        } else {
          set({ sendError: 'error_generic' });
        }
        return false;
      }
    };

    await streamWithRetry(0);
  },

  finishStreamingMessage: (messageId: string, _sessionId: string) => {
    const { streamContent, citations } = get();

    const assistantMessage: Message = {
      id: messageId,
      role: 'assistant',
      content: streamContent,
      citations,
      createdAt: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, assistantMessage],
      isStreaming: false,
      streamContent: '',
      citations: [],
    }));

    get().loadSessions();
  },
}));
