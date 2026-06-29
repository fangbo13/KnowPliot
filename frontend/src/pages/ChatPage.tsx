import { useTranslation } from 'react-i18next';
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Alert, Button, Input, message as antMessage, type InputRef } from 'antd';
import { CheckOutlined, CloseOutlined, DownOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons';
import { useChatStore } from '../store/chatStore';
import { abortActiveStream } from '../stream/StreamLifecycleManager';
import { cleanupTokenBatcher } from '../stream/TokenBatchRenderer';
import WelcomeScreen from '../components/chat/WelcomeScreen';
import VirtualizedMessageList from '../components/chat/VirtualizedMessageList';
import ChatComposer from '../components/chat/ChatComposer';
import { chatApi } from '../api/chat';

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

function throttle<T extends (...args: any[]) => void>(fn: T, limit: number): T {
  let inThrottle = false;
  return ((...args: Parameters<T>) => {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      setTimeout(() => {
        inThrottle = false;
      }, limit);
    }
  }) as T;
}

function clipForScreenReader(text: string, maxLength: number = 100): string {
  if (text.length <= maxLength) return text;
  const truncated = text.slice(-maxLength);
  const boundaryMatch = truncated.search(/[.!?\n]/);
  if (boundaryMatch > 0 && boundaryMatch < truncated.length - 5) {
    return truncated.slice(boundaryMatch + 1);
  }
  return truncated;
}

export default function ChatPageContainer() {
  const { t } = useTranslation('chat');
  const location = useLocation();
  const isOnline = useOnlineStatus();
  const {
    sessions,
    messages,
    streamContent,
    citations,
    activeSessionId,
    isLoadingMessages,
    sendError,
    hasOlderMessages,
    setSendError,
    sendMessage,
    loadSessions,
    loadMessages,
    loadOlderRounds,
  } = useChatStore();

  const streamPhase = useChatStore((state) => state.streamPhase);
  const isSendLocked = useChatStore((state) => state.isSendLocked);
  const isStreaming = streamPhase !== 'idle';

  const [inputValue, setInputValue] = useState('');
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [isRenamingTitle, setIsRenamingTitle] = useState(false);
  const [renameDraft, setRenameDraft] = useState('');
  const [, forceUpdate] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<InputRef>(null);
  const titleInputRef = useRef<InputRef>(null);
  const loadedSessionRef = useRef<string | null>(null);
  const isNearBottomRef = useRef(true);
  const prevIsNearBottomRef = useRef(true);
  const isSendingRef = useRef(false);

  const activeSession = sessions.find((session) => session.id === activeSessionId) || null;
  const activeSessionTitle = activeSession?.title || t('session_title_new');

  useEffect(() => {
    if (!isRenamingTitle) return;
    setRenameDraft(activeSessionTitle);
    const timer = window.setTimeout(() => titleInputRef.current?.focus({ cursor: 'all' }), 80);
    return () => window.clearTimeout(timer);
  }, [activeSessionTitle, isRenamingTitle]);

  useEffect(() => {
    loadedSessionRef.current = null;
  }, [location.pathname]);

  useEffect(() => {
    return () => cleanupTokenBatcher();
  }, []);

  useEffect(() => {
    if (activeSessionId && activeSessionId !== loadedSessionRef.current) {
      setIsTransitioning(true);
      loadedSessionRef.current = activeSessionId;
      loadMessages(activeSessionId).finally(() => {
        setIsTransitioning(false);
      });
    }
  }, [activeSessionId, loadMessages]);

  const throttledScroll = useRef(
    throttle((behavior: ScrollBehavior) => {
      messagesEndRef.current?.scrollIntoView({ behavior });
    }, 200)
  ).current;

  useEffect(() => {
    const container = messagesEndRef.current?.parentElement;
    if (!container) return;
    if (isNearBottomRef.current || !isStreaming) {
      throttledScroll('smooth');
    }
  }, [messages, streamContent, isStreaming, throttledScroll]);

  useEffect(() => {
    const sentinel = messagesEndRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        const newIsNearBottom = entry.isIntersecting;
        if (prevIsNearBottomRef.current !== newIsNearBottom) {
          prevIsNearBottomRef.current = newIsNearBottom;
          isNearBottomRef.current = newIsNearBottom;
          forceUpdate((prev) => prev + 1);
        } else {
          isNearBottomRef.current = newIsNearBottom;
        }
      },
      { root: sentinel.parentElement ?? undefined, rootMargin: '0px 0px 100px 0px' }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [messages.length]);

  const handleSend = () => {
    if (!inputValue.trim() || isStreaming || isSendLocked || isSendingRef.current) return;
    if (!navigator.onLine) {
      antMessage.warning(t('offline_send_warning') || 'You are offline. Please check your network.');
      return;
    }
    isSendingRef.current = true;
    sendMessage(inputValue.trim());
    setInputValue('');
    inputRef.current?.focus();
    requestAnimationFrame(() => {
      isSendingRef.current = false;
    });
  };

  const handleQuickAction = (question: string) => {
    sendMessage(question);
    inputRef.current?.focus();
  };

  const handleRetry = () => {
    if (isStreaming || isSendLocked || isSendingRef.current) return;
    if (!navigator.onLine) {
      antMessage.warning(t('offline_send_warning') || 'You are offline. Please check your network.');
      return;
    }

    const lastUserMsg = [...messages].reverse().find((message) => message.role === 'user');
    if (lastUserMsg) {
      setSendError(null);
      isSendingRef.current = true;
      sendMessage(lastUserMsg.content);
      requestAnimationFrame(() => {
        isSendingRef.current = false;
      });
    }
  };

  const beginRenameTitle = () => {
    if (!activeSessionId) return;
    setRenameDraft(activeSessionTitle);
    setIsRenamingTitle(true);
  };

  const cancelRenameTitle = () => {
    setRenameDraft(activeSessionTitle);
    setIsRenamingTitle(false);
  };

  const handleRenameSession = async (nextTitle: string) => {
    if (!activeSessionId) return;
    const trimmed = nextTitle.trim();
    if (!trimmed) {
      antMessage.warning(t('rename_title_hint') || 'Please enter a title');
      return;
    }

    try {
      await chatApi.renameSession(activeSessionId, trimmed);
      await loadSessions();
      setIsRenamingTitle(false);
      antMessage.success(
        t('session_renamed_success') ||
          (navigator.language.startsWith('zh') ? '对话已重命名' : 'Conversation renamed')
      );
    } catch (error) {
      console.error('Failed to rename session:', error);
      antMessage.error(
        t('session_renamed_failed') ||
          (navigator.language.startsWith('zh') ? '重命名失败，请重试' : 'Rename failed. Please try again')
      );
    }
  };

  const handleStop = () => {
    abortActiveStream();
  };

  const handleLoadOlder = () => {
    loadOlderRounds(5);
  };

  if (!activeSessionId && messages.length === 0) {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto', padding: '40px 16px' }}>
        <WelcomeScreen
          onQuickAction={handleQuickAction}
          onSendMessage={(message) => {
            sendMessage(message);
          }}
        />
      </div>
    );
  }

  const getErrorDescription = (error: string) => {
    if (error === 'error_auth') return t('error_auth');
    if (error === 'error_server') return t('error_server');
    if (error === 'error_network') return t('error_network');
    if (error === 'error_generic') return t('error_generic');
    if (error === 'error_session') return t('error_session');
    if (error === 'error_timeout') return t('error_timeout');
    return t('error_generic');
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        minHeight: 0,
        height: '100%',
        maxWidth: 900,
        margin: '0 auto',
        width: '100%',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '16px 24px 8px',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            minWidth: 0,
          }}
        >
          <div className={`chat-title-rename ${isRenamingTitle ? 'is-editing' : ''}`} style={{ minWidth: 0 }}>
            {isRenamingTitle ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                <Input
                  ref={titleInputRef}
                  value={renameDraft}
                  maxLength={120}
                  aria-label={t('rename_title_hint') || 'Rename conversation'}
                  onChange={(event) => setRenameDraft(event.target.value)}
                  onPressEnter={() => handleRenameSession(renameDraft)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      event.preventDefault();
                      cancelRenameTitle();
                    }
                  }}
                  onBlur={() => {
                    if (renameDraft.trim() && renameDraft.trim() !== activeSessionTitle) {
                      handleRenameSession(renameDraft);
                    } else {
                      cancelRenameTitle();
                    }
                  }}
                  className="chat-title-rename-input"
                  style={{
                    width: 'min(520px, calc(100vw - 420px))',
                    minWidth: 220,
                    height: 34,
                    borderRadius: 10,
                    fontSize: 18,
                    fontWeight: 600,
                    paddingInline: 10,
                  }}
                />
                <Button
                  type="text"
                  size="small"
                  icon={<CheckOutlined />}
                  aria-label={t('confirm') || 'Save'}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => handleRenameSession(renameDraft)}
                />
                <Button
                  type="text"
                  size="small"
                  icon={<CloseOutlined />}
                  aria-label={t('cancel') || 'Cancel'}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={cancelRenameTitle}
                />
              </div>
            ) : (
              <button
                type="button"
                className="chat-title-rename-button"
                onClick={beginRenameTitle}
                aria-label={t('rename_title_hint') || 'Rename conversation'}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  maxWidth: '100%',
                  border: 'none',
                  background: 'transparent',
                  padding: 0,
                  color: 'var(--color-text)',
                  cursor: activeSessionId ? 'text' : 'default',
                }}
              >
                <span
                  style={{
                    fontSize: 18,
                    fontWeight: 600,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {activeSessionTitle}
                </span>
                {!!activeSessionId && <EditOutlined className="chat-title-rename-icon" />}
              </button>
            )}
          </div>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          overflow: 'hidden',
          minHeight: 0,
          position: 'relative',
        }}
      >
        <div aria-live="polite" aria-atomic="false" className="sr-only">
          {isStreaming && streamContent && `AI is typing: ${clipForScreenReader(streamContent)}`}
          {isStreaming && !streamContent &&
            (streamPhase === 'connecting'
              ? t('thinking_connecting')
              : streamPhase === 'searching'
                ? t('thinking_searching')
                : t('thinking_generating'))}
        </div>

        {isLoadingMessages && messages.length === 0 && (
          <div style={{ padding: '16px 0' }}>
            {[1, 2, 3].map((index) => (
              <div
                key={index}
                className="message-skeleton"
                style={{
                  height: index === 1 ? 60 : 40,
                  width: index % 2 === 0 ? '60%' : '80%',
                  marginBottom: 8,
                  marginLeft: index % 2 === 0 ? 'auto' : 0,
                  marginRight: index % 2 === 0 ? 0 : 'auto',
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
            style={{
              marginBottom: 16,
              borderRadius: 8,
              ...(sendError === 'error_network'
                ? {
                    border: '2px solid var(--color-error)',
                    background: 'rgba(var(--color-error-rgb, 239, 68, 68), 0.08)',
                  }
                : {}),
            }}
            action={
              <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>
                {t('error_retry')}
              </Button>
            }
          />
        )}

        <div
          className="message-transition"
          style={{
            opacity: isTransitioning ? 0 : 1,
            transition: 'opacity 0.2s ease',
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
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

          {!isNearBottomRef.current && isStreaming && (
            <div
              style={{
                position: 'absolute',
                bottom: 16,
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 10,
                animation: 'fadeIn 0.2s ease',
              }}
            >
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

        <div ref={messagesEndRef} style={{ height: 1 }} />
      </div>

      <div
        style={{
          position: 'fixed',
          bottom: 'calc(16px + env(safe-area-inset-bottom, 0px))',
          left: 0,
          right: 0,
          display: 'flex',
          justifyContent: 'center',
          zIndex: 100,
          pointerEvents: 'none',
        }}
      >
        <div
          className="floating-input-inner"
          style={{
            width: '100%',
            maxWidth: 720,
            padding: '0 24px',
            pointerEvents: 'auto',
          }}
        >
          <ChatComposer
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSend}
            onStop={handleStop}
            placeholder={t('placeholder')}
            ariaLabel={t('chat_input_label') || 'Type your message'}
            isStreaming={isStreaming}
            disabled={isSendLocked || !isOnline}
            inputRef={inputRef}
            multiline
            maxRows={4}
          />
        </div>
      </div>
    </div>
  );
}
