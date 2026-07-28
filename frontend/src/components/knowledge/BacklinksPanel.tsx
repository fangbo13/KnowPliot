/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// KB optimization spec §5.4: Obsidian-style Backlinks panel — lists documents
// that link TO the current document via [[wikilinks]] or doc links.

import { useEffect, useState } from 'react';
import { Empty, List, Spin, Tag, Typography } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { vizApi } from '../../api/knowledge';
import type { BacklinkInfo } from '../../api/knowledge';

interface Props {
  documentId: string;
  /** Called when the user clicks a backlink entry (open that document). */
  onOpenDocument?: (documentId: string) => void;
  /** Bump to re-fetch (e.g. after saving an edit). */
  refreshKey?: number;
}

export function BacklinksPanel({ documentId, onOpenDocument, refreshKey = 0 }: Props) {
  const { t } = useTranslation('common');
  const [backlinks, setBacklinks] = useState<BacklinkInfo[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    vizApi
      .getBacklinks(documentId)
      .then((data) => {
        if (!cancelled) setBacklinks(data.backlinks);
      })
      .catch(() => {
        if (!cancelled) setBacklinks([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId, refreshKey]);

  if (loading) {
    return (
      <div style={{ padding: 16, textAlign: 'center' }}>
        <Spin size="small" />
      </div>
    );
  }

  if (backlinks.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('kb_backlinks_empty')}
        style={{ margin: '12px 0' }}
      />
    );
  }

  return (
    <List
      size="small"
      header={
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          <LinkOutlined style={{ marginRight: 6 }} />
          {t('kb_backlinks_title', { count: backlinks.length })}
        </Typography.Text>
      }
      dataSource={backlinks}
      renderItem={(item) => (
        <List.Item
          style={{ cursor: onOpenDocument ? 'pointer' : 'default', padding: '6px 8px' }}
          onClick={() => onOpenDocument?.(item.id)}
        >
          <Typography.Text ellipsis style={{ flex: 1 }}>
            {item.title}
          </Typography.Text>
          {item.anchor_text && (
            <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }} ellipsis>
              “{item.anchor_text}”
            </Typography.Text>
          )}
          {item.status === 'stale' && <Tag color="warning">{t('kb_status_stale')}</Tag>}
        </List.Item>
      )}
    />
  );
}

export default BacklinksPanel;
