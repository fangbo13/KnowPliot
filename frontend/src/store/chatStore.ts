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

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: Message[];
  isStreaming: boolean;
  streamContent: string;
  citations: Citation[];
  isLoadingMessages: boolean;
  sendError: string | null;

  // Actions
  setActiveSession: (id: string) => void;
  addMessage: (message: Message) => void;
  updateStreamContent: (content: string) => void;
  setStreaming: (isStreaming: boolean) => void;
  setStreamCitations: (citations: Citation[]) => void;
  setSendError: (error: string | null) => void;
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

  setActiveSession: (id) => set({ activeSessionId: id, messages: [], sendError: null }),

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message],
  })),

  updateStreamContent: (content) => set({ streamContent: content }),

  setStreaming: (isStreaming) => set({ isStreaming, streamContent: '', citations: [] }),

  setStreamCitations: (citations) => set({ citations }),

  setSendError: (sendError) => set({ sendError }),

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

    let sessionId = activeSessionId;
    if (!sessionId) {
      try {
        const newSession = await chatApi.createSession({ title: content.slice(0, 50) });
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

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let assistantContent = '';
        let currentEvent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

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
                  assistantContent += data.token || '';
                  get().updateStreamContent(assistantContent);
                  break;
                case 'citations':
                  get().setStreamCitations(data);
                  break;
                case 'done':
                  get().finishStreamingMessage(data.message_id, data.session_id);
                  return true;
                case 'error':
                  console.error('Stream error:', data.error);
                  get().setStreaming(false);
                  set({ sendError: data.error || 'Stream error occurred' });
                  return false;
              }
            }
          }
        }
        return true;
      } catch (error) {
        console.error(`Streaming error (attempt ${attempt + 1}):`, error);
        if (attempt < maxRetries) {
          const delay = (attempt + 1) * 1000;
          await new Promise((resolve) => setTimeout(resolve, delay));
          return streamWithRetry(attempt + 1);
        }
        get().setStreaming(false);
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
