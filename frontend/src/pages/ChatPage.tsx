import { useEffect, useState, useRef } from 'react';
import { Input, Button, Space } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { useChatStore } from '../store/chatStore';
import WelcomeScreen from '../components/chat/WelcomeScreen';
import MessageBubble from '../components/chat/MessageBubble';

export default function ChatPageContainer() {
  const {
    messages,
    isStreaming,
    streamContent,
    citations,
    activeSessionId,
    sendMessage,
  } = useChatStore();

  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef(null);

  // Auto-scroll: instant during streaming, smooth for completed messages
  useEffect(() => {
    const container = messagesEndRef.current?.parentElement;
    if (!container) return;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    if (isNearBottom || !isStreaming) {
      messagesEndRef.current?.scrollIntoView({
        behavior: isStreaming ? 'instant' : 'smooth',
      });
    }
  }, [messages, streamContent, isStreaming]);

  const handleSend = () => {
    if (!inputValue.trim() || isStreaming) return;
    sendMessage(inputValue.trim());
    setInputValue('');
  };

  const handleQuickAction = (question: string) => {
    sendMessage(question);
  };

  if (!activeSessionId && messages.length === 0) {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto', padding: '40px 16px' }}>
        <WelcomeScreen onQuickAction={handleQuickAction} />
      </div>
    );
  }

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
      {/* Messages area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Streaming message */}
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

        {/* Thinking indicator - animated dots */}
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
                  background: 'var(--ey-yellow)',
                  animation: `dotBounce 1.4s ease-in-out ${i * 0.16}s infinite`,
                }} />
              ))}
            </div>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: 13, fontWeight: 500 }}>
              Thinking...
            </span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area - floating bar style */}
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
            placeholder="Type your question here..."
            disabled={isStreaming}
            size="large"
            maxLength={4000}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!inputValue.trim() || isStreaming}
            size="large"
            style={{ minWidth: 56, padding: '0 20px', fontWeight: 600 }}
          >
            {inputValue.trim() ? '' : 'Send'}
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
