/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { CheckOutlined, CloseOutlined, ArrowDownOutlined, EditOutlined, ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import type { VirtuosoHandle } from 'react-virtuoso';
import { useChatStore, type AnswerMode, type Message } from '../store/chatStore';
import { useSpaceStore } from '../store/spaceStore';
import WelcomeScreen from '../components/chat/WelcomeScreen';
import ChatComposer from '../components/chat/ChatComposer';
import { chatApi } from '../api/chat';
import { useAuthorization } from '../auth/CapabilityProvider';
import { notify } from '../utils/notifications';

const VirtualizedMessageList = lazy(() => import('../components/chat/VirtualizedMessageList'));
const ProcessingPanel = lazy(() => import('../components/chat/ProcessingPanel'));

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
  const authorization = useAuthorization();
  const canShare = authorization.has('chat.share');
  // Always show DEEP and Thinking buttons — the server gracefully falls back
  // to a safe policy if a mode is unavailable, so users can always try.
  const canUseDeep = true;
  const canUseThinking = true;
  const location = useLocation();
  const isOnline = useOnlineStatus();
  const {
    sessions, messages, activeSessionId, isLoadingMessages, hasOlderMessages,
    setSendError, sendMessage, loadSessions, loadMessages, loadOlderRounds, setActiveSession,
    abortSessionStream,
  } = useChatStore();

  const activeTurn = useChatStore((s) => activeSessionId ? s.turnsBySession[activeSessionId] : undefined);
  const streamPhase = activeTurn?.phase ?? 'idle';
  const isSendLocked = activeTurn?.isLocked ?? false;
  const sendError = activeTurn?.error ?? null;
  const isStreaming = isSendLocked && streamPhase !== 'error';
  const visibleStreamContent = isStreaming ? activeTurn?.content ?? '' : '';
  const visibleCitations = isStreaming ? activeTurn?.citations ?? [] : [];
  const visibleStreamPhase = isStreaming ? streamPhase : 'idle';
  const visibleAiStatusText = isStreaming ? activeTurn?.aiStatusText ?? null : null;

  const activeSpace = useSpaceStore((s) => s.getActiveSpace());
  const templateQuickQuestions = activeSpace?.settings?.quick_questions;

  const [inputValue, setInputValue] = useState('');
  const [answerMode, setAnswerMode] = useState<AnswerMode>('fast');
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [modeNotice, setModeNotice] = useState<string | null>(null);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [isRenamingTitle, setIsRenamingTitle] = useState(false);
  const [renameDraft, setRenameDraft] = useState('');
  const [showScrollFab, setShowScrollFab] = useState(false);
  const [capacityClockMs, setCapacityClockMs] = useState(Date.now());

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const loadedSessionRef = useRef<string | null>(null);
  const previousSessionRef = useRef<string | null>(activeSessionId);
  const isSendingRef = useRef(false);

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null;
  const activeSessionTitle = activeSession?.title || t('session_title_new');
  const capacityRetrySeconds = activeTurn?.capacityRetryAtMs
    ? Math.max(0, Math.ceil((activeTurn.capacityRetryAtMs - capacityClockMs) / 1000))
    : 0;

  useEffect(() => {
    if (!activeTurn?.capacityRetryAtMs || activeTurn.capacityRetryAtMs <= Date.now()) return;
    setCapacityClockMs(Date.now());
    const timer = window.setInterval(() => setCapacityClockMs(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [activeTurn?.capacityRetryAtMs]);

  useEffect(() => {
    if (!isRenamingTitle) return;
    setRenameDraft(activeSessionTitle);
    const timer = window.setTimeout(() => titleInputRef.current?.focus(), 80);
    return () => window.clearTimeout(timer);
  }, [activeSessionTitle, isRenamingTitle]);

  useEffect(() => { loadedSessionRef.current = null; }, [location.pathname]);

  useEffect(() => {
    if (answerMode !== 'deep' || canUseDeep) return;
    setAnswerMode('fast');
    setModeNotice('error_deep_unavailable');
  }, [answerMode, canUseDeep]);

  useEffect(() => {
    if (thinkingEnabled && !canUseThinking) {
      setThinkingEnabled(false);
      setModeNotice('error_thinking_unavailable');
    }
  }, [thinkingEnabled, canUseThinking]);

  // A new logical conversation starts from the safe defaults.  Mode changes
  // within the same conversation deliberately do not touch this preference.
  useEffect(() => {
    if (previousSessionRef.current !== activeSessionId) {
      previousSessionRef.current = activeSessionId;
      setAnswerMode('fast');
      setThinkingEnabled(false);
    }
  }, [activeSessionId]);

  useEffect(() => {
    if (activeSessionId && activeSessionId !== loadedSessionRef.current) {
      if (activeTurn?.isLocked) {
        loadedSessionRef.current = activeSessionId;
        return;
      }
      setIsTransitioning(true);
      loadedSessionRef.current = activeSessionId;
      loadMessages(activeSessionId).finally(() => setIsTransitioning(false));
    }
  }, [activeSessionId, activeTurn?.isLocked, loadMessages]);

  const scrollToBottom = () => virtuosoRef.current?.scrollToIndex({ index: 'LAST', behavior: 'smooth', align: 'end' });

  const handleSend = () => {
    if (!inputValue.trim() || isStreaming || isSendLocked || isSendingRef.current) return;
    if (answerMode === 'deep' && !canUseDeep) {
      setAnswerMode('fast');
      setModeNotice('error_deep_unavailable');
      return;
    }
    if (!navigator.onLine) {
      void notify('warning', t('offline_send_warning') || 'You are offline. Please check your network.');
      return;
    }
    isSendingRef.current = true;
    const options = thinkingEnabled
      ? { answerMode, canUseDeep, thinkingEnabled: true, canUseThinking: true }
      : { answerMode, canUseDeep };
    sendMessage(inputValue.trim(), options);
    // Each newly submitted logical question starts from the safe defaults;
    // the captured options above remain attached to its owning Turn.
    setAnswerMode('fast');
    setThinkingEnabled(false);
    setModeNotice(null);
    setInputValue('');
    inputRef.current?.focus();
    requestAnimationFrame(() => { isSendingRef.current = false; });
  };

  const handleQuickAction = (question: string) => {
    sendMessage(question, { answerMode: 'fast' });
    setAnswerMode('fast');
    setThinkingEnabled(false);
    inputRef.current?.focus();
  };

  const handleRetry = (targetAssistant?: Message) => {
    if (isStreaming || isSendLocked || isSendingRef.current) return;
    if (!navigator.onLine) {
      void notify('warning', t('offline_send_warning') || 'You are offline. Please check your network.');
      return;
    }
    const targetIndex = targetAssistant
      ? messages.findIndex((message) => message.id === targetAssistant.id)
      : messages.length;
    const lastUserMsg = messages.slice(0, targetIndex).reverse().find((message) => message.role === 'user');
    if (lastUserMsg) {
      isSendingRef.current = true;
      if (targetAssistant) {
        setSendError(null);
        sendMessage(lastUserMsg.content, {
          answerMode: answerMode === 'deep' && canUseDeep ? 'deep' : 'fast',
          canUseDeep,
          ...(thinkingEnabled ? { thinkingEnabled: true, canUseThinking: true } : {}),
          regenerateMessageId: targetAssistant.id,
        });
        requestAnimationFrame(() => { isSendingRef.current = false; });
        return;
      }
      const retryClientRequestId = activeTurn?.clientRequestId;
      const reusesFailedDeepTurn = (activeTurn?.requestedAnswerMode ?? activeTurn?.answerMode) === 'deep'
        && activeTurn?.phase === 'error'
        && !activeTurn?.isLocked
        && Boolean(retryClientRequestId);
      if (reusesFailedDeepTurn) {
        setAnswerMode('fast');
        setModeNotice(null);
        sendMessage(lastUserMsg.content, {
          answerMode: 'fast',
          ...(thinkingEnabled ? { thinkingEnabled: true, canUseThinking: true } : {}),
          retryClientRequestId: retryClientRequestId!,
        });
      } else {
        setSendError(null);
        sendMessage(lastUserMsg.content, {
          answerMode: answerMode === 'deep' && canUseDeep ? 'deep' : 'fast',
          canUseDeep,
          ...(thinkingEnabled ? { thinkingEnabled: true, canUseThinking: true } : {}),
        });
      }
      requestAnimationFrame(() => { isSendingRef.current = false; });
    }
  };

  const handleBranch = async (targetAssistant: Message) => {
    if (isStreaming || isSendLocked) return;
    try {
      const branch = await chatApi.branchMessage(targetAssistant.id);
      await loadSessions();
      setActiveSession(branch.id);
      void notify('success', t('branch_created'));
    } catch {
      void notify('error', t('branch_failed'));
    }
  };

  const handleShare = async () => {
    if (!activeSessionId || !canShare) return;
    try {
      const share = await chatApi.createShare(activeSessionId);
      const url = `${window.location.origin}/shared/${share.token}`;
      if (navigator.share) await navigator.share({ title: activeSessionTitle, url });
      else await navigator.clipboard.writeText(url);
      void notify('success', t('share_created'));
    } catch {
      void notify('error', t('share_failed'));
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
      void notify('warning', t('rename_empty_warning', { defaultValue: 'Please enter a title' }));
      return;
    }
    try {
      await chatApi.renameSession(activeSessionId, trimmed);
      await loadSessions();
      setIsRenamingTitle(false);
      void notify('success', t('session_renamed_success', { defaultValue: 'Conversation renamed' }));
    } catch (error) {
      console.error('Failed to rename session:', error);
      void notify('error', t('session_renamed_failed', { defaultValue: 'Rename failed. Please try again' }));
    }
  };

  const handleStop = () => { if (activeSessionId) abortSessionStream(activeSessionId); };
  const handleLoadOlder = () => loadOlderRounds(5);

  if (!activeSessionId && messages.length === 0) {
    return (
      <div className="chat-view">
        <WelcomeScreen
          onQuickAction={handleQuickAction}
          onSendMessage={(m, opts) => sendMessage(m, { answerMode: opts?.answerMode ?? 'fast', ...(opts?.thinkingEnabled ? { thinkingEnabled: true, canUseThinking: true } : {}), canUseDeep: true })}
          templateQuickQuestions={templateQuickQuestions}
        />
        <div style={{ position: 'fixed', bottom: 'calc(14px + env(safe-area-inset-bottom, 0px))', left: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: 100, pointerEvents: 'none' }}>
          <div style={{
            opacity: visibleAiStatusText ? 1 : 0,
            transform: visibleAiStatusText ? 'translateY(0)' : 'translateY(8px)',
            transition: 'opacity var(--motion-base) var(--motion-ease), transform var(--motion-base) var(--motion-ease)',
            marginBottom: 10,
            display: 'flex',
            justifyContent: 'center',
            pointerEvents: visibleAiStatusText ? 'auto' : 'none'
          }}>
            <div className="gemini-status-indicator" style={{ background: 'var(--color-bg-elevated)' }}>
              <span className="gemini-status-spinner" />
              <span>{visibleAiStatusText}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const getErrorDescription = (error: string) => {
    if (error === 'error_capacity') {
      return t('error_capacity', { seconds: capacityRetrySeconds });
    }
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
          {isStreaming && visibleStreamContent && `AI is typing: ${clipForScreenReader(visibleStreamContent)}`}
          {isStreaming && !visibleStreamContent &&
            (streamPhase === 'connecting' ? t('thinking_connecting')
              : streamPhase === 'searching' ? t('thinking_searching')
              : t('thinking_generating'))}
        </div>

        {isStreaming && activeTurn?.safePhase ? (
          <Suspense fallback={null}>
            <ProcessingPanel
              answerMode={activeTurn.answerMode ?? 'fast'}
              phase={activeTurn.safePhase}
              timings={activeTurn.timings}
              citations={activeTurn.citations}
              executionSnapshot={activeTurn.executionSnapshot}
            />
          </Suspense>
        ) : null}

        {isLoadingMessages && messages.length === 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '24px 0' }}>
            <div className="skeleton-msg" style={{ alignSelf: 'flex-end', width: '60%', padding: '14px 18px', borderRadius: 20 }}>
              {[100, 85].map((w, i) => <div key={i} className="skeleton-line" style={{ width: `${w}%`, height: 14 }} />)}
            </div>
            <div className="skeleton-msg" style={{ alignSelf: 'flex-start', width: '85%', padding: '14px 18px', borderRadius: 20 }}>
              {[100, 100, 65].map((w, i) => <div key={i} className="skeleton-line" style={{ width: `${w}%`, height: 14 }} />)}
            </div>
            <div className="skeleton-msg" style={{ alignSelf: 'flex-end', width: '40%', padding: '14px 18px', borderRadius: 20 }}>
              {[90].map((w, i) => <div key={i} className="skeleton-line" style={{ width: `${w}%`, height: 14 }} />)}
            </div>
          </div>
        )}

        {sendError && (
          <div className="chat-error section-enter" role="alert">
            <WarningOutlined className="chat-error-icon" />
            <div className="chat-error-body">
              <div className="chat-error-title">{t('error_title') || 'Error'}</div>
              <div className="chat-error-desc">{getErrorDescription(sendError)}</div>
              <div className="chat-error-actions">
                <button className="msg-action-btn" disabled={capacityRetrySeconds > 0} onClick={() => handleRetry()}>
                  <ReloadOutlined />
                  {capacityRetrySeconds > 0
                    ? t('capacity_retry_countdown', { seconds: capacityRetrySeconds })
                    : t('error_retry')}
                </button>
                <button className="msg-action-btn" onClick={() => setSendError(null)}>{t('cancel') || 'Dismiss'}</button>
              </div>
            </div>
          </div>
        )}

        {modeNotice ? (
          <div className="chat-mode-notice" role="alert">
            {t(modeNotice, {
              defaultValue: 'Deep answer is no longer available. Fast answer remains available.',
            })}
          </div>
        ) : null}

        <div style={{ opacity: isTransitioning ? 0 : 1, transition: 'opacity var(--dur) var(--ease-out)', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <Suspense fallback={
            <div className="chat-route-loading skeleton-active" role="status" style={{ padding: 24 }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16 }}>
                <div className="skeleton-card skeleton-active" style={{ width: 40, height: 40, borderRadius: '50%' }} />
                <div style={{ flex: 1 }}>
                  <div className="skeleton-card skeleton-active" style={{ height: 12, width: '40%', marginBottom: 8 }} />
                  <div className="skeleton-card skeleton-active" style={{ height: 12, width: '60%' }} />
                </div>
              </div>
              <div className="skeleton-card skeleton-active" style={{ height: 12, marginBottom: 8, width: '90%' }} />
              <div className="skeleton-card skeleton-active" style={{ height: 12, marginBottom: 8, width: '75%' }} />
              <div className="skeleton-card skeleton-active" style={{ height: 12, width: '50%' }} />
            </div>
          }>
            <VirtualizedMessageList
              virtuosoRef={virtuosoRef}
              messages={messages}
              hasOlderMessages={hasOlderMessages}
              onLoadOlder={handleLoadOlder}
              isStreaming={isStreaming}
              streamContent={visibleStreamContent}
              citations={visibleCitations}
              streamPhase={visibleStreamPhase}
              onRegenerate={handleRetry}
              onBranch={handleBranch}
              onShare={handleShare}
              canShare={canShare}
              onScrollToBottomChange={setShowScrollFab}
            />
          </Suspense>

          {showScrollFab && (
            <button className="scroll-fab section-enter" onClick={scrollToBottom} aria-label={t('new_messages') || 'Scroll to latest'} style={{ background: 'var(--color-bg-elevated)' }}>
              <ArrowDownOutlined />{t('new_messages') || 'Latest'}
            </button>
          )}
        </div>
      </div>

      <div style={{ position: 'fixed', bottom: 'calc(14px + env(safe-area-inset-bottom, 0px))', left: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: 100, pointerEvents: 'none' }}>
        <div style={{
          opacity: visibleAiStatusText ? 1 : 0,
          transform: visibleAiStatusText ? 'translateY(0)' : 'translateY(8px)',
          transition: 'opacity var(--motion-base) var(--motion-ease), transform var(--motion-base) var(--motion-ease)',
          marginBottom: 10,
          display: 'flex',
          justifyContent: 'center',
          pointerEvents: visibleAiStatusText ? 'auto' : 'none'
        }}>
          <div className="gemini-status-indicator" style={{ background: 'var(--color-bg-elevated)' }}>
            <span className="gemini-status-spinner" />
            <span>{visibleAiStatusText}</span>
          </div>
        </div>

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
            retryAfterSeconds={capacityRetrySeconds}
            answerMode={answerMode}
            canUseDeep={canUseDeep}
            thinkingEnabled={thinkingEnabled}
            canUseThinking={canUseThinking}
            onAnswerModeChange={(mode) => {
              if (mode === 'deep' && !canUseDeep) {
                setAnswerMode('fast');
                setModeNotice('error_deep_unavailable');
                return;
              }
              setAnswerMode(mode);
              setModeNotice(null);
            }}
            onThinkingChange={(enabled) => {
              if (enabled && !canUseThinking) {
                setThinkingEnabled(false);
                setModeNotice('error_thinking_unavailable');
                return;
              }
              setThinkingEnabled(enabled);
              setModeNotice(null);
            }}
          />
        </div>
      </div>
    </div>
  );
}
