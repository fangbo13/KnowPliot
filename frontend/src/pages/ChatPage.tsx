import { useTranslation } from 'react-i18next';
import { useEffect, useState, useRef, useCallback } from 'react';
import { Input, Button, Space, Spin, Alert } from 'antd';
import { SendOutlined, ReloadOutlined } from '@ant-design/icons';
import { useChatStore } from '../store/chatStore';
import WelcomeScreen from '../components/chat/WelcomeScreen';
import MessageBubble from '../components/chat/MessageBubble';

// Throttle helper for scroll optimization
function throttle<T extends (...args: unknown[]) => void>(fn: T, limit: number): T {
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
  } = useChatStore();

  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef(null);
  const loadedSessionRef = useRef<string | null>(null);

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

  if (!activeSessionId && messages.length === 0) {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto', padding: '40px 16px' }}>
        <WelcomeScreen onQuickAction={handleQuickAction} />
      </div>
    );
  }

  // Classify error message for better user feedback
  const getErrorDescription = (error: string) => {
    if (error.includes('401') || error.includes('authentication')) {
      return t('error_auth') || 'API authentication failed. Please check backend configuration.';
    }
    if (error.includes('500') || error.includes('Server error')) {
      return t('error_server') || 'Server error. Please try again later.';
    }
    if (error.includes('NetworkError') || error.includes('fetch') || error.includes('Network')) {
      return t('error_network') || 'Network error. Please check your connection.';
    }
    return error;
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
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
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
          <MessageBubble key={msg.id} message={msg} />
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

      <div style={{
        padding: '16px 24px 24px',
        background: 'var(--color-bg-container)',
        borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0',
        boxShadow: '0 -2px 10px rgba(0,0,0,0.03)',
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
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!inputValue.trim() || isStreaming}
            size="large"
            style={{ minWidth: 56, padding: inputValue.trim() ? '0 16px' : '0 20px', fontWeight: 600 }}
          >
            {inputValue.trim() ? '' : t('send')}
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
