import { Card, Typography, Space } from 'antd';
import ReactMarkdown from 'react-markdown';
import type { Message } from '../../store/chatStore';

const { Text } = Typography;

interface Props {
  message: Message;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming = false }: Props) {
  const isUser = message.role === 'user';

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        padding: '8px 24px',
        marginBottom: 8,
      }}
    >
      <div
        style={{
          maxWidth: '75%',
          padding: isUser ? '10px 16px' : '0',
        }}
      >
        {/* Message bubble */}
        <Card
          style={{
            background: isUser ? '#E00033' : 'white',
            color: isUser ? 'white' : undefined,
            border: isUser ? 'none' : '1px solid #f0f0f0',
            borderRadius: 12,
            boxShadow: 'none',
          }}
          bodyStyle={{ padding: isUser ? '0' : '12px 16px' }}
        >
          {isUser ? (
            <span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>
          ) : (
            <div>
              <ReactMarkdown>{message.content}</ReactMarkdown>
              {isStreaming && (
                <span style={{
                  display: 'inline-block',
                  width: 8,
                  height: 16,
                  background: '#999',
                  marginLeft: 2,
                  animation: 'blink 1s infinite',
                }} />
              )}
            </div>
          )}
        </Card>

        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>Sources:</Text>
            <Space wrap style={{ marginTop: 4 }}>
              {message.citations.map((cit, i) => (
                <Card
                  key={i}
                  size="small"
                  style={{
                    background: '#fafafa',
                    fontSize: 12,
                    maxWidth: 250,
                  }}
                >
                  <Text strong>{cit.document_title}</Text>
                  {cit.page_number && <Text> · p.{cit.page_number}</Text>}
                  <br />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    Score: {cit.score}
                  </Text>
                </Card>
              ))}
            </Space>
          </div>
        )}
      </div>
    </div>
  );
}
