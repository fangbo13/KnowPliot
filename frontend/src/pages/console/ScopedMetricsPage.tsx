/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useState } from 'react';

import { scopedConsoleApi } from '../../api/scopedConsole';
import type { SystemMetrics } from '../../api/admin';

export default function ScopedMetricsPage() {
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
    <div className="page">
      <div className="page-inner">
        <header className="page-head"><h1 className="page-title">Scoped metrics</h1></header>
        {error && <p role="alert">Metrics are temporarily unavailable.</p>}
        {!metrics && !error && <p role="status">Loading metrics…</p>}
        {metrics && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginTop: 24 }}>
            {[
              ['Users', metrics.users.total],
              ['Active users', metrics.users.active],
              ['Questions', metrics.usage.questions],
              ['Documents', metrics.documents.total],
            ].map(([label, value]) => (
              <section key={String(label)} className="glass-panel" style={{ padding: 22, borderRadius: 14 }}>
                <div style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>{label}</div>
                <div style={{ marginTop: 8, fontSize: 28, fontWeight: 600 }}>{value}</div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
