/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Badge, Popover, Spin, Button, message } from 'antd';
import { BellOutlined, CheckOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  actOnNotification,
  fetchFeed,
  fetchUnreadCount,
  markAllRead,
  markRead,
  safeNotificationPath,
  type FeedItem,
} from '../api/notifications';
import { getRateLimitDetails, isAbortError } from '../api/client';

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
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const countControllerRef = useRef<AbortController | null>(null);
  const feedControllerRef = useRef<AbortController | null>(null);
  const requestSequence = useRef(0);

  const loadCount = useCallback(async () => {
    const controller = new AbortController();
    countControllerRef.current?.abort();
    countControllerRef.current = controller;
    try {
      const value = await fetchUnreadCount(controller.signal);
      if (!controller.signal.aborted) setCount(value);
    } catch (reason: unknown) {
      if (isAbortError(reason) || controller.signal.aborted) return;
      const rateLimit = getRateLimitDetails(reason);
      setError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    }
  }, []);

  useEffect(() => {
    loadCount();
    const id = setInterval(loadCount, 60000);
    return () => {
      clearInterval(id);
      countControllerRef.current?.abort();
    };
  }, [loadCount]);

  const loadFeed = useCallback(async () => {
    const sequence = ++requestSequence.current;
    feedControllerRef.current?.abort();
    const controller = new AbortController();
    feedControllerRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const nextItems = await fetchFeed(controller.signal);
      if (!controller.signal.aborted && sequence === requestSequence.current) setItems(nextItems);
    } catch (reason: unknown) {
      if (isAbortError(reason) || controller.signal.aborted || sequence !== requestSequence.current) return;
      const rateLimit = getRateLimitDetails(reason);
      setError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    } finally {
      if (!controller.signal.aborted && sequence === requestSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => () => {
    requestSequence.current += 1;
    countControllerRef.current?.abort();
    feedControllerRef.current?.abort();
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
    const path = safeNotificationPath(it.deep_link || it.link);
    if (path) { setOpen(false); navigate(path); }
  };

  const handleAction = async (item: FeedItem, action: 'accept' | 'decline') => {
    const key = `${item.id}:${action}`;
    if (actionBusy) return;
    setActionBusy(key);
    try {
      await actOnNotification(item, action);
      setItems((current) => current.map((candidate) => candidate.id === item.id ? {
        ...candidate,
        is_read: true,
        action_state: 'actioned',
        allowed_actions: [],
      } : candidate));
      setCount((current) => Math.max(0, current - (item.is_read ? 0 : 1)));
      message.success(action === 'accept' ? '邀请已接受。' : '邀请已拒绝。');
      const path = action === 'accept' ? safeNotificationPath(item.deep_link) : null;
      if (path) {
        setOpen(false);
        navigate(path);
      }
    } catch (reason: unknown) {
      const rateLimit = getRateLimitDetails(reason);
      message.error(rateLimit
        ? `请求过于频繁${rateLimit.retryAfterSeconds == null ? '' : `，请在 ${rateLimit.retryAfterSeconds} 秒后重试`}`
        : '该邀请已变化或无法处理，请刷新通知。');
      await loadFeed();
    } finally {
      setActionBusy(null);
    }
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
        {error ? (
          <div style={{ padding: 24 }}>
            <div role="alert" style={{ color: 'var(--color-error, #c0392b)', marginBottom: 12 }}>
              {error.code === 'rate_limited'
                ? `${t('rate_limited') || 'Too many requests'}${error.retryAfterSeconds == null ? '' : ` — retry in ${error.retryAfterSeconds}s`}`
                : (t('load_error') || 'Unable to load notifications')}
            </div>
            <Button size="small" onClick={() => void loadFeed()}>{t('error_retry') || 'Retry'}</Button>
          </div>
        ) : loading ? (
          <div style={{ padding: 32, textAlign: 'center' }}><Spin /></div>
        ) : items.length === 0 ? (
          <div style={{ padding: '28px 12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-placeholder)' }}>
              <div style={{ fontFamily: 'var(--font-family-serif)', fontSize: 32, opacity: 0.5, marginBottom: 12 }}>K</div>
              <span>{t('notifications_empty')}</span>
            </div>
          </div>
        ) : (
          items.map((it) => {
            const invitationActions = it.kind === 'notification'
              && it.action_kind === 'space_invitation'
              && it.action_state === 'available';
            return (
              <div
                key={it.id}
                style={{
                  background: it.is_read ? 'transparent' : 'var(--accent-soft)',
                  borderBottom: '1px solid var(--color-border-secondary)',
                }}
              >
                <button
                  className="hover-lift btn-press"
                  onClick={() => void handleItem(it)}
                  style={{
                    display: 'flex', gap: 10, width: '100%', textAlign: 'left',
                    padding: invitationActions ? '11px 14px 7px' : '11px 14px',
                    border: 'none', cursor: 'pointer', background: 'transparent',
                  }}
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
                {invitationActions && (
                  <div style={{ display: 'flex', gap: 8, padding: '0 14px 12px 31px' }}>
                    {it.allowed_actions.includes('accept') && (
                      <Button
                        type="primary"
                        size="small"
                        loading={actionBusy === `${it.id}:accept`}
                        disabled={Boolean(actionBusy)}
                        onClick={() => void handleAction(it, 'accept')}
                      >
                        接受
                      </Button>
                    )}
                    {it.allowed_actions.includes('decline') && (
                      <Button
                        size="small"
                        loading={actionBusy === `${it.id}:decline`}
                        disabled={Boolean(actionBusy)}
                        onClick={() => void handleAction(it, 'decline')}
                      >
                        拒绝
                      </Button>
                    )}
                  </div>
                )}
              </div>
            );
          })
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
      overlayClassName="ambient-glow section-enter"
      styles={{ body: { padding: 0, borderRadius: 14, overflow: 'hidden' } }}
    >
      <button className={`icon-btn hover-lift btn-press ${count > 0 ? 'ambient-glow' : ''}`} aria-label={t('notifications_aria')}>
        <Badge count={count} size="small" offset={[-1, 1]}>
          <BellOutlined />
        </Badge>
      </button>
    </Popover>
  );
}
