import { useTranslation } from 'react-i18next';
import { Card, Typography, Space } from 'antd';
import ReactMarkdown from 'react-markdown';
import type { Message } from '../../store/chatStore';

const { Text } = Typography;

// XSS protection: whitelist only safe Markdown elements
// Block: script, iframe, object, embed, form, input, style, link, meta, base
const ALLOWED_ELEMENTS = [
  'p', 'br', 'strong', 'em', 'u', 's', 'del', 'ins', 'sub', 'sup',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'blockquote', 'code', 'pre', 'hr',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'a', 'img',
  'details', 'summary',
];

interface Props {
  message: Message;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming = false }: Props) {
  const { t } = useTranslation('chat');
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
        <Card
          className={!isUser ? 'msg-bubble-assistant' : undefined}
          style={{
            background: isUser ? 'var(--user-msg-bg, #262626)' : 'var(--color-bg-container, white)',
            color: isUser ? 'white' : undefined,
            border: isUser ? 'none' : '1px solid var(--color-border-secondary, #f0f0f0)',
            borderLeft: isUser ? '4px solid var(--user-msg-accent, #0052FF)' : undefined,
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
              <ReactMarkdown
                allowedElements={ALLOWED_ELEMENTS}
                unwrapDisallowed={true}
                components={{
                  a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noopener noreferrer">
                      {children}
                    </a>
                  ),
                  img: ({ src, alt }) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={src} alt={alt || ''} loading="lazy" />
                  ),
                }}
              >{message.content}</ReactMarkdown>
              {isStreaming && (
                <span style={{
                  display: 'inline-block',
                  width: 2,
                  height: 18,
                  background: '#0052FF',
                  marginLeft: 4,
                  verticalAlign: 'text-bottom',
                  animation: 'blink 0.8s ease-in-out infinite',
                  borderRadius: 1,
                  boxShadow: '0 0 4px rgba(0, 82, 255, 0.4)',
                }} />
              )}
            </div>
          )}
        </Card>

        {!isUser && message.citations && message.citations.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>{t('sources')}</Text>
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
                  {cit.page_number && <Text> 路 p.{cit.page_number}</Text>}
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
