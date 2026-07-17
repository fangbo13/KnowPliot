/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useState } from 'react';

import type { AuditLog } from '../../api/admin';
import { scopedConsoleApi } from '../../api/scopedConsole';

export default function ScopedAuditPage({ spaceId }: { spaceId?: string }) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void scopedConsoleApi.audit(spaceId ? { space: spaceId } : {}).then(
      (rows) => {
        if (!cancelled) {
          setLogs(rows);
          setLoading(false);
        }
      },
      () => {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      },
    );
    return () => { cancelled = true; };
  }, [spaceId]);

  return (
    <div className="page">
      <div className="page-inner">
        <header className="page-head"><h1 className="page-title">Audit</h1></header>
        {loading && <p role="status">Loading audit events…</p>}
        {error && <p role="alert">Audit events are temporarily unavailable.</p>}
        {!loading && !error && (
          <div className="glass-panel" style={{ marginTop: 24, overflowX: 'auto', borderRadius: 14 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr><th>Time</th><th>Action</th><th>Result</th><th>Target</th></tr></thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td>{new Date(log.created_at).toLocaleString()}</td>
                    <td>{log.action}</td>
                    <td>{log.result}</td>
                    <td>{log.target_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {logs.length === 0 && <p style={{ padding: 24 }}>No audit events in this scope.</p>}
          </div>
        )}
      </div>
    </div>
  );
}
