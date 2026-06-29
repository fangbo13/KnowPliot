import { useTranslation } from 'react-i18next';
import { message as antdMessage } from 'antd';
import {
  CopyOutlined, CheckOutlined, ShareAltOutlined, ReloadOutlined,
  DownOutlined, RightOutlined, PaperClipOutlined,
} from '@ant-design/icons';
import { useState, memo } from 'react';
import type { Message, Citation } from '../../store/chatStore';
import ErrorBoundary from '../ErrorBoundary';
import { MarkdownView } from './markdown';
import StreamingMarkdown from './StreamingMarkdown';

function getRelevanceLabel(score: number, t: (key: string) => string): string {
  if (score > 0.8) return t('high_relevance');
  if (score > 0.5) return t('medium_relevance');
  return t('low_relevance');
}
function getRelevanceColor(score: number): string {
  if (score > 0.8) return 'var(--color-success)';
  if (score > 0.5) return 'var(--color-warning)';
  return 'var(--color-text-tertiary)';
}

interface Props {
  message: Message;
  isStreaming?: boolean;
  disableActions?: boolean;
  onRegenerate?: () => void;
}

/**
 * Claude-style message row.
 *  - user: warm sand bubble, right-aligned.
 *  - assistant: labelled document text. Streaming uses block-incremental Markdown;
 *    the completed message renders the full authoritative Markdown once.
 *
 * React.memo (below) keeps non-streaming bubbles from re-parsing Markdown while a
 * different message streams — only the streaming bubble re-renders per frame.
 */
function MessageBubble({ message, isStreaming = false, disableActions = false, onRegenerate }: Props) {
  const { t } = useTranslation('chat');
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = message.content;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    setCopied(true);
    antdMessage.success(t('copied') || 'Copied');
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: 'KnowPilot', text: message.content });
        return;
      } catch { /* cancelled → fall through to copy */ }
    }
    handleCopy();
  };

  if (isUser) {
    return (
      <div className="msg-row user">
        <div className="msg-bubble user">{message.content}</div>
      </div>
    );
  }

  return (
    <div className="msg-row assistant">
      <div className="msg-assistant-label">
        <span className="msg-assistant-dot">K</span>
        <span className="msg-assistant-name">KnowPilot</span>
      </div>

      <div className="msg-bubble assistant">
        {isStreaming ? (
          <StreamingMarkdown content={message.content} />
        ) : (
          <div className="markdown-content">
            <ErrorBoundary
              title={t('markdown_error_title') || 'Rendering error'}
              description={t('markdown_error_desc') || 'There was a problem rendering this message'}
              retryText={t('markdown_error_retry') || 'Reload'}
            >
              <MarkdownView>{message.content}</MarkdownView>
            </ErrorBoundary>
          </div>
        )}
      </div>

      {!isStreaming && (
        <div className="msg-actions">
          <button className="msg-action-btn" onClick={handleCopy} disabled={disableActions}
            aria-label={copied ? t('copied') : t('copy_message')}>
            {copied ? <CheckOutlined style={{ color: 'var(--color-success)' }} /> : <CopyOutlined />}
            {copied ? (t('copied') || 'Copied') : (t('copy_message') || 'Copy')}
          </button>
          <button className="msg-action-btn" onClick={handleShare} disabled={disableActions}
            aria-label={t('share_message')}>
            <ShareAltOutlined />{t('share_message') || 'Share'}
          </button>
          {onRegenerate && (
            <button className="msg-action-btn" onClick={onRegenerate} disabled={disableActions}
              aria-label={t('regenerate')}>
              <ReloadOutlined />{t('regenerate') || 'Retry'}
            </button>
          )}
        </div>
      )}

      {message.citations && message.citations.length > 0 && (
        <div className="msg-citations">
          <button className="citation-toggle" onClick={() => setSourcesExpanded((v) => !v)}>
            {sourcesExpanded ? <DownOutlined /> : <RightOutlined />}
            <PaperClipOutlined aria-label={t('sources')} />
            {t('sources_count', { count: message.citations.length })}
          </button>
          {sourcesExpanded && (
            <div className="citation-list">
              {message.citations.map((cit: Citation, i: number) => (
                <div key={i} className="citation-item">
                  <span className="citation-index">{i + 1}.</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="citation-title" title={cit.document_title}>{cit.document_title}</div>
                    <div className="citation-meta">
                      {cit.page_number != null && <span>{t('page_label', { n: cit.page_number, defaultValue: 'Page {{n}}' })}</span>}
                      <span className="relevance-badge" style={{ color: getRelevanceColor(cit.score) }}>
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
  );
}

const MemoizedMessageBubble = memo(MessageBubble, (prev, next) => {
  if (next.isStreaming) return false; // streaming bubble must update every frame
  return prev.message.id === next.message.id
    && prev.message.content === next.message.content
    && prev.isStreaming === next.isStreaming
    && prev.disableActions === next.disableActions;
});

export default MemoizedMessageBubble;
export { MessageBubble as MessageBubbleRaw };
