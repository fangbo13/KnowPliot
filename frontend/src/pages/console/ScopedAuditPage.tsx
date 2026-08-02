/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Dark/i18n/Layout spec §B2/§C: i18n-driven, bare <table> replaced with the
// standard antd Table inside a Surface.

import { useEffect, useState } from 'react';
import { Table } from 'antd';
import { useTranslation } from 'react-i18next';

import type { AuditLog } from '../../api/admin';
import { scopedConsoleApi } from '../../api/scopedConsole';
import { PageHeader, Status, Surface } from '../../design/primitives';

export default function ScopedAuditPage({ spaceId }: { spaceId?: string }) {
  const { t } = useTranslation('common');
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
    <div className="page section-enter">
      <PageHeader title={t('scoped_audit_title')} description={t('scoped_audit_description')} />
      {error && <Status role="alert" tone="error">{t('scoped_audit_unavailable')}</Status>}
      {!error && (
        <Surface>
          <Table<AuditLog>
            rowKey="id"
            loading={loading}
            dataSource={logs}
            locale={{ emptyText: t('scoped_audit_empty') }}
            columns={[
              {
                title: t('audit_col_time'),
                dataIndex: 'created_at',
                key: 'created_at',
                render: (value: string) => new Date(value).toLocaleString(),
              },
              { title: t('audit_col_action'), dataIndex: 'action', key: 'action' },
              { title: t('audit_col_result'), dataIndex: 'result', key: 'result' },
              { title: t('audit_col_target'), dataIndex: 'target_type', key: 'target_type' },
            ]}
            pagination={{ pageSize: 15 }}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        </Surface>
      )}
    </div>
  );
}
