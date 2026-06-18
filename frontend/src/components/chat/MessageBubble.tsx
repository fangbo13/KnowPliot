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
        animation: `fadeInUp 0.3s ease-out ${isUser ? '0s' : '0.05s'} both`,
      }}
    >
      <div
        style={{
          maxWidth: '75%',
          padding: isUser ? '0' : '0',
        }}
      >
        {/* Message bubble */}
        <Card
          className={!isUser ? 'msg-bubble-assistant' : undefined}
          style={{
            background: isUser ? 'var(--user-msg-bg, #262626)' : 'var(--color-bg-container, white)',
            color: isUser ? 'white' : undefined,
            border: isUser ? 'none' : '1px solid var(--color-border-secondary, #f0f0f0)',
            borderLeft: isUser ? '4px solid var(--user-msg-accent, #FFE500)' : undefined,
            borderRadius: 12,
            boxShadow: isUser ? 'none' : 'var(--shadow-sm, none)',
          }}
          bodyStyle={{
            padding: isUser ? '12px 16px' : '12px 16px',
          }}
        >
          {isUser ? (
            <span style={{
              whiteSpace: 'pre-wrap',
              overflowWrap: 'break-word',
              wordBreak: 'break-word',
            }}>{message.content}</span>
          ) : (
            <div className="markdown-content" style={{
              color: 'var(--color-text, inherit)',
              overflowWrap: 'break-word',
              wordBreak: 'break-word',
            }}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
              {isStreaming && (
                <span style={{
                  display: 'inline-block',
                  width: 2,
                  height: 18,
                  background: 'var(--ey-yellow)',
                  marginLeft: 4,
                  verticalAlign: 'text-bottom',
                  animation: 'blink 0.8s ease-in-out infinite',
                  borderRadius: 1,
                  boxShadow: '0 0 4px rgba(255, 229, 0, 0.4)',
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
                    background: 'var(--color-bg-elevated, #fafafa)',
                    fontSize: 12,
                    maxWidth: 250,
                    overflow: 'hidden',
                  }}
                >
                  <Text strong ellipsis style={{ maxWidth: '100%', display: 'block' }}>
                    {cit.document_title}
                  </Text>
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
