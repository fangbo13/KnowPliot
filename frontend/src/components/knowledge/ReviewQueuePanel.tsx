/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Spec §3 UI: review queue for reviewers / knowledge admins / owners.
// Shows diff summary + conflict hints; approving can one-click mark the
// conflicting older documents as stale (spec §4 L1).

import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Empty, Input, Modal, Segmented, Space, Spin, Tag, message } from 'antd';
import { CheckOutlined, CloseOutlined, WarningOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { reviewApi } from '../../api/knowledge';
import type { ReviewRequestInfo } from '../../api/knowledge';
import { useAuth } from '../../auth/AuthProvider';

interface Props {
  onDecided?: () => void;
}

const decisionColor: Record<string, string> = {
  pending: 'gold',
  approved: 'green',
  rejected: 'red',
};

export function ReviewQueuePanel({ onDecided }: Props) {
  const { t } = useTranslation('common');
  const { user } = useAuth();
  const [decision, setDecision] = useState<'pending' | 'approved' | 'rejected'>('pending');
  const [reviews, setReviews] = useState<ReviewRequestInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [decideTarget, setDecideTarget] = useState<{ review: ReviewRequestInfo; action: 'approve' | 'reject' } | null>(null);
  const [comment, setComment] = useState('');
  const [markStaleIds, setMarkStaleIds] = useState<string[]>([]);
  const [deciding, setDeciding] = useState(false);

  const load = useCallback(async (which = decision) => {
    setLoading(true);
    try {
      const data = await reviewApi.getQueue(which);
      setReviews(data);
      setForbidden(false);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setForbidden(true);
      else message.error(t('review_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [decision, t]);

  useEffect(() => { void load(); }, [load]);

  const openDecide = (review: ReviewRequestInfo, action: 'approve' | 'reject') => {
    setDecideTarget({ review, action });
    setComment('');
    setMarkStaleIds([]);
  };

  const handleDecide = async () => {
    if (!decideTarget) return;
    setDeciding(true);
    try {
      if (decideTarget.action === 'approve') {
        await reviewApi.approve(decideTarget.review.id, {
          comment,
          mark_stale_ids: markStaleIds,
        });
        message.success(t('review_approved'));
      } else {
        await reviewApi.reject(decideTarget.review.id, { comment });
        message.success(t('review_rejected'));
      }
      setDecideTarget(null);
      void load();
      onDecided?.();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('review_decide_failed'));
    } finally {
      setDeciding(false);
    }
  };

  if (forbidden) {
    return <Alert type="info" showIcon message={t('review_no_permission')} />;
  }

  return (
    <div data-testid="review-queue-panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Segmented
          value={decision}
          onChange={(v) => setDecision(v as typeof decision)}
          options={[
            { value: 'pending', label: t('review_tab_pending') },
            { value: 'approved', label: t('review_tab_approved') },
            { value: 'rejected', label: t('review_tab_rejected') },
          ]}
        />
        <Button size="small" onClick={() => void load()}>{t('refresh')}</Button>
      </div>
      <Spin spinning={loading}>
        {reviews.length === 0 ? (
          <Empty description={t('review_queue_empty')} />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            {reviews.map((review) => {
              const diff = review.diff_summary as { added_lines?: number; removed_lines?: number };
              return (
                <Card key={review.id} size="small" style={{ borderColor: 'var(--color-border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: 260 }}>
                      <Space size="small" wrap>
                        <strong>{review.document.title}</strong>
                        <Tag color="blue">v{review.document.version}</Tag>
                        <Tag color={decisionColor[review.decision]}>{t(`review_decision_${review.decision}`)}</Tag>
                      </Space>
                      {/* Spec §3 watermark: submitter + time on every review card */}
                      <div style={{ marginTop: 6, fontSize: 12, color: 'var(--color-text-secondary)' }}>
                        {t('review_submitted_by', {
                          name: review.submitted_by.name,
                          date: new Date(review.created_at).toLocaleString(),
                        })}
                        {typeof diff.added_lines === 'number' && (
                          <span style={{ marginLeft: 12 }}>
                            <span style={{ color: 'var(--color-success)' }}>+{diff.added_lines}</span>
                            {' / '}
                            <span style={{ color: 'var(--color-error)' }}>-{diff.removed_lines}</span>
                          </span>
                        )}
                      </div>
                      {review.conflict_hints.length > 0 && (
                        <Alert
                          type="warning"
                          showIcon
                          icon={<WarningOutlined />}
                          style={{ marginTop: 8 }}
                          message={t('review_conflict_title', { count: review.conflict_hints.length })}
                          description={review.conflict_hints.map((hint) => (
                            <div key={hint.document_id} style={{ fontSize: 12 }}>
                              《{hint.title}》 — {t('review_conflict_score', { score: Math.round(hint.score * 100) })}
                            </div>
                          ))}
                        />
                      )}
                      {review.decision !== 'pending' && review.comment && (
                        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--color-text-tertiary)' }}>
                          {t('review_comment_label')}: {review.comment}
                        </div>
                      )}
                    </div>
                    {review.decision === 'pending' && (
                      review.submitted_by.id === user?.id ? (
                        <Tag color="warning" icon={<WarningOutlined />}>
                          {t('review_self_blocked')}
                        </Tag>
                      ) : (
                        <Space>
                          <Button
                            type="primary"
                            size="small"
                            icon={<CheckOutlined />}
                            onClick={() => openDecide(review, 'approve')}
                          >
                            {t('review_approve')}
                          </Button>
                          <Button
                            danger
                            size="small"
                            icon={<CloseOutlined />}
                            onClick={() => openDecide(review, 'reject')}
                          >
                            {t('review_reject')}
                          </Button>
                        </Space>
                      )
                    )}
                  </div>
                </Card>
              );
            })}
          </Space>
        )}
      </Spin>

      {decideTarget && (
        <Modal
          open
          title={decideTarget.action === 'approve' ? t('review_approve_title') : t('review_reject_title')}
          okText={decideTarget.action === 'approve' ? t('review_approve') : t('review_reject')}
          okButtonProps={decideTarget.action === 'reject' ? { danger: true } : undefined}
          cancelText={t('cancel')}
          confirmLoading={deciding}
          onOk={handleDecide}
          onCancel={() => setDecideTarget(null)}
        >
          <p style={{ marginBottom: 12 }}>
            《{decideTarget.review.document.title}》 v{decideTarget.review.document.version}
          </p>
          {decideTarget.action === 'approve' && decideTarget.review.conflict_hints.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 500, marginBottom: 6 }}>{t('review_mark_stale_hint')}</div>
              {decideTarget.review.conflict_hints.map((hint) => (
                <Checkbox
                  key={hint.document_id}
                  checked={markStaleIds.includes(hint.document_id)}
                  onChange={(e) => {
                    setMarkStaleIds((prev) => e.target.checked
                      ? [...prev, hint.document_id]
                      : prev.filter((id) => id !== hint.document_id));
                  }}
                  style={{ display: 'flex', marginLeft: 0 }}
                >
                  《{hint.title}》（{t('review_conflict_score', { score: Math.round(hint.score * 100) })}）
                </Checkbox>
              ))}
            </div>
          )}
          <Input.TextArea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={t('review_comment_placeholder')}
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
        </Modal>
      )}
    </div>
  );
}
