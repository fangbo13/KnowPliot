/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// KB optimization spec §5.4: Obsidian-style Backlinks panel — lists documents
// that link TO the current document via [[wikilinks]] or doc links.
// KB/RAG audit spec P3 §B1: also lists this document's UNRESOLVED outgoing
// wikilinks (Obsidian gray links — the linked note does not exist yet).

import { useEffect, useState } from 'react';
import { Empty, List, Spin, Tag, Typography } from 'antd';
import { DisconnectOutlined, LinkOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { vizApi } from '../../api/knowledge';
import type { BacklinkInfo } from '../../api/knowledge';
import { documentApi } from '../../api/documents';

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
  const [unresolved, setUnresolved] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      vizApi.getBacklinks(documentId).catch(() => ({ backlinks: [] })),
      documentApi.getDocumentLinks(documentId).catch(() => ({ unresolved: [] })),
    ])
      .then(([backData, linkData]) => {
        if (cancelled) return;
        setBacklinks(backData.backlinks || []);
        setUnresolved(linkData.unresolved || []);
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

  if (backlinks.length === 0 && unresolved.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('kb_backlinks_empty')}
        style={{ margin: '12px 0' }}
      />
    );
  }

  return (
    <div>
      {backlinks.length > 0 && (
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
      )}
      {unresolved.length > 0 && (
        <List
          size="small"
          header={
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              <DisconnectOutlined style={{ marginRight: 6 }} />
              {t('kb_unresolved_links_title', { count: unresolved.length })}
            </Typography.Text>
          }
          dataSource={unresolved}
          renderItem={(title) => (
            <List.Item style={{ padding: '6px 8px' }}>
              {/* Obsidian gray link — the note does not exist yet. */}
              <Typography.Text style={{ flex: 1, color: 'var(--color-text-tertiary)' }} ellipsis>
                [[{title}]]
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                {t('kb_unresolved_link_hint')}
              </Typography.Text>
            </List.Item>
          )}
        />
      )}
    </div>
  );
}

export default BacklinksPanel;
