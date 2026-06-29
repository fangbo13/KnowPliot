import { useTranslation } from 'react-i18next';
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { message as antMessage } from 'antd';
import { CheckOutlined, CloseOutlined, ArrowDownOutlined, EditOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import type { VirtuosoHandle } from 'react-virtuoso';
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

function clipForScreenReader(text: string, maxLength = 100): string {
  if (text.length <= maxLength) return text;
  const truncated = text.slice(-maxLength);
  const boundary = truncated.search(/[.!?\n]/);
  if (boundary > 0 && boundary < truncated.length - 5) return truncated.slice(boundary + 1);
  return truncated;
}

export default function ChatPageContainer() {
  const { t } = useTranslation('chat');
  const location = useLocation();
  const isOnline = useOnlineStatus();
  const {
    sessions, messages, streamContent, citations, activeSessionId, streamingSessionId,
    isLoadingMessages, sendError, hasOlderMessages, setSendError, sendMessage,
    loadSessions, loadMessages, loadOlderRounds,
  } = useChatStore();

  const streamPhase = useChatStore((s) => s.streamPhase);
  const isSendLocked = useChatStore((s) => s.isSendLocked);
  const isStreaming = streamPhase !== 'idle';

  const [inputValue, setInputValue] = useState('');
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [isRenamingTitle, setIsRenamingTitle] = useState(false);
  const [renameDraft, setRenameDraft] = useState('');
  const [showScrollFab, setShowScrollFab] = useState(false);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const loadedSessionRef = useRef<string | null>(null);
  const isSendingRef = useRef(false);

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null;
  const activeSessionTitle = activeSession?.title || t('session_title_new');

  useEffect(() => {
    if (!isRenamingTitle) return;
    setRenameDraft(activeSessionTitle);
    const timer = window.setTimeout(() => titleInputRef.current?.focus(), 80);
    return () => window.clearTimeout(timer);
  }, [activeSessionTitle, isRenamingTitle]);

  useEffect(() => { loadedSessionRef.current = null; }, [location.pathname]);
  useEffect(() => () => cleanupTokenBatcher(), []);

  useEffect(() => {
    if (activeSessionId && activeSessionId !== loadedSessionRef.current) {
      if (streamPhase !== 'idle' && streamingSessionId === activeSessionId) {
        loadedSessionRef.current = activeSessionId;
        return;
      }
      setIsTransitioning(true);
      loadedSessionRef.current = activeSessionId;
      loadMessages(activeSessionId).finally(() => setIsTransitioning(false));
    }
  }, [activeSessionId, loadMessages, streamPhase, streamingSessionId]);

  const scrollToBottom = () => virtuosoRef.current?.scrollToIndex({ index: 'LAST', behavior: 'smooth', align: 'end' });

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
    requestAnimationFrame(() => { isSendingRef.current = false; });
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
    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUserMsg) {
      setSendError(null);
      isSendingRef.current = true;
      sendMessage(lastUserMsg.content);
      requestAnimationFrame(() => { isSendingRef.current = false; });
    }
  };

  const beginRenameTitle = () => {
    if (!activeSessionId) return;
    setRenameDraft(activeSessionTitle);
    setIsRenamingTitle(true);
  };
  const cancelRenameTitle = () => { setRenameDraft(activeSessionTitle); setIsRenamingTitle(false); };

  const handleRenameSession = async (nextTitle: string) => {
    if (!activeSessionId) return;
    const trimmed = nextTitle.trim();
    if (!trimmed) {
      antMessage.warning(t('rename_empty_warning', { defaultValue: 'Please enter a title' }));
      return;
    }
    try {
      await chatApi.renameSession(activeSessionId, trimmed);
      await loadSessions();
      setIsRenamingTitle(false);
      antMessage.success(t('session_renamed_success', { defaultValue: 'Conversation renamed' }));
    } catch (error) {
      console.error('Failed to rename session:', error);
      antMessage.error(t('session_renamed_failed', { defaultValue: 'Rename failed. Please try again' }));
    }
  };

  const handleStop = () => abortActiveStream();
  const handleLoadOlder = () => loadOlderRounds(5);

  if (!activeSessionId && messages.length === 0) {
    return (
      <div className="chat-view">
        <WelcomeScreen onQuickAction={handleQuickAction} onSendMessage={(m) => sendMessage(m)} />
      </div>
    );
  }

  const getErrorDescription = (error: string) => {
    const map: Record<string, string> = {
      error_auth: 'error_auth', error_server: 'error_server', error_network: 'error_network',
      error_generic: 'error_generic', error_session: 'error_session', error_timeout: 'error_timeout',
    };
    return t(map[error] || 'error_generic');
  };

  return (
    <div className="chat-view">
      <div className="chat-titlebar">
        {isRenamingTitle ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, width: '100%' }}>
            <input
              ref={titleInputRef}
              className="chat-title-input"
              value={renameDraft}
              maxLength={120}
              aria-label={t('rename_title_hint') || 'Rename conversation'}
              onChange={(e) => setRenameDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRenameSession(renameDraft);
                else if (e.key === 'Escape') { e.preventDefault(); cancelRenameTitle(); }
              }}
              onBlur={() => {
                if (renameDraft.trim() && renameDraft.trim() !== activeSessionTitle) handleRenameSession(renameDraft);
                else cancelRenameTitle();
              }}
            />
            <button className="icon-btn" onMouseDown={(e) => e.preventDefault()} onClick={() => handleRenameSession(renameDraft)} aria-label={t('confirm') || 'Save'}><CheckOutlined /></button>
            <button className="icon-btn" onMouseDown={(e) => e.preventDefault()} onClick={cancelRenameTitle} aria-label={t('cancel') || 'Cancel'}><CloseOutlined /></button>
          </div>
        ) : (
          <button className="chat-title-btn" onClick={beginRenameTitle} aria-label={t('rename_title_hint') || 'Rename conversation'} style={{ cursor: activeSessionId ? 'text' : 'default' }}>
            <span className="chat-title-text">{activeSessionTitle}</span>
            {!!activeSessionId && <EditOutlined className="chat-title-edit-icon" />}
          </button>
        )}
      </div>

      <div className="chat-stream-wrap">
        <div aria-live="polite" aria-atomic="false" className="sr-only">
          {isStreaming && streamContent && `AI is typing: ${clipForScreenReader(streamContent)}`}
          {isStreaming && !streamContent &&
            (streamPhase === 'connecting' ? t('thinking_connecting')
              : streamPhase === 'searching' ? t('thinking_searching')
              : t('thinking_generating'))}
        </div>

        {isLoadingMessages && messages.length === 0 && (
          <div className="skeleton-msg">
            {[80, 55, 70].map((w, i) => (
              <div key={i} className="skeleton-line" style={{ width: `${w}%`, height: i === 0 ? 20 : 14 }} />
            ))}
          </div>
        )}

        {sendError && (
          <div className="chat-error" role="alert">
            <WarningOutlined className="chat-error-icon" />
            <div className="chat-error-body">
              <div className="chat-error-title">{t('error_title') || 'Error'}</div>
              <div className="chat-error-desc">{getErrorDescription(sendError)}</div>
              <div className="chat-error-actions">
                <button className="msg-action-btn" onClick={handleRetry}><ReloadOutlined />{t('error_retry')}</button>
                <button className="msg-action-btn" onClick={() => setSendError(null)}>{t('cancel') || 'Dismiss'}</button>
              </div>
            </div>
          </div>
        )}

        <div style={{ opacity: isTransitioning ? 0 : 1, transition: 'opacity var(--dur) var(--ease-out)', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <VirtualizedMessageList
            virtuosoRef={virtuosoRef}
            messages={messages}
            hasOlderMessages={hasOlderMessages}
            onLoadOlder={handleLoadOlder}
            isStreaming={isStreaming}
            streamContent={streamContent}
            citations={citations}
            streamPhase={streamPhase}
            onRegenerate={handleRetry}
            onScrollToBottomChange={setShowScrollFab}
          />

          {showScrollFab && (
            <button className="scroll-fab" onClick={scrollToBottom} aria-label={t('new_messages') || 'Scroll to latest'}>
              <ArrowDownOutlined />{t('new_messages') || 'Latest'}
            </button>
          )}
        </div>
      </div>

      <div style={{ position: 'fixed', bottom: 'calc(14px + env(safe-area-inset-bottom, 0px))', left: 0, right: 0, display: 'flex', justifyContent: 'center', zIndex: 100, pointerEvents: 'none' }}>
        <div style={{ width: '100%', maxWidth: 'calc(var(--content-max) - 16px)', padding: '0 24px', pointerEvents: 'auto' }}>
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
            maxRows={6}
            showHint
          />
        </div>
      </div>
    </div>
  );
}
