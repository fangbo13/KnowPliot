import { useEffect, useState, useRef } from 'react';
import { Input, Button, Spin, Space } from 'antd';
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

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamContent]);

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
      height: 'calc(100vh - 120px)',
      maxWidth: 900,
      margin: '0 auto',
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

        {/* Thinking indicator */}
        {isStreaming && !streamContent && (
          <div style={{ padding: '12px 24px' }}>
            <Spin size="small" />
            <span style={{ marginLeft: 8, color: '#999' }}>Thinking...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div style={{
        padding: '16px 0',
        borderTop: '1px solid #f0f0f0',
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
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!inputValue.trim() || isStreaming}
            size="large"
          >
            Send
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
