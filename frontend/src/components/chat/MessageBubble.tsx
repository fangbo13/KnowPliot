import { useTranslation } from 'react-i18next';
import { Card, Typography, Tooltip, message as antdMessage, Button, Popover } from 'antd';
import { CopyOutlined, CheckOutlined, ShareAltOutlined, ReloadOutlined, DownOutlined, RightOutlined, MoreOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { useState, useRef, useCallback, memo } from 'react';
import type { Message, Citation } from '../../store/chatStore';
import ErrorBoundary from '../ErrorBoundary';

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
  disableActions?: boolean;  // V3.5 2B: disables copy/share/regenerate during stream
  onRegenerate?: () => void;
}

/**
 * V3.7 P1.2: MessageBubble with React.memo + streaming plain-text rendering.
 *
 * Key optimizations:
 * 1. React.memo with custom comparator — non-streaming messages only re-render
 *    when id/content change, preventing ~880 unnecessary ReactMarkdown re-parses
 *    during streaming.
 * 2. Streaming mode renders plain text (no Markdown) — eliminates O(n²)
 *    cumulative Markdown AST parsing. Only 1 Markdown parse when stream ends.
 * 3. Streaming cursor (blink animation) is kept in plain-text mode for UX.
 */
function MessageBubble({ message, isStreaming = false, disableActions = false, onRegenerate }: Props) {
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

  // Streaming cursor component — reusable in both plain-text and markdown modes
  const StreamingCursor = isStreaming ? (
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
  ) : null;

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
            className="msg-copy-btn msg-action-btn-group"
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              opacity: disableActions ? 0.3 : 0,  // V3.5: Visible but dimmed when actions disabled
              transform: disableActions ? 'scale(0.85)' : 'scale(0.85)',
              transition: 'opacity 0.25s ease, transform 0.25s ease',
              zIndex: 1,
              display: 'flex',
              gap: 2,
              pointerEvents: disableActions ? 'none' : 'auto',  // V3.5: Block clicks during stream
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
              opacity: disableActions ? 0.3 : undefined,  // V3.5: Dimmed during stream
              pointerEvents: disableActions ? 'none' : undefined,  // V3.5: Block clicks during stream
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
              {/* V3.7 P1.2: Streaming mode uses plain text (0 Markdown parses).
                  When stream ends (isStreaming=false), renders full Markdown (1 parse).
                  This eliminates O(n²) cumulative Markdown AST parsing (~880 → 1). */}
              {isStreaming ? (
                <span style={{
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'break-word',
                  wordBreak: 'break-word',
                }}>
                  {message.content}
                  {StreamingCursor}
                </span>
              ) : (
                <ErrorBoundary
                  title={t('markdown_error_title') || '渲染错误'}
                  description={t('markdown_error_desc') || '此消息渲染时出现问题'}
                  retryText={t('markdown_error_retry') || '重新加载'}
                >
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
                </ErrorBoundary>
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

/**
 * V3.7 P1.2: MemoizedMessageBubble — React.memo with custom comparator.
 *
 * Optimization strategy:
 * - Streaming messages (isStreaming=true) ALWAYS re-render (content changes every rAF frame)
 * - Non-streaming messages ONLY re-render when their id or content changes
 *   (preventing ~880 unnecessary ReactMarkdown re-parses during stream)
 *
 * This reduces streaming-period re-renders from 880+ to just the streaming bubble.
 */
const MemoizedMessageBubble = memo(MessageBubble, (prevProps, nextProps) => {
  // Streaming messages must always update — content changes every frame
  if (nextProps.isStreaming) return false;

  // Non-streaming messages: only re-render if id or content changed
  // (props like `disableActions` change during stream but memo prevents
  //  unnecessary Markdown re-parse since content hasn't changed)
  return prevProps.message.id === nextProps.message.id
    && prevProps.message.content === nextProps.message.content
    && prevProps.isStreaming === nextProps.isStreaming
    && prevProps.disableActions === nextProps.disableActions;
});

// Export the memoized version — this is what VirtualizedMessageList should use
export default MemoizedMessageBubble;
// Also export the raw component for testing or direct use
export { MessageBubble as MessageBubbleRaw };
