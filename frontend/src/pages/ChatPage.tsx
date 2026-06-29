import { useTranslation } from 'react-i18next';
import { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Input, Button, Space, Alert, type InputRef, message as antMessage } from 'antd';
const { TextArea } = Input;
import { SendOutlined, ReloadOutlined, DownOutlined, StopOutlined } from '@ant-design/icons';
import { useChatStore } from '../store/chatStore';
import { abortActiveStream } from '../stream/StreamLifecycleManager';
import { cleanupTokenBatcher } from '../stream/TokenBatchRenderer';
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

  // V4.1 BUG-001: Cleanup token batcher on unmount to prevent memory leak.
  // Module-level singleton (accumulatedContent, rafId, batchCallback) cannot be GC'd
  // if batchCallback closure holds references to React state. This cleanup cancels
  // pending rAF and nulls the callback so the closure can be collected.
  // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-001]
  useEffect(() => {
    return () => cleanupTokenBatcher();
  }, []);

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
    // V4.1 BUG-017: Use single source of truth (isNearBottomRef from IntersectionObserver)
    // instead of separate scroll heuristic. Removed the heuristic calculation:
    // container.scrollHeight - container.scrollTop - container.clientHeight < 100
    // The IntersectionObserver with rootMargin '0px 0px 100px 0px' provides the same
    // proximity detection with no flicker from dual thresholds.
    // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-017]
    if (isNearBottomRef.current || !isStreaming) {
      throttledScroll('smooth');
    }
  }, [messages, streamContent, isStreaming, throttledScroll]);

  // IntersectionObserver to detect if user scrolled away from bottom
  // V4.1 BUG-017: Changed from threshold:0.1 to rootMargin:'0px 0px 100px 0px'.
  // V4.2 SYS-V4.2-018: Only trigger forceUpdate when isNearBottom value CHANGES.
  // Previous: forceUpdate(prev => prev + 1) on every IntersectionObserver callback,
  // even when isNearBottom didn't change → ~60/sec unnecessary React renders during streaming.
  // Now: track previous value in a ref and only call forceUpdate when the value flips.
  // This reduces IntersectionObserver-triggered renders from ~60/sec to ~0-2/sec
  // (only when user actually scrolls near/away from bottom).
  const prevIsNearBottomRef = useRef(true);
  useEffect(() => {
    const sentinel = messagesEndRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        const newIsNearBottom = entry.isIntersecting;
        // V4.2 SYS-V4.2-018: Only trigger re-render when value actually changes
        if (prevIsNearBottomRef.current !== newIsNearBottom) {
          prevIsNearBottomRef.current = newIsNearBottom;
          isNearBottomRef.current = newIsNearBottom;
          forceUpdate(prev => prev + 1);
        } else {
          // Value unchanged — just update the ref, no React re-render
          isNearBottomRef.current = newIsNearBottom;
        }
      },
      { root: sentinel.parentElement ?? undefined, rootMargin: '0px 0px 100px 0px' }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [messages.length]); // V3.7: Removed streamContent — only re-observe when new messages arrive

  // V4.1 BUG-002: Local ref guard to prevent double-click firing two sendMessage calls
  // within one render frame. The React disabled prop on TextArea is batched, so the
  // button stays enabled for ~16ms after the first click. This ref provides a synchronous
  // guard that blocks the second click in the same frame.
  // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-002]
  const isSendingRef = useRef(false);

  // V3.5 HIGH-001: handleSend now checks isSendLocked
  const handleSend = () => {
    if (!inputValue.trim() || isStreaming || isSendLocked || isSendingRef.current) return;
    // P0-4: Block sending when offline
    if (!navigator.onLine) {
      antMessage.warning(t('offline_send_warning') || '当前网络不可用，请检查网络连接后重试');
      return;
    }
    isSendingRef.current = true;
    sendMessage(inputValue.trim());
    setInputValue('');
    inputRef.current?.focus();
    // Reset guard after React renders the disabled state (~next frame)
    requestAnimationFrame(() => { isSendingRef.current = false; });
  };

  const handleQuickAction = (question: string) => {
    sendMessage(question);
    // V4.1 BUG-016: Focus chat input after quick-action for keyboard navigation continuity.
    // Without this, focus remains on the clicked card, breaking keyboard nav flow.
    // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-016]
    inputRef.current?.focus();
  };

  // V4.2 UI-V4.2-002: handleRetry now reuses handleSend's full guard chain.
  // Previously bypassed isStreaming/isSendLocked/isSendingRef/navigator.onLine checks,
  // allowing offline sends and potential concurrent double-stream.
  // [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-002]
  const handleRetry = () => {
    if (isStreaming || isSendLocked || isSendingRef.current) return;
    if (!navigator.onLine) {
      antMessage.warning(t('offline_send_warning') || '当前网络不可用，请检查网络连接后重试');
      return;
    }
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user');
    if (lastUserMsg) {
      setSendError(null);
      isSendingRef.current = true;
      sendMessage(lastUserMsg.content);
      requestAnimationFrame(() => { isSendingRef.current = false; });
    }
  };

  // V4.0 UI-HIGH-001: Stop generation handler
  // Aborts the active SSE stream and preserves the content that was already output.
  // The AbortError handler in chatStore.ts will save the truncated content as a message.
  const handleStop = () => {
    abortActiveStream();   // Terminate SSE fetch — triggers AbortError in chatStore
    // abortActiveStream triggers the catch block in sendMessage,
    // which calls flushImmediate() + clearStreamOnComplete() + saves truncated content
    // No need to call setSendError — abort is intentional, not an error
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
          // V5.0 FIX (blank chat): this must be a flex column so its flex:1 child
          // (.message-transition) actually receives a height. Without display:flex the
          // child's flex:1 is ignored → the wrapper collapses → Virtuoso renders at 0
          // height → the whole message list is invisible (the reported "blank chat").
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          overflow: 'hidden',
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
            // V4.0 DEFECT-007: Network errors get stronger visual treatment for clearer feedback
            // V4.2 UI-V4.2-003: Replace hardcoded #fff2f0/#ff4d4f with CSS variables for dark mode.
            // Previously #fff2f0 (light-only pink) was jarring on dark backgrounds.
            // [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-003]
            style={{
              marginBottom: 16,
              borderRadius: 8,
              ...(sendError === 'error_network' ? {
                border: '2px solid var(--color-error)',
                background: 'rgba(var(--color-error-rgb, 239, 68, 68), 0.08)',
              } : {}),
            }}
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
          // V5.0 FIX (blank chat): flex column + minHeight:0 so the Virtuoso list inside
          // (styled flex:1) gets a bounded height to virtualize against. Without this the
          // list has no height and shows nothing.
          style={{ opacity: isTransitioning ? 0 : 1, transition: 'opacity 0.2s ease', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
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

      {/* Floating Input Bar — DeepSeek style (fixed to viewport)
       * V4.1 BUG-006: Responsive bottom offset with safe-area-inset for mobile browsers.
       * Uses calc(16px + env(safe-area-inset-bottom)) to handle iOS Safari address bar
       * and Android Chrome viewport height fluctuations. Small screens (<500px) use
       * tighter spacing and full-width input.
       * [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-006] */}
      <div style={{
        position: 'fixed',
        bottom: 'calc(16px + env(safe-area-inset-bottom, 0px))',
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        zIndex: 100,
        pointerEvents: 'none',
      }}>
        <div className="floating-input-inner" style={{
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
            boxShadow: 'var(--shadow-floating-input)',
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
              {/* V4.0 UI-HIGH-001: Conditional Stop/Send button */}
              {isStreaming ? (
                <Button
                  type="primary"
                  danger
                  icon={<StopOutlined />}
                  onClick={handleStop}
                  size="large"
                  aria-label={t('stop_generation') || '停止生成'}
                  style={{
                    minWidth: 44,
                    height: 44,
                    borderRadius: 12,
                    fontWeight: 600,
                  }}
                />
              ) : (
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={handleSend}
                  disabled={!inputValue.trim() || isSendLocked || !isOnline}  // V3.5 HIGH-001: send lock guard
                  size="large"
                  style={{
                    minWidth: 44,
                    height: 44,
                    borderRadius: 12,
                    fontWeight: 600,
                  }}
                />
              )}
            </Space.Compact>
          </div>
          {/* V4.2 UI-V4.2-009: Character counter with ARIA live region.
          * Screen readers now announce character count changes, especially
          * critical near the 3500+ threshold when color changes to amber/red.
          * [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-009] */}
          {inputValue.length > 0 && (
            <div
              role="status"
              aria-live="polite"
              aria-label={`Character count: ${inputValue.length} of 4000`}
              style={{
              textAlign: 'right',
              fontSize: 11,
              color: inputValue.length >= 4000 ? 'var(--color-error)' : inputValue.length > 3500 ? 'var(--color-warning)' : 'var(--color-text-tertiary)',
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
