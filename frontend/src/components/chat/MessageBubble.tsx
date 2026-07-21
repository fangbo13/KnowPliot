/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import { message as antdMessage } from 'antd';
import {
  CopyOutlined, CheckOutlined, ShareAltOutlined, ReloadOutlined, BranchesOutlined,
  DownOutlined, RightOutlined, PaperClipOutlined,
  LikeOutlined, DislikeOutlined, FlagOutlined, CloseOutlined,
} from '@ant-design/icons';
import { useEffect, useRef, useState, memo } from 'react';
import { motion } from 'framer-motion';
import { designTokens } from '../../design/tokens';
import type { Message, Citation, ChatExecutionSnapshot } from '../../store/chatStore';
import { chatApi } from '../../api/chat';
import ErrorBoundary from '../ErrorBoundary';
import { MarkdownView } from './markdown';
import StreamingMarkdown from './StreamingMarkdown';

const MESSAGE_TRANSITION_SECONDS = designTokens.motion.duration.base / 1000;

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

const SAFE_SNAPSHOT_FALLBACKS = new Set([
  'deep_mode_disabled', 'thinking_mode_disabled', 'deep_policy_unavailable',
  'thinking_not_allowed', 'thinking_budget_invalid', 'model_policy_not_ready',
  'legacy_thinking_unknown',
]);

function SnapshotDetails({ snapshot, t }: {
  snapshot: ChatExecutionSnapshot;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  const known = (snapshot.thinking_snapshot_known ?? snapshot.thinkingSnapshotKnown) !== false;
  const requestedMode = snapshot.requested_answer_mode || snapshot.requestedAnswerMode || 'fast';
  const effectiveMode = snapshot.answer_mode || snapshot.effectiveAnswerMode || requestedMode;
  const requestedThinking = snapshot.requested_thinking_enabled ?? snapshot.requestedThinkingEnabled ?? false;
  const effectiveThinking = snapshot.thinking_enabled ?? snapshot.thinkingEnabled ?? false;
  const budget = snapshot.thinking_budget ?? snapshot.thinkingBudget;
  const modelId = snapshot.model_id || snapshot.modelId || '';
  const rawFallback = snapshot.policy_fallback_code || snapshot.policyFallbackCode || '';
  const fallbackCode = rawFallback || (!known ? 'legacy_thinking_unknown' : '');
  const fallbackKey = fallbackCode
    ? (SAFE_SNAPSHOT_FALLBACKS.has(fallbackCode)
      ? fallbackCode
      : 'policy_fallback')
    : null;
  return (
    <details className="message-execution-snapshot">
      <summary>{t('processing_effective_snapshot')}</summary>
      <dl>
        <div><dt>{t('processing_requested_mode')}</dt><dd>{t(`answer_mode_${requestedMode}`)}</dd></div>
        <div><dt>{t('processing_effective_mode')}</dt><dd>{t(`answer_mode_${effectiveMode}`)}</dd></div>
        <div><dt>{t('processing_model')}</dt><dd>{modelId || t('processing_legacy_unknown')}</dd></div>
        <div><dt>{t('processing_requested_thinking')}</dt><dd>{known ? (requestedThinking ? t('thinking_mode_on') : t('thinking_mode_off')) : t('processing_legacy_unknown')}</dd></div>
        <div><dt>{t('processing_effective_thinking')}</dt><dd>{known ? (effectiveThinking ? t('thinking_mode_on') : t('thinking_mode_off')) : t('processing_legacy_unknown')}</dd></div>
        <div><dt>{t('processing_budget')}</dt><dd>{known && effectiveThinking && budget != null ? budget : (known ? t('processing_budget_not_applicable') : t('processing_legacy_unknown'))}</dd></div>
        {fallbackKey ? (
          <div>
            <dt>{t('processing_fallback')}</dt>
            <dd>
              <span>{t(`processing_fallback_${fallbackKey}`)}</span>
              <code>{fallbackKey}</code>
            </dd>
          </div>
        ) : null}
      </dl>
    </details>
  );
}

interface Props {
  message: Message;
  isStreaming?: boolean;
  disableActions?: boolean;
  canShare?: boolean;
  onRegenerate?: () => void;
  onBranch?: () => void;
  onShare?: () => void | Promise<void>;
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
function MessageBubble({ message, isStreaming = false, disableActions = false, canShare = false, onRegenerate, onBranch, onShare }: Props) {
  const { t } = useTranslation('chat');
  const isUser = message.role === 'user';
  const executionSnapshot = message.executionSnapshot ?? message.execution_snapshot;
  const [copied, setCopied] = useState(false);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [feedbackType, setFeedbackType] = useState<FeedbackType | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [issueType, setIssueType] = useState<FeedbackType>('incorrect');
  const [feedbackComment, setFeedbackComment] = useState('');
  const [suggestedSource, setSuggestedSource] = useState('');
  const [flagForReview, setFlagForReview] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const feedbackTriggerRef = useRef<HTMLButtonElement>(null);
  const feedbackWasOpenRef = useRef(false);

  useEffect(() => {
    if (feedbackWasOpenRef.current && !feedbackOpen) {
      feedbackTriggerRef.current?.focus();
    }
    feedbackWasOpenRef.current = feedbackOpen;
  }, [feedbackOpen]);

  useEffect(() => {
    if (!feedbackOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setFeedbackOpen(false);
      }
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [feedbackOpen]);
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
    if (onShare) {
      await onShare();
      return;
    }
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
      <motion.div 
        className="msg-row user"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: MESSAGE_TRANSITION_SECONDS, ease: [0.2, 0.8, 0.2, 1] }}
      >
        <div className="msg-bubble user">{message.content}</div>
      </motion.div>
    );
  }

  return (
    <motion.div 
      className="msg-row assistant"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: MESSAGE_TRANSITION_SECONDS, ease: [0.2, 0.8, 0.2, 1] }}
    >
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

      {!isStreaming && executionSnapshot ? (
        <SnapshotDetails snapshot={executionSnapshot} t={t} />
      ) : null}

      {!isStreaming && (
        <div className="msg-actions">
          <button className="msg-action-btn hover-lift btn-press" onClick={handleCopy} disabled={disableActions}
            aria-label={copied ? t('copied') : t('copy_message')}>
            {copied ? <CheckOutlined style={{ color: 'var(--color-success)' }} /> : <CopyOutlined />}
            {copied ? (t('copied') || 'Copied') : (t('copy_message') || 'Copy')}
          </button>
          {canShare && (
            <button className="msg-action-btn hover-lift btn-press" onClick={handleShare} disabled={disableActions}
              aria-label={t('share_message')}>
              <ShareAltOutlined />{t('share_message') || 'Share'}
            </button>
          )}
          {onRegenerate && (
            <button className="msg-action-btn hover-lift btn-press" onClick={onRegenerate} disabled={disableActions}
              aria-label={t('regenerate')}>
              <ReloadOutlined />{t('regenerate') || 'Retry'}
            </button>
          )}
          {onBranch && (
            <button className="msg-action-btn btn-press" onClick={onBranch} disabled={disableActions}
              aria-label={t('branch_conversation')}>
              <BranchesOutlined />{t('branch_conversation')}
            </button>
          )}
          {canGiveFeedback && (
            <>
              <button
                className={`msg-action-btn hover-lift btn-press ${feedbackType === 'helpful' ? 'active' : ''}`}
                onClick={() => submitSimpleFeedback('helpful')}
                disabled={feedbackBusy}
                aria-pressed={feedbackType === 'helpful'}
                aria-label={t('feedback_helpful')}
              >
                <LikeOutlined />{t('feedback_helpful') || 'Helpful'}
              </button>
              <button
                ref={feedbackTriggerRef}
                className={`msg-action-btn hover-lift btn-press ${feedbackType && feedbackType !== 'helpful' ? 'active' : ''}`}
                onClick={() => setFeedbackOpen((v) => !v)}
                disabled={feedbackBusy}
                aria-expanded={feedbackOpen}
                aria-label={t('feedback_unhelpful')}
              >
                <DislikeOutlined />{t('feedback_unhelpful') || 'Not helpful'}
              </button>
              {feedbackType && (
                <button
                  className="msg-action-btn hover-lift btn-press"
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
        <div
          className="msg-feedback-panel"
          role="form"
          aria-label={t('feedback_panel_label')}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              setFeedbackOpen(false);
            }
          }}
        >
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
            <button className="msg-action-btn hover-lift btn-press" onClick={submitDetailedFeedback} disabled={feedbackBusy}>
              {t('feedback_submit') || 'Submit'}
            </button>
            <button className="msg-action-btn hover-lift btn-press" onClick={() => setFeedbackOpen(false)} disabled={feedbackBusy}>
              {t('feedback_cancel') || 'Cancel'}
            </button>
          </div>
        </div>
      )}

      {message.role === 'assistant' && message.confidenceLabel && (
        <div className={`msg-quality msg-quality-${message.confidenceLabel}`}>
          <span>{t(`confidence_${message.confidenceLabel}`)}</span>
          {message.needsHumanReview && <span>{t('needs_human_review')}</span>}
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
              {message.citations.map((cit: Citation, i: number) => {
                const sourceUrl = cit.source_url?.startsWith('/api/v1/chat/citations/')
                  ? cit.source_url
                  : null;
                return (
                  <div key={cit.source_id ?? `${cit.document_id}-${i}`} className="citation-item">
                    <span className="citation-index">{i + 1}.</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {sourceUrl ? (
                        <a
                          className="citation-title"
                          href={sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                          title={cit.document_title}
                        >
                          {cit.document_title}
                        </a>
                      ) : (
                        <div className="citation-title" title={cit.document_title}>
                          {cit.document_title}
                        </div>
                      )}
                      {cit.snippet && <div className="citation-snippet">{cit.snippet}</div>}
                      <div className="citation-meta">
                        {cit.page_number != null && <span>{t('page_label', { n: cit.page_number, defaultValue: 'Page {{n}}' })}</span>}
                        <span className="relevance-badge" style={{ color: getRelevanceColor(cit.score) }}>
                          {getRelevanceLabel(cit.score, t)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}

const MemoizedMessageBubble = memo(MessageBubble, (prev, next) => {
  if (next.isStreaming) return false; // streaming bubble must update every frame
  return prev.message.id === next.message.id
    && prev.message.content === next.message.content
    && (prev.message.executionSnapshot ?? prev.message.execution_snapshot)
      === (next.message.executionSnapshot ?? next.message.execution_snapshot)
    && prev.isStreaming === next.isStreaming
    && prev.disableActions === next.disableActions
    && prev.canShare === next.canShare;
});

export default MemoizedMessageBubble;
export { MessageBubble as MessageBubbleRaw };
