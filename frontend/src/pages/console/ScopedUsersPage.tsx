/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Dark/i18n/Layout spec §B2/§C: fully i18n-driven + migrated from the legacy
// page/page-head skeleton to the PageHeader/Surface primitives.

import { useCallback, useEffect, useState } from 'react';
import { Button, Input, Table, Tag, message } from 'antd';
import { useTranslation } from 'react-i18next';

import {
  scopedConsoleApi,
  type ScopedConsoleUser,
} from '../../api/scopedConsole';
import { PageHeader, Surface } from '../../design/primitives';

export default function ScopedUsersPage() {
  const { t } = useTranslation('common');
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<ScopedConsoleUser[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (nextQuery: string) => {
    setLoading(true);
    try {
      setUsers(await scopedConsoleApi.users(nextQuery));
    } catch {
      message.error(t('scoped_users_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load('');
  }, [load]);

  return (
    <div className="page section-enter">
      <PageHeader
        title={t('scoped_users_title')}
        description={t('scoped_users_description')}
      />
      <Surface>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <Input.Search
            aria-label={t('scoped_users_search_aria')}
            allowClear
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onSearch={(value) => void load(value.trim())}
            placeholder={t('email_label')}
          />
          <Button onClick={() => void load(query.trim())}>{t('refresh')}</Button>
        </div>
        <Table<ScopedConsoleUser>
          rowKey="id"
          loading={loading}
          dataSource={users}
          columns={[
            { title: t('email_label'), dataIndex: 'email', key: 'email' },
            {
              title: t('member_status'),
              dataIndex: 'is_active',
              key: 'is_active',
              render: (active: boolean) => (
                <Tag color={active ? 'green' : 'default'}>
                  {active ? t('status_active') : t('status_inactive')}
                </Tag>
              ),
            },
          ]}
          pagination={{ pageSize: 15 }}
        />
      </Surface>
    </div>
  );
}
