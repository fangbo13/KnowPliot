/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useState } from 'react';
import { Badge, Popover, Spin, Empty, Button } from 'antd';
import { BellOutlined, CheckOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { fetchFeed, fetchUnreadCount, markAllRead, markRead, FeedItem } from '../api/notifications';

const LEVEL_COLOR: Record<string, string> = {
  info: 'var(--accent)',
  success: 'var(--color-success, #3f9142)',
  warning: 'var(--color-warning, #c8881b)',
  error: 'var(--color-error, #c0392b)',
};

function timeAgo(iso: string | null, zh: boolean): string {
  if (!iso) return '';
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return '';
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return zh ? '刚刚' : 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return zh ? `${m} 分钟前` : `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return zh ? `${h} 小时前` : `${h}h ago`;
  const days = Math.floor(h / 24);
  return zh ? `${days} 天前` : `${days}d ago`;
}

/**
 * V7.0 NotificationBell — top-bar bell with an unread badge and a dropdown feed
 * merging targeted notifications and broadcast announcements. Polls the unread
 * count every 60s; loads the full feed only when opened.
 */
export default function NotificationBell() {
  const { t, i18n } = useTranslation('common');
  const navigate = useNavigate();
  const zh = i18n.language?.startsWith('zh');
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const loadCount = useCallback(async () => {
    try { setCount(await fetchUnreadCount()); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    loadCount();
    const id = setInterval(loadCount, 60000);
    return () => clearInterval(id);
  }, [loadCount]);

  const loadFeed = useCallback(async () => {
    setLoading(true);
    try { setItems(await fetchFeed()); } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) loadFeed();
  };

  const handleItem = async (it: FeedItem) => {
    if (!it.is_read) {
      try { await markRead(it.id); } catch { /* ignore */ }
      setItems((prev) => prev.map((x) => (x.id === it.id ? { ...x, is_read: true } : x)));
      loadCount();
    }
    if (it.link) { setOpen(false); navigate(it.link); }
  };

  const handleMarkAll = async () => {
    try { await markAllRead(); } catch { /* ignore */ }
    setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
    setCount(0);
  };

  const panel = (
    <div style={{ width: 340, maxWidth: '90vw' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 14px', borderBottom: '1px solid var(--color-border-secondary)',
      }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{t('notifications_title')}</span>
        {count > 0 && (
          <Button type="text" size="small" icon={<CheckOutlined />} onClick={handleMarkAll}
            style={{ color: 'var(--accent-text)', fontWeight: 600 }}>
            {t('notifications_mark_all_read')}
          </Button>
        )}
      </div>

      <div style={{ maxHeight: 380, overflowY: 'auto' }}>
        {loading ? (
          <div style={{ padding: 32, textAlign: 'center' }}><Spin /></div>
        ) : items.length === 0 ? (
          <div style={{ padding: '28px 12px' }}>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('notifications_empty')} />
          </div>
        ) : (
          items.map((it) => (
            <button
              key={it.id}
              onClick={() => handleItem(it)}
              style={{
                display: 'flex', gap: 10, width: '100%', textAlign: 'left',
                padding: '11px 14px', border: 'none', cursor: 'pointer',
                background: it.is_read ? 'transparent' : 'var(--accent-soft)',
                borderBottom: '1px solid var(--color-border-secondary)',
                transition: 'background var(--dur) var(--ease-out)',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-fill-secondary, rgba(0,0,0,0.03))')}
              onMouseLeave={(e) => (e.currentTarget.style.background = it.is_read ? 'transparent' : 'var(--accent-soft)')}
            >
              <span style={{
                marginTop: 6, width: 7, height: 7, borderRadius: 4, flexShrink: 0,
                background: it.is_read ? 'transparent' : (LEVEL_COLOR[it.level] || 'var(--accent)'),
              }} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 13.5, fontWeight: it.is_read ? 500 : 600, color: 'var(--color-text)' }}>
                    {it.title}
                  </span>
                  {it.version && (
                    <span style={{
                      fontSize: 11, padding: '0 6px', borderRadius: 6, lineHeight: '16px',
                      background: 'var(--accent-soft)', color: 'var(--accent-text)', fontWeight: 600,
                    }}>{it.version}</span>
                  )}
                </span>
                {it.body && (
                  <span style={{ display: 'block', fontSize: 12.5, color: 'var(--color-text-secondary)', marginTop: 2, lineHeight: 1.5 }}>
                    {it.body}
                  </span>
                )}
                <span style={{ display: 'block', fontSize: 11.5, color: 'var(--color-text-tertiary, var(--color-text-secondary))', marginTop: 4 }}>
                  {timeAgo(it.created_at, !!zh)}
                </span>
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  );

  return (
    <Popover
      open={open}
      onOpenChange={onOpenChange}
      trigger="click"
      placement="bottomRight"
      content={panel}
      styles={{ body: { padding: 0, borderRadius: 14, overflow: 'hidden' } }}
    >
      <button className="icon-btn" aria-label={t('notifications_aria')}>
        <Badge count={count} size="small" offset={[-1, 1]}>
          <BellOutlined />
        </Badge>
      </button>
    </Popover>
  );
}
