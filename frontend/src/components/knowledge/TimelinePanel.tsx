/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Spec §5 UI: space-level timeline — monthly version-activity heat bars plus
// FY aggregation chips. Document-level version chains live in the version
// drawer on the documents tab (existing feature).

import { useEffect, useRef, useState } from 'react';
import { Alert, Empty, Spin, Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { vizApi } from '../../api/knowledge';
import type { TimelineData } from '../../api/knowledge';

export function TimelinePanel() {
  const { t } = useTranslation('common');
  const [data, setData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef(false);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    setLoading(true);
    vizApi.getTimeline()
      .then(setData)
      .catch(() => setError(t('timeline_load_failed')))
      .finally(() => setLoading(false));
  }, [t]);

  if (error) return <Alert type="error" showIcon message={error} />;

  const months = data?.months || [];
  const maxVersions = Math.max(1, ...months.map((m) => m.versions));

  return (
    <Spin spinning={loading}>
      <div data-testid="timeline-panel">
        <h3 style={{ marginBottom: 12, fontSize: 15 }}>{t('timeline_monthly_title')}</h3>
        {months.length === 0 && !loading ? (
          <Empty description={t('timeline_empty')} />
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-end',
              gap: 6,
              height: 180,
              padding: '12px 8px',
              border: '1px solid var(--color-border)',
              borderRadius: 12,
              overflowX: 'auto',
              background: 'var(--color-bg-container)',
            }}
          >
            {months.map((m) => {
              const height = Math.max(8, (m.versions / maxVersions) * 140);
              return (
                <Tooltip
                  key={m.month}
                  title={`${m.month} · ${t('timeline_versions', { count: m.versions })} · ${t('timeline_new_docs', { count: m.new_documents })}`}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 34 }}>
                    <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>{m.versions}</span>
                    <div
                      style={{
                        width: 22,
                        height,
                        borderRadius: 4,
                        background: `rgba(var(--color-accent-rgb), ${0.25 + 0.75 * (m.versions / maxVersions)})`,
                      }}
                    />
                    <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)', whiteSpace: 'nowrap' }}>
                      {m.month.slice(2)}
                    </span>
                  </div>
                </Tooltip>
              );
            })}
          </div>
        )}

        <h3 style={{ margin: '24px 0 12px', fontSize: 15 }}>{t('timeline_fy_title')}</h3>
        {(data?.fiscal_years || []).length === 0 ? (
          <div style={{ color: 'var(--color-text-tertiary)', fontSize: 13 }}>{t('timeline_fy_empty')}</div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {data!.fiscal_years.map((fy) => (
              <Tag key={fy.code} color="geekblue" style={{ padding: '4px 12px', fontSize: 13 }}>
                {fy.label} · {t('timeline_fy_docs', { count: fy.documents })}
              </Tag>
            ))}
          </div>
        )}
        <div style={{ marginTop: 16, fontSize: 12, color: 'var(--color-text-tertiary)' }}>
          {t('timeline_doc_hint')}
        </div>
      </div>
    </Spin>
  );
}
