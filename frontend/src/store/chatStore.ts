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

  // Actions
  setActiveSession: (id: string) => void;
  addMessage: (message: Message) => void;
  updateStreamContent: (content: string) => void;
  setStreaming: (isStreaming: boolean) => void;
  setStreamCitations: (citations: Citation[]) => void;
  loadSessions: () => Promise<void>;
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

  setActiveSession: (id) => set({ activeSessionId: id, messages: [] }),

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message],
  })),

  updateStreamContent: (content) => set({ streamContent: content }),

  setStreaming: (isStreaming) => set({ isStreaming, streamContent: '', citations: [] }),

  setStreamCitations: (citations) => set({ citations }),

  loadSessions: async () => {
    try {
      const sessions = await chatApi.getSessions();
      set({ sessions });
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  },

  sendMessage: async (content: string) => {
    const { activeSessionId, isStreaming } = get();

    // Prevent double-send (race condition fix M-02)
    if (isStreaming) return;

    // Set streaming BEFORE any async work (race condition fix M-02)
    get().setStreaming(true);

    // Create a new session if none exists
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
        get().setStreaming(false);
        return;
      }
    }

    // Add user message
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };
    get().addMessage(userMessage);

    // SSE connection with retry (H-01)
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
                  return false;
              }
            }
          }
        }
        return true;
      } catch (error) {
        console.error(`Streaming error (attempt ${attempt + 1}):`, error);
        if (attempt < maxRetries) {
          // Wait with exponential backoff before retry
          const delay = (attempt + 1) * 1000;
          await new Promise((resolve) => setTimeout(resolve, delay));
          return streamWithRetry(attempt + 1);
        }
        // All retries exhausted
        get().setStreaming(false);
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

    // Reload sessions to update the list
    get().loadSessions();
  },
}));
