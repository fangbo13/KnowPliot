import { useTranslation } from 'react-i18next';
import { Card, Typography, message as antdMessage, Button, Popover } from 'antd';
import { CopyOutlined, CheckOutlined, ShareAltOutlined, ReloadOutlined, DownOutlined, RightOutlined, MoreOutlined, PaperClipOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useState, useRef, useCallback, memo } from 'react';
import type { Message, Citation } from '../../store/chatStore';
import { useTheme } from '../../hooks/useTheme';
import ErrorBoundary from '../ErrorBoundary';
import CopyCodeButton from './CopyCodeButton';

const { Text } = Typography;

// XSS protection: whitelist only safe Markdown elements
// V4.0: Added 'span' for highlight.js syntax tokens, 'input' for GFM task list checkboxes
const ALLOWED_ELEMENTS = [
  'p', 'br', 'strong', 'em', 'u', 's', 'del', 'ins', 'sub', 'sup',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'blockquote', 'code', 'pre', 'hr',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'a', 'img',
  'details', 'summary',
  'span',   // V4.0 P0-2: highlight.js generates <span class="hljs-*"> for syntax tokens
  'input',  // V4.0 P0-3: GFM task lists generate <input type="checkbox">
];

// Convert score to relevance label
function getRelevanceLabel(score: number, t: (key: string) => string): string {
  if (score > 0.8) return t('high_relevance');
  if (score > 0.5) return t('medium_relevance');
  return t('low_relevance');
}

// V4.2 UI-V4.2-006: Replace hardcoded Ant Design light-mode colors with CSS variables
// for dark mode compatibility. #52c41a/#faad14/#8c8c8c had poor contrast in dark mode.
// [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-006]
function getRelevanceColor(score: number): string {
  if (score > 0.8) return 'var(--color-success)';    // green (adapts to dark)
  if (score > 0.5) return 'var(--color-warning)';    // orange (adapts to dark)
  return 'var(--color-text-tertiary)';                // gray (adapts to dark)
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
  const { effective: themeEffective } = useTheme();
  const isDark = themeEffective === 'dark';
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
          title: 'KnowPilot',
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
      background: 'var(--accent)',
      marginLeft: 4,
      verticalAlign: 'text-bottom',
      animation: 'blink 0.8s ease-in-out infinite',
      borderRadius: 1,
      boxShadow: 'var(--shadow-accent)',
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
            padding: 'var(--msg-bubble-padding, 12px 16px)',  // V4.0 UI-LOW-001: Use CSS variable for responsive padding
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
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeHighlight]}
                  components={{
                    // V4.6 DARK-002: Inline <code> override — hardcode dark mode colors via inline
                    // style (highest CSS priority). Ant Design 5.x darkAlgorithm CSS-in-JS injection
                    // overrides our globals.css rules for <code>, producing near-white background
                    // (#F1F5F9) + light text (#E2E8F0) = unreadable. Inline style bypasses all
                    // CSS-in-JS overrides. Code inside <pre> blocks uses the pre override instead.
                    code: ({ children, className, ...props }) => {
                      // Detect code blocks: rehype-highlight adds "language-*" / "hljs" className
                      // only to <code> inside <pre> blocks. Inline <code> has no className.
                      const isCodeBlock = className && (
                        String(className).includes('language-') ||
                        String(className).includes('hljs')
                      );

                      if (isCodeBlock) {
                        // Code block inside <pre> — don't apply inline styles;
                        // the pre component override + CSS handles code block styling
                        return <code className={className} {...props}>{children}</code>;
                      }

                      // Inline code: hardcode theme-specific colors to bypass CSS-in-JS overrides
                      const inlineCodeStyle: React.CSSProperties = isDark ? {
                        background: '#1E293B',
                        color: '#93C5FD',
                        border: '1px solid #334155',
                        borderRadius: 4,
                        padding: '2px 6px',
                        fontSize: 13,
                        fontFamily: "'JetBrains Mono', monospace",
                        wordBreak: 'break-word',
                      } : {
                        // Light mode: use CSS variables (no CSS-in-JS interference in light mode)
                        background: 'var(--muted)',
                        borderRadius: 4,
                        padding: '2px 6px',
                        fontSize: 13,
                        fontFamily: "'JetBrains Mono', monospace",
                        wordBreak: 'break-word',
                      };

                      return <code {...props} style={inlineCodeStyle}>{children}</code>;
                    },
                    pre: ({ children, node, ...props }) => {
                      // V4.0 P1-1: Wrap <pre> in a relative container for CopyCodeButton positioning
                      // Extract code content and language from the child <code> element via AST node
                      let codeContent = '';
                      let language = '';

                      // Traverse node children to find the code element and extract text
                      if (node?.children?.[0]) {
                        const codeNode = node.children[0] as any;
                        // Extract language from className (e.g. "language-python")
                        if (codeNode?.properties?.className) {
                          const classes = Array.isArray(codeNode.properties.className)
                            ? codeNode.properties.className
                            : [codeNode.properties.className];
                          const langClass = classes.find((c: string) => c.startsWith('language-'));
                          if (langClass) language = langClass.replace('language-', '');
                        }
                        // Extract text content from code node children
                        if (codeNode?.children) {
                          codeContent = codeNode.children
                            .map((c: any) => c.value || '')
                            .join('');
                        }
                      }

                      return (
                        <div style={{ position: 'relative' }}>
                          <pre {...props}>{children}</pre>
                          <CopyCodeButton code={codeContent} language={language} />
                        </div>
                      );
                    },
                    // V4.0 DEFECT-002: Protocol validation on href/src to prevent XSS.
                    // Without this, javascript:alert(1) in <a href> and data:image/svg+xml
                    // in <img src> would execute arbitrary code. Unsafe protocols render
                    // as plain text instead of interactive elements.
                    // [Source: V4.0/deep_sys_defect_list.md §DEFECT-002]
                    a: ({ href, children }) => {
                      const SAFE_HREF_PROTOCOLS = ['http://', 'https://', 'mailto:'];
                      const isSafe = href && SAFE_HREF_PROTOCOLS.some(p => href.toLowerCase().startsWith(p));
                      if (!isSafe) {
                        // Unsafe href (javascript:, data:, vbscript:, etc.) → render as plain text
                        return <span style={{ color: 'var(--color-text-secondary)' }}>{children}</span>;
                      }
                      return (
                        <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                      );
                    },
                    img: ({ src, alt }) => {
                      const SAFE_SRC_PROTOCOLS = ['http://', 'https://'];
                      const isSafe = src && SAFE_SRC_PROTOCOLS.some(p => src.toLowerCase().startsWith(p));
                      if (!isSafe) {
                        // Unsafe src (data: URI SVG XSS, javascript:, etc.) → render alt text or null
                        return alt ? <span style={{ color: 'var(--color-text-secondary)' }}>[{alt}]</span> : null;
                      }
                      return <img src={src} alt={alt || ''} loading="lazy" />;
                    },
                  }}
                >{message.content}</ReactMarkdown>
                </ErrorBoundary>
              )}
            </div>
          )}
        </Card>

        {/* Action buttons row for assistant messages — always visible below Card */}
        {!isUser && !isStreaming && (
          <div
            className="msg-action-row"
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              alignItems: 'center',
              gap: 8,
              marginTop: 6,
              padding: '2px 8px',
            }}
          >
            <Button
              type="text"
              size="small"
              icon={copied ? <CheckOutlined style={{ color: 'var(--color-success)' }} /> : <CopyOutlined />}
              onClick={handleCopy}
              disabled={disableActions}
              aria-label={copied ? t('copied') : t('copy_message')}
              className="msg-action-btn"
            >
              {copied ? (t('copied') || '已复制') : (t('copy_message') || '复制')}
            </Button>
            <Button
              type="text"
              size="small"
              icon={<ShareAltOutlined />}
              onClick={handleShare}
              disabled={disableActions}
              aria-label={t('share_message')}
              className="msg-action-btn"
            >
              {t('share_message') || '分享'}
            </Button>
            {onRegenerate && (
              <Button
                type="text"
                size="small"
                icon={<ReloadOutlined />}
                onClick={onRegenerate}
                disabled={disableActions}
                aria-label={t('regenerate')}
                className="msg-action-btn"
              >
                {t('regenerate') || '重新生成'}
              </Button>
            )}
            {/* Mobile "more" menu button — only shown on touch devices via CSS */}
            <Popover
              content={
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => { handleCopy(); setMobileMenuOpen(false); }}>
                    {t('copy_message') || '复制'}
                  </Button>
                  <Button type="text" size="small" icon={<ShareAltOutlined />} onClick={() => { handleShare(); setMobileMenuOpen(false); }}>
                    {t('share_message') || '分享'}
                  </Button>
                  {onRegenerate && (
                    <Button type="text" size="small" icon={<ReloadOutlined />} onClick={() => { onRegenerate(); setMobileMenuOpen(false); }}>
                      {t('regenerate') || '重新生成'}
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
                className="mobile-msg-menu-btn"
                style={{ display: 'none' }}
              />
            </Popover>
          </div>
        )}

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
            {/* V4.2 UI-V4.2-008: Replace emoji 📎 with semantic <PaperClipOutlined> icon
            * + aria-label for screen reader accessibility. Emoji Unicode names are
            * unpredictable across screen readers and cannot be localized.
            * [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-008] */}
            <PaperClipOutlined aria-label={t('sources')} />
            {' '}
            {t('sources_count', { count: message.citations.length })}
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
