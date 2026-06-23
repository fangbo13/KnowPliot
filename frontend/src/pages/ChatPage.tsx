import { useTranslation } from 'react-i18next';
import { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Input, Button, Space, Spin, Alert, type InputRef } from 'antd';
import { SendOutlined, ReloadOutlined, PlusOutlined } from '@ant-design/icons';
import { useChatStore } from '../store/chatStore';
import WelcomeScreen from '../components/chat/WelcomeScreen';
import MessageBubble from '../components/chat/MessageBubble';

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

export default function ChatPageContainer() {
  const { t } = useTranslation('chat');
  const location = useLocation();
  const {
    messages,
    isStreaming,
    streamContent,
    citations,
    activeSessionId,
    isLoadingMessages,
    sendError,
    setSendError,
    sendMessage,
    loadMessages,
    resetSession,
  } = useChatStore();

  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<InputRef>(null);
  const loadedSessionRef = useRef<string | null>(null);

  // Reset loadedSessionRef when navigating to /chat — ensures messages reload
  // after returning from HistoryPage where setActiveSession was called
  useEffect(() => {
    loadedSessionRef.current = null;
  }, [location.pathname]);

  useEffect(() => {
    if (activeSessionId && activeSessionId !== loadedSessionRef.current) {
      loadedSessionRef.current = activeSessionId;
      loadMessages(activeSessionId);
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
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    if (isNearBottom || !isStreaming) {
      throttledScroll(isStreaming ? 'instant' : 'smooth');
    }
  }, [messages, streamContent, isStreaming, throttledScroll]);

  const handleSend = () => {
    if (!inputValue.trim() || isStreaming) return;
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

  const handleNewChat = () => {
    resetSession();
    inputRef.current?.focus();
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

  // Classify error message for better user feedback
  const getErrorDescription = (error: string) => {
    if (error === 'error_auth') return t('error_auth');
    if (error === 'error_server') return t('error_server');
    if (error === 'error_network') return t('error_network');
    if (error === 'error_generic') return t('error_generic');
    return t('error_generic');
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      flex: 1,
      minHeight: 0,
      maxWidth: 900,
      margin: '0 auto',
      width: '100%',
    }}>
      <div style={{
        flex: 1,
        overflowY: 'auto',
        paddingBottom: 120,
      }}>
        {/* Screen reader live region for streaming */}
        <div aria-live="polite" aria-atomic="false" className="sr-only">
          {isStreaming && streamContent && `AI正在输入: ${streamContent.slice(-100)}`}
          {isStreaming && !streamContent && (t('thinking') || '思考中...')}
        </div>

        {isLoadingMessages && messages.length === 0 && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '48px 0' }}>
            <Spin size="large" tip={t('loading_messages') || 'Loading...'} />
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

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onRegenerate={msg.role === 'assistant' ? handleRetry : undefined}
          />
        ))}

        {isStreaming && streamContent && (
          <MessageBubble
            message={{
              id: 'streaming',
              role: 'assistant',
              content: streamContent,
              citations,
              createdAt: new Date().toISOString(),
            }}
            isStreaming
          />
        )}

        {isStreaming && !streamContent && (
          <div style={{
            padding: '16px 24px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            animation: 'fadeIn 0.3s ease',
          }}>
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              {[0, 1, 2].map(i => (
                <div key={i} style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: 'var(--accent)',
                  animation: `dotBounce 1.4s ease-in-out ${i * 0.16}s infinite`,
                }} />
              ))}
            </div>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: 13, fontWeight: 500 }}>
              {t('thinking')}
            </span>
          </div>
        )}

        <div ref={messagesEndRef} />
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
          {/* New Chat button */}
          {activeSessionId && (
            <div style={{
              display: 'flex',
              justifyContent: 'center',
              marginBottom: 8,
              pointerEvents: 'auto',
            }}>
              <Button
                type="text"
                size="small"
                icon={<PlusOutlined />}
                onClick={handleNewChat}
                style={{
                  color: 'var(--color-text-secondary)',
                  fontSize: 12,
                  padding: '4px 12px',
                  height: 'auto',
                }}
              >
                {t('new_chat')}
              </Button>
            </div>
          )}

          <div style={{
            background: 'var(--color-bg-container)',
            border: '1px solid var(--color-border)',
            borderRadius: 16,
            padding: '8px 8px 8px 16px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04)',
            transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
          }}>
            <Space.Compact style={{ width: '100%' }}>
              <Input
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onPressEnter={handleSend}
                placeholder={t('placeholder')}
                disabled={isStreaming}
                size="large"
                maxLength={4000}
                aria-label={t('chat_input_label') || 'Type your message'}
                style={{
                  border: 'none',
                  boxShadow: 'none',
                  fontSize: 14,
                }}
                styles={{ input: { padding: '4px 0' } }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={!inputValue.trim() || isStreaming}
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
        </div>
      </div>
    </div>
  );
}
