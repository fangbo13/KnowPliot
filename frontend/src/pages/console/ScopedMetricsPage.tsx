/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Dark/i18n/Layout spec §B2/§C: i18n-driven, migrated to PageHeader +
// shared StatCard primitive (was inline glass-panel markup).

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { scopedConsoleApi } from '../../api/scopedConsole';
import type { SystemMetrics } from '../../api/admin';
import { PageHeader, StatCard, Status } from '../../design/primitives';

export default function ScopedMetricsPage() {
  const { t } = useTranslation('common');
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void scopedConsoleApi.metrics().then(
      (value) => { if (!cancelled) setMetrics(value); },
      () => { if (!cancelled) setError(true); },
    );
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="page section-enter">
      <PageHeader title={t('scoped_metrics_title')} description={t('scoped_metrics_description')} />
      {error && <Status role="alert" tone="error">{t('scoped_metrics_unavailable')}</Status>}
      {!metrics && !error && <Status role="status" tone="info">{t('loading')}</Status>}
      {metrics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
          <StatCard label={t('metric_users')} value={metrics.users.total} />
          <StatCard label={t('metric_active_users')} value={metrics.users.active} />
          <StatCard label={t('metric_questions')} value={metrics.usage.questions} />
          <StatCard label={t('metric_documents')} value={metrics.documents.total} />
        </div>
      )}
    </div>
  );
}
