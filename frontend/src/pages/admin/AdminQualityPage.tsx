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
import type { ComplianceExportJob, KnowledgeQualityReport, QualityExportDataset } from '../../api/admin';

const STATUS_COLORS: Record<string, string> = {
  submitted: 'default',
  pending_review: 'gold',
  in_review: 'blue',
  resolved: 'green',
  dismissed: 'red',
  withdrawn: 'default',
  open: 'gold',
  in_progress: 'blue',
  succeeded: 'green',
  failed: 'red',
  expired: 'red',
  queued: 'blue',
  processing: 'blue',
  wont_fix: 'red',
};

const DATASETS: QualityExportDataset[] = ['feedback', 'reviews', 'gaps', 'unanswered', 'documents'];

export default function AdminQualityPage() {
  const { t } = useTranslation('common');
  const [reviews, setReviews] = useState<FeedbackReview[]>([]);
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<FeedbackReview | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [slaFilter, setSlaFilter] = useState<string | undefined>();
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [report, setReport] = useState<KnowledgeQualityReport | null>(null);
  const [exportJobs, setExportJobs] = useState<ComplianceExportJob[]>([]);
  const [exportDataset, setExportDataset] = useState<QualityExportDataset>('feedback');

  const isSlaOverdue = (row: FeedbackReview) => {
    const ageDays = (Date.now() - new Date(row.created_at).getTime()) / 86400000;
    return (
      (row.status === 'pending_review' && ageDays > 3) ||
      (row.status === 'in_review' && ageDays > 5)
    );
  };

  const filteredReviews = useMemo(
    () => (slaFilter === 'overdue' ? reviews.filter(isSlaOverdue) : reviews),
    [reviews, slaFilter],
  );

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

  const loadReport = async () => {
    try {
      setReport(await adminApi.knowledgeQualityReport());
    } catch {
      message.error(t('quality_report_failed'));
    }
  };

  const loadExportJobs = async () => {
    try {
      setExportJobs(await adminApi.exportJobs());
    } catch {
      message.error(t('quality_export_jobs_failed'));
    }
  };

  useEffect(() => {
    loadReport();
    loadExportJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      setGaps(await adminApi.knowledgeGaps());
    } catch {
      message.error(t('quality_action_failed'));
    }
  };

  const saveBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const downloadDataset = async (dataset: QualityExportDataset) => {
    try {
      saveBlob(await adminApi.exportQualityDataset(dataset), `${dataset}.csv`);
    } catch {
      message.error(t('quality_export_failed'));
    }
  };

  const createAsyncExport = async () => {
    try {
      await adminApi.createExportJob({ dataset: exportDataset });
      message.success(t('quality_export_job_created'));
      await loadExportJobs();
    } catch {
      message.error(t('quality_export_failed'));
    }
  };

  const downloadExportJob = async (job: ComplianceExportJob) => {
    try {
      saveBlob(await adminApi.downloadExportJob(job.id), `${job.dataset}-${job.id}.csv`);
    } catch {
      message.error(t('quality_export_failed'));
    }
  };

  const retryExportJob = async (job: ComplianceExportJob) => {
    try {
      await adminApi.retryExportJob(job.id);
      message.success(t('quality_export_retry_queued'));
      await loadExportJobs();
    } catch {
      message.error(t('quality_export_retry_failed'));
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
      title: t('quality_sla'),
      key: 'sla',
      render: (_, row) => (
        isSlaOverdue(row)
          ? <Tag color="red">{t('quality_sla_overdue')}</Tag>
          : <Tag>{t('quality_sla_ok')}</Tag>
      ),
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
  ], [t, reviews]);

  return (
    <div>
      <Space direction="vertical" size={18} style={{ width: '100%' }}>
        <div>
          <h1 style={{ margin: 0 }}>{t('admin_nav_quality')}</h1>
          <p style={{ color: 'var(--color-text-secondary)', marginTop: 6 }}>{t('quality_page_subtitle')}</p>
        </div>

        {report && (
          <Space wrap>
            <Card size="small">
              <strong>{report.feedback.total}</strong>
              <div>{t('quality_feedback_total')}</div>
            </Card>
            <Card size="small">
              <strong>{Math.round(report.feedback.negative_rate * 100)}%</strong>
              <div>{t('quality_negative_rate')}</div>
            </Card>
            <Card size="small">
              <strong>{report.reviews.pending + report.reviews.in_review}</strong>
              <div>{t('quality_open_reviews')}</div>
            </Card>
            <Card size="small">
              <strong>{report.knowledge_gaps.open + report.knowledge_gaps.in_progress}</strong>
              <div>{t('quality_open_gaps')}</div>
            </Card>
          </Space>
        )}

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
            <Select
              allowClear
              placeholder={t('quality_sla')}
              style={{ width: 180 }}
              value={slaFilter}
              onChange={setSlaFilter}
              options={[{ value: 'overdue', label: t('quality_sla_overdue') }]}
            />
            <Button onClick={load}>{t('refresh')}</Button>
            <Button onClick={loadReport}>{t('quality_refresh_report')}</Button>
            <Button onClick={() => downloadDataset('feedback')}>{t('quality_export_feedback')}</Button>
            <Button onClick={() => downloadDataset('gaps')}>{t('quality_export_gaps')}</Button>
          </Space>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={filteredReviews}
            pagination={{ pageSize: 10 }}
            locale={{ emptyText: <Empty description={t('quality_empty')} /> }}
          />
        </Card>

        <Card title={t('quality_async_exports')}>
          <Space wrap style={{ marginBottom: 14 }}>
            <Select
              value={exportDataset}
              style={{ width: 190 }}
              onChange={setExportDataset}
              options={DATASETS.map((value) => ({
                value,
                label: t(`quality_dataset_${value}`),
              }))}
            />
            <Button type="primary" onClick={createAsyncExport}>
              {t('quality_create_export_job')}
            </Button>
            <Button onClick={loadExportJobs}>{t('refresh')}</Button>
          </Space>
          <Table
            rowKey="id"
            size="small"
            dataSource={exportJobs}
            pagination={{ pageSize: 5 }}
            locale={{ emptyText: <Empty description={t('quality_no_export_jobs')} /> }}
            columns={[
              {
                title: t('quality_export_dataset'),
                dataIndex: 'dataset',
                key: 'dataset',
                render: (value) => t(`quality_dataset_${value}`),
              },
              {
                title: t('quality_status'),
                dataIndex: 'status',
                key: 'status',
                render: (value) => <Tag color={STATUS_COLORS[value] || 'default'}>{value}</Tag>,
              },
              {
                title: t('quality_export_rows'),
                dataIndex: 'row_count',
                key: 'row_count',
              },
              {
                title: t('quality_export_error'),
                key: 'error',
                render: (_, job) => job.safe_error_summary || job.error_code || '—',
              },
              {
                title: t('quality_actions'),
                key: 'actions',
                render: (_, job) => (
                  <Space>
                    <Button
                      size="small"
                      disabled={job.status !== 'succeeded'}
                      onClick={() => downloadExportJob(job)}
                    >
                      {t('quality_download_export')}
                    </Button>
                    {job.status === 'failed' && (
                      <Button size="small" onClick={() => retryExportJob(job)}>
                        {t('quality_retry_export')}
                      </Button>
                    )}
                  </Space>
                ),
              },
            ]}
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
              {isSlaOverdue(selected) && <Tag color="red">{t('quality_sla_overdue')}</Tag>}
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
