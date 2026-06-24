import { useTranslation } from 'react-i18next';
import { Card, Typography, Tooltip, message as antdMessage, Button, Popover } from 'antd';
import { CopyOutlined, CheckOutlined, ShareAltOutlined, ReloadOutlined, DownOutlined, RightOutlined, MoreOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { useState, useRef, useCallback } from 'react';
import type { Message, Citation } from '../../store/chatStore';

const { Text } = Typography;

// XSS protection: whitelist only safe Markdown elements
const ALLOWED_ELEMENTS = [
  'p', 'br', 'strong', 'em', 'u', 's', 'del', 'ins', 'sub', 'sup',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'blockquote', 'code', 'pre', 'hr',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'a', 'img',
  'details', 'summary',
];

// Convert score to relevance label
function getRelevanceLabel(score: number, t: (key: string) => string): string {
  if (score > 0.8) return t('high_relevance');
  if (score > 0.5) return t('medium_relevance');
  return t('low_relevance');
}

function getRelevanceColor(score: number): string {
  if (score > 0.8) return '#52c41a';  // green
  if (score > 0.5) return '#faad14';  // orange
  return '#8c8c8c';  // gray
}

interface Props {
  message: Message;
  isStreaming?: boolean;
  onRegenerate?: () => void;
}

export default function MessageBubble({ message, isStreaming = false, onRegenerate }: Props) {
  const { t } = useTranslation('chat');
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [longPressActive, setLongPressActive] = useState(false);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleTouchStart = useCallback(() => {
    // Long press visual feedback (P1-2)
    setLongPressActive(true);
    // Vibrate on devices that support it
    if (navigator.vibrate) navigator.vibrate(50);
    longPressTimer.current = setTimeout(() => {
      setMobileMenuOpen(true);
    }, 500);
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
    setLongPressActive(false);
  }, []);

  const handleTouchCancel = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
    setLongPressActive(false);
  }, []);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      antdMessage.success(t('copied') || '已复制');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = message.content;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      antdMessage.success(t('copied') || '已复制');
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: 'EY Onboarding AI',
          text: message.content,
        });
      } catch {
        // User cancelled share, fallback to copy
        handleCopy();
      }
    } else {
      handleCopy();
    }
  };

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
        className="msg-bubble-wrapper"
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        onTouchCancel={handleTouchCancel}
        style={{
          maxWidth: '75%',
          padding: '0',
          position: 'relative',
        }}
      >
        {/* Action buttons for assistant messages */}
        {!isUser && (
          <>
          <div
            className="msg-copy-btn"
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              opacity: 0,
              transition: 'opacity 0.2s ease',
              zIndex: 1,
              display: 'flex',
              gap: 2,
            }}
          >
            <Tooltip title={copied ? t('copied') : t('copy_message')}>
              <Button
                type="text"
                size="small"
                icon={copied ? <CheckOutlined style={{ color: '#52c41a' }} /> : <CopyOutlined />}
                onClick={handleCopy}
                aria-label={copied ? t('copied') : t('copy_message')}
                style={{
                  padding: '2px 6px',
                  color: copied ? '#52c41a' : 'var(--color-text-tertiary)',
                }}
              />
            </Tooltip>
            <Tooltip title={t('share_message')}>
              <Button
                type="text"
                size="small"
                icon={<ShareAltOutlined />}
                onClick={handleShare}
                aria-label={t('share_message')}
                style={{
                  padding: '2px 6px',
                  color: 'var(--color-text-tertiary)',
                }}
              />
            </Tooltip>
            {onRegenerate && (
              <Tooltip title={t('regenerate')}>
                <Button
                  type="text"
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={onRegenerate}
                  aria-label={t('regenerate')}
                  style={{
                    padding: '2px 6px',
                    color: 'var(--color-text-tertiary)',
                  }}
                />
              </Tooltip>
            )}
          </div>
          {/* Mobile always-visible "more" button */}
          <div
            className="mobile-msg-menu"
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              display: 'none',
            }}
          >
            <Popover
              content={
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => { handleCopy(); setMobileMenuOpen(false); }}>
                    {t('copy_message')}
                  </Button>
                  <Button type="text" size="small" icon={<ShareAltOutlined />} onClick={() => { handleShare(); setMobileMenuOpen(false); }}>
                    {t('share_message')}
                  </Button>
                  {onRegenerate && (
                    <Button type="text" size="small" icon={<ReloadOutlined />} onClick={() => { onRegenerate(); setMobileMenuOpen(false); }}>
                      {t('regenerate')}
                    </Button>
                  )}
                </div>
              }
              trigger="click"
              open={mobileMenuOpen}
              onOpenChange={setMobileMenuOpen}
              placement="bottomRight"
            >
              <Button
                type="text"
                size="small"
                icon={<MoreOutlined />}
                aria-label="Message actions"
                style={{ padding: '2px 6px', color: 'var(--color-text-tertiary)' }}
              />
            </Popover>
          </div>
          </>
        )}
        <Card
          className={`${longPressActive ? 'long-press-active' : ''} ${!isUser ? 'msg-bubble-assistant' : ''}`.trim()}
          style={{
            background: isUser ? 'var(--user-msg-bg, #262626)' : 'var(--color-bg-container, white)',
            color: isUser ? 'white' : undefined,
            border: isUser ? 'none' : '1px solid var(--color-border-secondary, #f0f0f0)',
            borderLeft: isUser ? '4px solid var(--user-msg-accent, #0052FF)' : undefined,
            borderRadius: 12,
            boxShadow: isUser ? 'none' : 'var(--shadow-sm, none)',
          }}
          bodyStyle={{
            padding: '12px 16px',
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

        {/* Collapsible citations for assistant messages */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <Button
              type="text"
              size="small"
              onClick={() => setSourcesExpanded(!sourcesExpanded)}
              icon={sourcesExpanded ? <DownOutlined /> : <RightOutlined />}
              style={{
                fontSize: 12,
                color: 'var(--color-text-secondary)',
                padding: '2px 4px',
                height: 'auto',
              }}
            >
              📎 {t('sources_count', { count: message.citations.length })}
            </Button>

            {sourcesExpanded && (
              <div
                className="citation-list"
                style={{
                  marginTop: 4,
                  padding: '6px 8px',
                  background: 'var(--color-bg-elevated, #fafafa)',
                  borderRadius: 8,
                  border: '1px solid var(--color-border-secondary)',
                }}
              >
                {message.citations.map((cit: Citation, i: number) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                      padding: '4px 0',
                      borderBottom: i < (message.citations?.length ?? 0) - 1 ? '1px solid var(--color-border-secondary)' : 'none',
                    }}
                  >
                    <span style={{
                      fontSize: 11,
                      color: 'var(--color-text-tertiary)',
                      minWidth: 18,
                      paddingTop: 1,
                    }}>
                      {i + 1}.
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Text
                        strong
                        ellipsis={{ tooltip: cit.document_title }}
                        style={{ fontSize: 12, display: 'block', maxWidth: '100%' }}
                      >
                        {cit.document_title}
                      </Text>
                      <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                        {cit.page_number && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            第 {cit.page_number} 页
                          </Text>
                        )}
                        <span
                          className="relevance-badge"
                          style={{
                            fontSize: 11,
                            color: getRelevanceColor(cit.score),
                            fontWeight: 500,
                          }}
                        >
                          {getRelevanceLabel(cit.score, t)}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
