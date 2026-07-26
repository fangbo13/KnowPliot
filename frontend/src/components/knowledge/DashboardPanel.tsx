/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Spec §5 UI: admin knowledge dashboard — review backlog, term coverage
// matrix (term × doc count / avg freshness heat), stale + expiring alerts,
// and the L6 quality loop metrics (refusal rate, confidence distribution,
// feedback / knowledge gaps).

import { useEffect, useRef, useState } from 'react';
import { Alert, Card, Col, Empty, Row, Spin, Statistic, Table, Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { vizApi } from '../../api/knowledge';
import type { DashboardData } from '../../api/knowledge';

function freshnessCell(value: number | null) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--color-text-tertiary)' }}>—</span>;
  const pct = Math.round(value * 100);
  const bg = value >= 0.7
    ? 'rgba(var(--color-success-rgb), 0.18)'
    : value >= 0.4
      ? 'rgba(var(--color-warning-rgb), 0.18)'
      : 'rgba(var(--color-error-rgb), 0.15)';
  return (
    <span style={{ background: bg, borderRadius: 6, padding: '2px 10px', fontSize: 12 }}>
      {pct}%
    </span>
  );
}

export function DashboardPanel() {
  const { t } = useTranslation('common');
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef(false);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    setLoading(true);
    vizApi.getDashboard()
      .then(setData)
      .catch((err: unknown) => {
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 403) setForbidden(true);
        else setError(t('dashboard_load_failed'));
      })
      .finally(() => setLoading(false));
  }, [t]);

  if (forbidden) return <Alert type="info" showIcon message={t('dashboard_no_permission')} />;
  if (error) return <Alert type="error" showIcon message={error} />;

  const quality = data?.quality;

  return (
    <Spin spinning={loading}>
      <div data-testid="knowledge-dashboard-panel" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* L6 quality metrics */}
        <Row gutter={16}>
          <Col span={6}>
            <Card size="small"><Statistic title={t('dashboard_total_answers')} value={quality?.total_answers ?? 0} /></Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title={t('dashboard_refusal_rate')}
                value={quality?.refusal_rate !== null && quality?.refusal_rate !== undefined
                  ? (quality.refusal_rate * 100).toFixed(1)
                  : '—'}
                suffix={quality?.refusal_rate !== null && quality?.refusal_rate !== undefined ? '%' : undefined}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small"><Statistic title={t('dashboard_pending_reviews')} value={data?.review_pending_count ?? 0} /></Card>
          </Col>
          <Col span={6}>
            <Card size="small"><Statistic title={t('dashboard_stale_count')} value={data?.stale_documents.length ?? 0} /></Card>
          </Col>
        </Row>

        {quality && (
          <Card size="small" title={t('dashboard_quality_title')}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: 13 }}>
              <span>{t('dashboard_needs_review')}: <strong>{quality.needs_human_review}</strong></span>
              <span>{t('dashboard_feedback')}: <strong>{quality.feedback_submitted}</strong></span>
              <span>{t('dashboard_gaps_created')}: <strong>{quality.knowledge_gaps_created}</strong></span>
              <span>{t('dashboard_gaps_resolved')}: <strong>{quality.knowledge_gaps_resolved}</strong></span>
              {Object.entries(quality.confidence_distribution).map(([label, count]) => (
                <Tag key={label}>{label}: {count}</Tag>
              ))}
            </div>
          </Card>
        )}

        {/* Review backlog */}
        <Card size="small" title={t('dashboard_backlog_title')}>
          {(data?.review_backlog || []).length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('dashboard_backlog_empty')} />
          ) : (
            <Table
              size="small"
              rowKey="review_id"
              pagination={false}
              dataSource={data!.review_backlog}
              columns={[
                { title: t('kb_title'), dataIndex: 'title', key: 'title', ellipsis: true },
                { title: t('kb_version'), dataIndex: 'version', key: 'version', width: 80, render: (v: number) => `v${v}` },
                { title: t('dashboard_submitted_by'), dataIndex: 'submitted_by', key: 'submitted_by', width: 160 },
                {
                  title: t('dashboard_conflicts'),
                  dataIndex: 'conflicts',
                  key: 'conflicts',
                  width: 90,
                  render: (n: number) => (n > 0 ? <Tag color="orange">{n}</Tag> : '—'),
                },
                {
                  title: t('dashboard_submitted_at'),
                  dataIndex: 'submitted_at',
                  key: 'submitted_at',
                  width: 180,
                  render: (v: string) => new Date(v).toLocaleString(),
                },
              ]}
            />
          )}
        </Card>

        {/* Coverage matrix */}
        <Card size="small" title={t('dashboard_coverage_title')}>
          {(data?.coverage || []).length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('dashboard_coverage_empty')} />
          ) : (
            <Table
              size="small"
              rowKey="term_id"
              pagination={{ pageSize: 8 }}
              dataSource={data!.coverage}
              columns={[
                { title: t('dashboard_dimension'), dataIndex: 'dimension', key: 'dimension', width: 130 },
                { title: t('dashboard_term'), dataIndex: 'label', key: 'label' },
                { title: t('dashboard_doc_count'), dataIndex: 'documents', key: 'documents', width: 100 },
                {
                  title: t('dashboard_avg_freshness'),
                  dataIndex: 'avg_freshness',
                  key: 'avg_freshness',
                  width: 130,
                  render: freshnessCell,
                },
              ]}
            />
          )}
          {(data?.uncovered_terms || []).length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>{t('dashboard_uncovered_title')}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {data!.uncovered_terms.map((term) => (
                  <Tooltip key={`${term.dimension}-${term.code}`} title={term.dimension}>
                    <Tag color="red">{term.label}</Tag>
                  </Tooltip>
                ))}
              </div>
            </div>
          )}
        </Card>

        {/* Stale + expiring alerts */}
        <Card size="small" title={t('dashboard_stale_title')}>
          {(data?.stale_documents || []).length === 0 && (data?.expiring_documents || []).length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('dashboard_stale_empty')} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {data!.stale_documents.map((doc) => (
                <div key={doc.id} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
                  <Tag color="orange">{t('status_stale')}</Tag>
                  <span style={{ flex: 1 }}>{doc.title}</span>
                  {freshnessCell(doc.freshness)}
                  <span style={{ color: 'var(--color-text-tertiary)', fontSize: 12 }}>
                    {new Date(doc.updated_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
              {data!.expiring_documents.map((doc) => (
                <div key={doc.id} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
                  <Tag color="volcano">{t('dashboard_expiring')}</Tag>
                  <span style={{ flex: 1 }}>{doc.title}</span>
                  <span style={{ color: 'var(--color-text-tertiary)', fontSize: 12 }}>
                    {t('kb_effective_to')}: {doc.effective_to}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </Spin>
  );
}
