import { useTranslation } from 'react-i18next';
import { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Input, Button, Space, Alert, type InputRef, message as antMessage } from 'antd';
const { TextArea } = Input;
import { SendOutlined, ReloadOutlined, DownOutlined } from '@ant-design/icons';
import { useChatStore } from '../store/chatStore';
import WelcomeScreen from '../components/chat/WelcomeScreen';
import VirtualizedMessageList from '../components/chat/VirtualizedMessageList';

// P0-4: Online status tracking for send button disable
function useOnlineStatus() {
  const [isOnline, setIsOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const onOnline = () => setIsOnline(true);
    const onOffline = () => setIsOnline(false);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);
  return isOnline;
}

// Throttle helper for scroll optimization
function throttle<T extends (...args: any[]) => void>(fn: T, limit: number): T {
  let inThrottle = false;
  return ((...args: Parameters<T>) => {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      setTimeout(() => { inThrottle = false; }, limit);
    }
  }) as T;
}

/**
 * P1-8: Clip text at sentence boundary for better screen reader experience.
 * Instead of hard slice(-100), find the last sentence boundary (period,
 * question mark, exclamation, or newline) and truncate there.
 */
function clipForScreenReader(text: string, maxLength: number = 100): string {
  if (text.length <= maxLength) return text;
  const truncated = text.slice(-maxLength);
  // Find the last sentence boundary
  const boundaryMatch = truncated.search(/[.!?？。\n]/);
  if (boundaryMatch > 0 && boundaryMatch < truncated.length - 5) {
    return truncated.slice(boundaryMatch + 1);
  }
  return truncated;
}

export default function ChatPageContainer() {
  const { t } = useTranslation('chat');
  const location = useLocation();
  const isOnline = useOnlineStatus(); // P0-4
  const {
    messages,
    streamContent,
    citations,
    activeSessionId,
    isLoadingMessages,
    sendError,
    hasOlderMessages,
    setSendError,
    sendMessage,
    loadMessages,
    loadOlderRounds,
  } = useChatStore();

  // V3.5: Read unified stream phase + send lock
  const streamPhase = useChatStore(state => state.streamPhase);
  const isSendLocked = useChatStore(state => state.isSendLocked);
  const isStreaming = streamPhase !== 'idle'; // V3.5: Derived from streamPhase

  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<InputRef>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const loadedSessionRef = useRef<string | null>(null);
  const [isTransitioning, setIsTransitioning] = useState(false); // P1-5

  // V3.7 P1.2: IntersectionObserver fix — use ref instead of state to prevent
  // Observer recreation on every streamContent change (was 60 rebuilds/second).
  // Observer is created once and only re-observes when messages.length changes.
  const isNearBottomRef = useRef(true);
  const [, forceUpdate] = useState(0); // Only used for "scroll to bottom" button visibility

  // V3.6: Reset loadedSessionRef when navigating to /chat — ensures messages reload
  // when a session was previously set (e.g., from sidebar click)
  useEffect(() => {
    loadedSessionRef.current = null;
  }, [location.pathname]);

  useEffect(() => {
    if (activeSessionId && activeSessionId !== loadedSessionRef.current) {
      // P1-5: Show transition state
      setIsTransitioning(true);
      loadedSessionRef.current = activeSessionId;
      loadMessages(activeSessionId).finally(() => {
        setIsTransitioning(false);
      });
    }
  }, [activeSessionId, loadMessages]);

  // Throttle scroll during streaming to prevent excessive renders
  const throttledScroll = useRef(
    throttle((behavior: ScrollBehavior) => {
      messagesEndRef.current?.scrollIntoView({ behavior });
    }, 200)
  ).current;

  useEffect(() => {
    const container = messagesEndRef.current?.parentElement;
    if (!container) return;
    // V3.7 P1.2: Use ref value instead of state — avoids re-render per streamContent frame
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    isNearBottomRef.current = nearBottom;
    if (nearBottom || !isStreaming) {
      throttledScroll('smooth');
    }
  }, [messages, streamContent, isStreaming, throttledScroll]);

  // IntersectionObserver to detect if user scrolled away from bottom
  // V3.7 P1.2: Removed streamContent from dependencies — Observer is now created
  // only once per session (or when messages.length changes). The isNearBottom
  // value is stored in a ref to prevent React re-renders from streamContent changes.
  // This eliminates ~60 Observer create/destroy cycles per second during streaming.
  useEffect(() => {
    const sentinel = messagesEndRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        isNearBottomRef.current = entry.isIntersecting;
        // Only trigger re-render for "scroll to bottom" button visibility
        // when the value actually changes (not every streamContent frame)
        forceUpdate(prev => prev + 1);
      },
      { root: sentinel.parentElement ?? undefined, threshold: 0.1 }
    );
    observer.observe(sentinel);
    // V3.7: Log Observer creation for verification (should only appear once per session)
    console.log('[V3.7 P1.2] IntersectionObserver created — this should log only once per session');
    return () => observer.disconnect();
  }, [messages.length]); // V3.7: Removed streamContent — only re-observe when new messages arrive

  // V3.5 HIGH-001: handleSend now checks isSendLocked
  const handleSend = () => {
    if (!inputValue.trim() || isStreaming || isSendLocked) return;
    // P0-4: Block sending when offline
    if (!navigator.onLine) {
      antMessage.warning(t('offline_send_warning') || '当前网络不可用，请检查网络连接后重试');
      return;
    }
    sendMessage(inputValue.trim());
    setInputValue('');
    inputRef.current?.focus();
  };

  const handleQuickAction = (question: string) => {
    sendMessage(question);
  };

  const handleRetry = () => {
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user');
    if (lastUserMsg) {
      setSendError(null);
      sendMessage(lastUserMsg.content);
    }
  };

  // V3.5: Load older messages handler for sliding window
  const handleLoadOlder = () => {
    loadOlderRounds(5);
  };

  if (!activeSessionId && messages.length === 0) {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto', padding: '40px 16px' }}>
        <WelcomeScreen
          onQuickAction={handleQuickAction}
          onSendMessage={(msg) => {
            sendMessage(msg);
          }}
        />
      </div>
    );
  }

  // V3.6: Classify error message for better user feedback — unified i18n error keys
  const getErrorDescription = (error: string) => {
    if (error === 'error_auth') return t('error_auth');
    if (error === 'error_server') return t('error_server');
    if (error === 'error_network') return t('error_network');
    if (error === 'error_generic') return t('error_generic');
    if (error === 'error_session') return t('error_session');
    if (error === 'error_timeout') return t('error_timeout');
    return t('error_generic'); // Fallback for any unknown error key
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      flex: 1,
      minHeight: 0,
      height: '100%',
      maxWidth: 900,
      margin: '0 auto',
      width: '100%',
    }}>
      <div
        ref={scrollContainerRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          paddingBottom: 80,
          minHeight: 0,
          position: 'relative',
        }}
      >
        {/* Screen reader live region for streaming — P1-8: sentence-boundary clipping */}
        <div aria-live="polite" aria-atomic="false" className="sr-only">
          {isStreaming && streamContent && `AI正在输入: ${clipForScreenReader(streamContent)}`}
          {isStreaming && !streamContent && (
            streamPhase === 'connecting' ? t('thinking_connecting')
            : streamPhase === 'searching' ? t('thinking_searching')
            : t('thinking_generating')
          )}
        </div>

        {isLoadingMessages && messages.length === 0 && (
          <div style={{ padding: '16px 0' }}>
            {/* P1-4: Skeleton message bubbles instead of Spinner */}
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="message-skeleton"
                style={{
                  height: i === 1 ? 60 : 40,
                  width: i % 2 === 0 ? '60%' : '80%',
                  marginBottom: 8,
                  marginLeft: i % 2 === 0 ? 'auto' : 0,
                  marginRight: i % 2 === 0 ? 0 : 'auto',
                }}
              />
            ))}
          </div>
        )}

        {sendError && (
          <Alert
            message={t('error_title') || 'Error'}
            description={getErrorDescription(sendError)}
            type="error"
            showIcon
            closable
            onClose={() => setSendError(null)}
            style={{ marginBottom: 16 }}
            action={
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={handleRetry}
              >
                {t('error_retry')}
              </Button>
            }
          />
        )}

        {/* P1-5: Transition wrapper for smooth content switching */}
        <div
          className="message-transition"
          style={{ opacity: isTransitioning ? 0 : 1, transition: 'opacity 0.2s ease', flex: 1, minHeight: 0 }}
        >

        {/* V3.5 HIGH-003: Virtualized message list with sliding window + stream state isolation */}
        <VirtualizedMessageList
          messages={messages}
          hasOlderMessages={hasOlderMessages}
          onLoadOlder={handleLoadOlder}
          isStreaming={isStreaming}
          streamContent={streamContent}
          citations={citations}
          streamPhase={streamPhase}
          onRegenerate={handleRetry}
        />

        {/* Scroll to bottom button — shown when user scrolled up during streaming */}
        {/* V3.7 P1.2: Uses isNearBottomRef instead of isNearBottom state */}
        {!isNearBottomRef.current && isStreaming && (
          <div style={{
            position: 'absolute',
            bottom: 16,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 10,
            animation: 'fadeIn 0.2s ease',
          }}>
            <Button
              size="small"
              icon={<DownOutlined />}
              onClick={() => throttledScroll('smooth')}
              style={{
                borderRadius: 20,
                boxShadow: 'var(--shadow-md)',
                background: 'var(--color-bg-container)',
                borderColor: 'var(--color-border)',
              }}
            >
              {t('new_messages')}
            </Button>
          </div>
        )}
        </div>
      </div>

      {/* Floating Input Bar — DeepSeek style (fixed to viewport) */}
      <div style={{
        position: 'fixed',
        bottom: 32,
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        zIndex: 100,
        pointerEvents: 'none',
      }}>
        <div style={{
          width: '100%',
          maxWidth: 720,
          padding: '0 24px',
          pointerEvents: 'auto',
        }}>
          <div style={{
            background: 'var(--color-bg-container)',
            border: '1px solid var(--color-border)',
            borderRadius: 16,
            padding: '8px 8px 8px 16px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04)',
            transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
          }}>
            <Space.Compact style={{ width: '100%' }}>
              <TextArea
                ref={inputRef as any}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={t('placeholder')}
                disabled={isStreaming || isSendLocked}  // V3.5 HIGH-001: also disabled during send lock
                maxLength={4000}
                autoSize={{ minRows: 1, maxRows: 4 }}
                aria-label={t('chat_input_label') || 'Type your message'}
                style={{
                  border: 'none',
                  boxShadow: 'none',
                  fontSize: 14,
                  resize: 'none',
                }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={!inputValue.trim() || isStreaming || isSendLocked || !isOnline}  // V3.5 HIGH-001: send lock guard
                size="large"
                style={{
                  minWidth: 44,
                  height: 44,
                  borderRadius: 12,
                  fontWeight: 600,
                }}
              />
            </Space.Compact>
          </div>
          {/* Character counter */}
          {inputValue.length > 0 && (
            <div style={{
              textAlign: 'right',
              fontSize: 11,
              color: inputValue.length >= 4000 ? '#ff4d4f' : inputValue.length > 3500 ? '#faad14' : 'var(--color-text-tertiary)',
              marginTop: 4,
              paddingRight: 4,
              transition: 'color 0.2s ease',
            }}>
              {inputValue.length}/4000
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
