/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useMemo, useState } from 'react';
import { Button, Card, Drawer, Empty, Input, Select, Space, Table, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import { adminApi, type FeedbackReview, type KnowledgeGap } from '../../api/admin';

const STATUS_COLORS: Record<string, string> = {
  submitted: 'default',
  pending_review: 'gold',
  in_review: 'blue',
  resolved: 'green',
  dismissed: 'red',
  withdrawn: 'default',
  open: 'gold',
  in_progress: 'blue',
  wont_fix: 'red',
};

export default function AdminQualityPage() {
  const { t } = useTranslation('common');
  const [reviews, setReviews] = useState<FeedbackReview[]>([]);
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<FeedbackReview | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [resolutionNotes, setResolutionNotes] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [reviewRows, gapRows] = await Promise.all([
        adminApi.feedbackReviews({ status: statusFilter, type: typeFilter }),
        adminApi.knowledgeGaps(),
      ]);
      setReviews(reviewRows);
      setGaps(gapRows);
    } catch {
      message.error(t('quality_load_failed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, typeFilter]);

  const mutateReview = async (fn: () => Promise<FeedbackReview>) => {
    try {
      const updated = await fn();
      setReviews((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      setSelected(updated);
      message.success(t('quality_action_success'));
    } catch {
      message.error(t('quality_action_failed'));
    }
  };

  const createGap = async () => {
    if (!selected) return;
    try {
      await adminApi.createKnowledgeGap({
        space: selected.space,
        feedback: selected.id,
        question: selected.review_context?.question || '',
        priority: 'medium',
        suggested_source: selected.suggested_source,
      });
      message.success(t('quality_gap_created'));
      const gapRows = await adminApi.knowledgeGaps();
      setGaps(gapRows);
    } catch {
      message.error(t('quality_action_failed'));
    }
  };

  const columns: ColumnsType<FeedbackReview> = useMemo(() => [
    {
      title: t('quality_type'),
      dataIndex: 'feedback_type',
      key: 'feedback_type',
      render: (value) => <Tag>{value}</Tag>,
    },
    {
      title: t('quality_status'),
      dataIndex: 'status',
      key: 'status',
      render: (value) => <Tag color={STATUS_COLORS[value] || 'default'}>{value}</Tag>,
    },
    {
      title: t('quality_question'),
      key: 'question',
      render: (_, row) => row.review_context?.question || '—',
      ellipsis: true,
    },
    {
      title: t('quality_reviewer'),
      dataIndex: 'reviewer_email',
      key: 'reviewer_email',
      render: (value) => value || '—',
    },
    {
      title: t('quality_actions'),
      key: 'actions',
      render: (_, row) => (
        <Button size="small" onClick={() => { setSelected(row); setResolutionNotes(row.resolution_notes || ''); }}>
          {t('quality_open')}
        </Button>
      ),
    },
  ], [t]);

  return (
    <div>
      <Space direction="vertical" size={18} style={{ width: '100%' }}>
        <div>
          <h1 style={{ margin: 0 }}>{t('admin_nav_quality')}</h1>
          <p style={{ color: 'var(--color-text-secondary)', marginTop: 6 }}>{t('quality_page_subtitle')}</p>
        </div>

        <Card>
          <Space wrap style={{ marginBottom: 14 }}>
            <Select
              allowClear
              placeholder={t('quality_status')}
              style={{ width: 180 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={['pending_review', 'in_review', 'resolved', 'dismissed', 'withdrawn'].map((value) => ({ value, label: value }))}
            />
            <Select
              allowClear
              placeholder={t('quality_type')}
              style={{ width: 180 }}
              value={typeFilter}
              onChange={setTypeFilter}
              options={['helpful', 'unhelpful', 'incorrect', 'outdated', 'missing_source'].map((value) => ({ value, label: value }))}
            />
            <Button onClick={load}>{t('refresh')}</Button>
          </Space>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={reviews}
            pagination={{ pageSize: 10 }}
            locale={{ emptyText: <Empty description={t('quality_empty')} /> }}
          />
        </Card>

        <Card title={t('quality_gaps')}>
          {gaps.length === 0 ? (
            <Empty description={t('quality_no_gaps')} />
          ) : (
            <Space direction="vertical" style={{ width: '100%' }}>
              {gaps.map((gap) => (
                <div key={gap.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span>{gap.question || gap.question_snapshot}</span>
                  <Space>
                    <Tag color={STATUS_COLORS[gap.status] || 'default'}>{gap.status}</Tag>
                    <Tag>{gap.priority}</Tag>
                  </Space>
                </div>
              ))}
            </Space>
          )}
        </Card>
      </Space>

      <Drawer
        title={t('quality_detail')}
        open={Boolean(selected)}
        width={640}
        onClose={() => setSelected(null)}
      >
        {selected && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Space>
              <Tag>{selected.feedback_type}</Tag>
              <Tag color={STATUS_COLORS[selected.status] || 'default'}>{selected.status}</Tag>
            </Space>
            <Card size="small" title={t('quality_question')}>
              {selected.review_context?.question || '—'}
            </Card>
            <Card size="small" title={t('quality_answer')}>
              {selected.review_context?.answer || '—'}
            </Card>
            <Card size="small" title={t('quality_feedback')}>
              <p>{selected.comment || '—'}</p>
              <p>{t('quality_suggested_source')}: {selected.suggested_source || '—'}</p>
            </Card>
            <Input.TextArea
              rows={4}
              value={resolutionNotes}
              onChange={(event) => setResolutionNotes(event.target.value)}
              placeholder={t('quality_resolution_notes')}
            />
            <Space wrap>
              <Button onClick={() => mutateReview(() => adminApi.claimFeedback(selected.id))}>
                {t('quality_claim')}
              </Button>
              <Button type="primary" onClick={() => mutateReview(() => adminApi.resolveFeedback(selected.id, { resolution_code: 'resolved', resolution_notes: resolutionNotes }))}>
                {t('quality_resolve')}
              </Button>
              <Button danger onClick={() => mutateReview(() => adminApi.dismissFeedback(selected.id, { resolution_code: 'dismissed', resolution_notes: resolutionNotes }))}>
                {t('quality_dismiss')}
              </Button>
              <Button onClick={() => mutateReview(() => adminApi.reopenFeedback(selected.id))}>
                {t('quality_reopen')}
              </Button>
              <Button onClick={createGap}>
                {t('quality_create_gap')}
              </Button>
            </Space>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
