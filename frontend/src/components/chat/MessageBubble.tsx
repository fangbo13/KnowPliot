/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import { message as antdMessage } from 'antd';
import {
  CopyOutlined, CheckOutlined, ShareAltOutlined, ReloadOutlined,
  DownOutlined, RightOutlined, PaperClipOutlined,
  LikeOutlined, DislikeOutlined, FlagOutlined, CloseOutlined,
} from '@ant-design/icons';
import { useEffect, useState, memo } from 'react';
import type { Message, Citation } from '../../store/chatStore';
import { chatApi } from '../../api/chat';
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

type FeedbackType = 'helpful' | 'unhelpful' | 'incorrect' | 'outdated' | 'missing_source';

function isPersistedUuid(id: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
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
  const [feedbackType, setFeedbackType] = useState<FeedbackType | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [issueType, setIssueType] = useState<FeedbackType>('incorrect');
  const [feedbackComment, setFeedbackComment] = useState('');
  const [suggestedSource, setSuggestedSource] = useState('');
  const [flagForReview, setFlagForReview] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const canGiveFeedback = !isStreaming && !disableActions && isPersistedUuid(message.id);

  useEffect(() => {
    let cancelled = false;
    if (!canGiveFeedback) return undefined;
    chatApi.getFeedback(message.id)
      .then((feedback) => {
        if (cancelled || !feedback || feedback.status === 'withdrawn') return;
        const currentType = feedback.type || feedback.feedback_type;
        setFeedbackType(currentType);
        if (currentType && currentType !== 'helpful') {
          setIssueType(currentType);
          setFeedbackComment(feedback.comment || '');
          setSuggestedSource(feedback.suggested_source || '');
          setFlagForReview(Boolean(feedback.flag_for_review));
        }
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [canGiveFeedback, message.id]);

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

  const submitSimpleFeedback = async (type: FeedbackType) => {
    if (!canGiveFeedback) return;
    setFeedbackBusy(true);
    try {
      await chatApi.updateFeedback(message.id, { type, flag_for_review: false });
      setFeedbackType(type);
      setFeedbackOpen(false);
      antdMessage.success(t('feedback_saved') || 'Feedback saved');
    } catch {
      antdMessage.error(t('feedback_failed') || 'Feedback failed');
    } finally {
      setFeedbackBusy(false);
    }
  };

  const submitDetailedFeedback = async () => {
    if (!canGiveFeedback) return;
    setFeedbackBusy(true);
    try {
      await chatApi.updateFeedback(message.id, {
        type: issueType,
        comment: feedbackComment,
        suggested_source: suggestedSource,
        flag_for_review: flagForReview,
      });
      setFeedbackType(issueType);
      setFeedbackOpen(false);
      antdMessage.success(t('feedback_saved') || 'Feedback saved');
    } catch {
      antdMessage.error(t('feedback_failed') || 'Feedback failed');
    } finally {
      setFeedbackBusy(false);
    }
  };

  const withdrawFeedback = async () => {
    if (!canGiveFeedback) return;
    setFeedbackBusy(true);
    try {
      await chatApi.withdrawFeedback(message.id);
      setFeedbackType(null);
      setFeedbackOpen(false);
      setFeedbackComment('');
      setSuggestedSource('');
      setFlagForReview(false);
      antdMessage.success(t('feedback_withdrawn') || 'Feedback withdrawn');
    } catch {
      antdMessage.error(t('feedback_failed') || 'Feedback failed');
    } finally {
      setFeedbackBusy(false);
    }
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
          {canGiveFeedback && (
            <>
              <button
                className={`msg-action-btn ${feedbackType === 'helpful' ? 'active' : ''}`}
                onClick={() => submitSimpleFeedback('helpful')}
                disabled={feedbackBusy}
                aria-pressed={feedbackType === 'helpful'}
                aria-label={t('feedback_helpful')}
              >
                <LikeOutlined />{t('feedback_helpful') || 'Helpful'}
              </button>
              <button
                className={`msg-action-btn ${feedbackType && feedbackType !== 'helpful' ? 'active' : ''}`}
                onClick={() => setFeedbackOpen((v) => !v)}
                disabled={feedbackBusy}
                aria-expanded={feedbackOpen}
                aria-label={t('feedback_unhelpful')}
              >
                <DislikeOutlined />{t('feedback_unhelpful') || 'Not helpful'}
              </button>
              {feedbackType && (
                <button
                  className="msg-action-btn"
                  onClick={withdrawFeedback}
                  disabled={feedbackBusy}
                  aria-label={t('feedback_withdraw')}
                >
                  <CloseOutlined />{t('feedback_withdraw') || 'Withdraw'}
                </button>
              )}
            </>
          )}
        </div>
      )}

      {feedbackOpen && canGiveFeedback && (
        <div className="msg-feedback-panel" role="form" aria-label={t('feedback_panel_label')}>
          <label>
            <span>{t('feedback_issue_type')}</span>
            <select
              value={issueType}
              onChange={(event) => setIssueType(event.target.value as FeedbackType)}
              disabled={feedbackBusy}
            >
              <option value="unhelpful">{t('feedback_type_unhelpful')}</option>
              <option value="incorrect">{t('feedback_type_incorrect')}</option>
              <option value="outdated">{t('feedback_type_outdated')}</option>
              <option value="missing_source">{t('feedback_type_missing_source')}</option>
            </select>
          </label>
          <label>
            <span>{t('feedback_comment')}</span>
            <textarea
              value={feedbackComment}
              onChange={(event) => setFeedbackComment(event.target.value)}
              placeholder={t('feedback_comment_placeholder') || ''}
              disabled={feedbackBusy}
            />
          </label>
          <label>
            <span>{t('feedback_source')}</span>
            <input
              value={suggestedSource}
              onChange={(event) => setSuggestedSource(event.target.value)}
              placeholder={t('feedback_source_placeholder') || ''}
              disabled={feedbackBusy}
            />
          </label>
          <label className="msg-feedback-check">
            <input
              type="checkbox"
              checked={flagForReview}
              onChange={(event) => setFlagForReview(event.target.checked)}
              disabled={feedbackBusy}
            />
            <span><FlagOutlined /> {t('feedback_flag_for_review')}</span>
          </label>
          <div className="msg-feedback-actions">
            <button className="msg-action-btn" onClick={submitDetailedFeedback} disabled={feedbackBusy}>
              {t('feedback_submit') || 'Submit'}
            </button>
            <button className="msg-action-btn" onClick={() => setFeedbackOpen(false)} disabled={feedbackBusy}>
              {t('feedback_cancel') || 'Cancel'}
            </button>
          </div>
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
