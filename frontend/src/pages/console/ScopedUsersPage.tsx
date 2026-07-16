/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Input, Table, Tag, message } from 'antd';

import {
  scopedConsoleApi,
  type ScopedConsoleUser,
} from '../../api/scopedConsole';

export default function ScopedUsersPage() {
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<ScopedConsoleUser[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (nextQuery: string) => {
    setLoading(true);
    try {
      setUsers(await scopedConsoleApi.users(nextQuery));
    } catch {
      message.error('Failed to load scoped users');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load('');
  }, [load]);

  return (
    <div className="page">
      <div className="page-inner">
        <div className="page-head">
          <h1 className="page-title">Scoped users</h1>
          <p style={{ color: 'var(--color-text-secondary)' }}>
            Only people inside your assigned governance scope are listed.
          </p>
        </div>
        <Card className="glass-panel">
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <Input.Search
              aria-label="Search scoped users"
              allowClear
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onSearch={(value) => void load(value.trim())}
              placeholder="Search email"
            />
            <Button onClick={() => void load(query.trim())}>Refresh</Button>
          </div>
          <Table<ScopedConsoleUser>
            rowKey="id"
            loading={loading}
            dataSource={users}
            columns={[
              { title: 'Email', dataIndex: 'email', key: 'email' },
              {
                title: 'Status',
                dataIndex: 'is_active',
                key: 'is_active',
                render: (active: boolean) => (
                  <Tag color={active ? 'green' : 'default'}>
                    {active ? 'Active' : 'Inactive'}
                  </Tag>
                ),
              },
            ]}
            pagination={{ pageSize: 15 }}
          />
        </Card>
      </div>
    </div>
  );
}
