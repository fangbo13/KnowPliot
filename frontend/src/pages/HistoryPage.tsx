/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeftOutlined, MessageOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Divider, Input, List, Segmented, Select, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';

import { chatApi, type HistoryStatusFilter, type HistoryTimeFilter } from '../api/chat';
import { useAuthorization } from '../auth/CapabilityProvider';
import MessageBubble from '../components/chat/MessageBubble';
import { EmptyState, PageHeader, Surface } from '../design/primitives';
import { useDebounce } from '../hooks/useDebounce';
import i18n from '../i18n';
import { useChatStore, type ChatSession, type Message } from '../store/chatStore';
import { computeGroupOrder, formatDate, getDateGroupKey, getGroupLabel } from '../utils/dateGroup';

const { Text } = Typography;

const TIME_FILTERS = new Set<HistoryTimeFilter>(['all', 'today', 'this_week', 'this_month', 'older']);
const STATUS_FILTERS = new Set<HistoryStatusFilter>(['all', 'partial', 'recovering', 'recovered', 'failed', 'terminal']);

function initialFilters() {
  const params = new URLSearchParams(window.location.search);
  const time = params.get('time') as HistoryTimeFilter | null;
  const status = params.get('status') as HistoryStatusFilter | null;
  return {
    query: params.get('q') ?? '',
    time: time && TIME_FILTERS.has(time) ? time : 'all' as HistoryTimeFilter,
    status: status && STATUS_FILTERS.has(status) ? status : 'all' as HistoryStatusFilter,
    cursor: params.get('cursor'),
  };
}

export default function HistoryPage() {
  const { t } = useTranslation('common');
  const canShare = useAuthorization().has('chat.share');
  const currentLang = i18n.language?.startsWith('zh') ? 'zh' : 'en';
  const { setActiveSession } = useChatStore();
  const navigate = useNavigate();
  const initial = useRef(initialFilters()).current;
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [previousCursor, setPreviousCursor] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(initial.cursor);
  const [viewingSessionId, setViewingSessionId] = useState<string | null>(null);
  const [viewMessages, setViewMessages] = useState<Message[]>([]);
  const [viewLoading, setViewLoading] = useState(false);
  const [viewLoadingOlder, setViewLoadingOlder] = useState(false);
  const [viewNextCursor, setViewNextCursor] = useState<string | null>(null);
  const [viewError, setViewError] = useState(false);
  const [viewOlderError, setViewOlderError] = useState(false);
  const [searchQuery, setSearchQuery] = useState(initial.query);
  const [timeFilter, setTimeFilter] = useState<HistoryTimeFilter>(initial.time);
  const [statusFilter, setStatusFilter] = useState<HistoryStatusFilter>(initial.status);
  const debouncedQuery = useDebounce(searchQuery, 300);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const viewRequestRef = useRef<AbortController | null>(null);

  useEffect(() => () => viewRequestRef.current?.abort(), []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (debouncedQuery.trim()) params.set('q', debouncedQuery.trim());
    if (timeFilter !== 'all') params.set('time', timeFilter);
    if (statusFilter !== 'all') params.set('status', statusFilter);
    if (cursor) params.set('cursor', cursor);
    const query = params.toString();
    window.history.replaceState({}, '', `${window.location.pathname}${query ? `?${query}` : ''}`);

    const controller = new AbortController();
    setLoading(true);
    setLoadError(false);
    chatApi.getSessions({
      query: debouncedQuery,
      time: timeFilter,
      status: statusFilter,
      cursor,
      signal: controller.signal,
    }).then((page) => {
      setSessions(page.results);
      setNextCursor(page.next);
      setPreviousCursor(page.previous);
    }).catch((error) => {
      if (error?.name !== 'CanceledError' && error?.name !== 'AbortError') {
        setSessions([]);
        setLoadError(true);
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [cursor, debouncedQuery, retryKey, statusFilter, timeFilter]);

  useEffect(() => {
    if (viewingSessionId && viewMessages.length > 0) {
      const timer = window.setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [viewMessages, viewingSessionId]);

  const handleSelectSession = async (id: string) => {
    viewRequestRef.current?.abort();
    const controller = new AbortController();
    viewRequestRef.current = controller;
    setViewingSessionId(id);
    setViewMessages([]);
    setViewNextCursor(null);
    setViewLoading(true);
    setViewLoadingOlder(false);
    setViewError(false);
    setViewOlderError(false);
    try {
      const page = await chatApi.getMessages(id, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setViewMessages(page.results.map((message) => ({
        id: message.id || crypto.randomUUID(),
        role: message.role,
        content: message.content || '',
        citations: message.citations || [],
        createdAt: message.created_at || message.createdAt || new Date().toISOString(),
      })).sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt)));
      setViewNextCursor(page.next);
    } catch {
      if (controller.signal.aborted) return;
      setViewMessages([]);
      setViewError(true);
    } finally {
      if (!controller.signal.aborted) setViewLoading(false);
    }
  };

  const loadOlderViewMessages = async () => {
    if (!viewingSessionId || !viewNextCursor || viewLoadingOlder) return;
    viewRequestRef.current?.abort();
    const controller = new AbortController();
    viewRequestRef.current = controller;
    setViewLoadingOlder(true);
    setViewOlderError(false);
    try {
      const page = await chatApi.getMessages(viewingSessionId, {
        cursor: viewNextCursor,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const olderMessages = page.results.map((message) => ({
        id: message.id || crypto.randomUUID(),
        role: message.role,
        content: message.content || '',
        citations: message.citations || [],
        createdAt: message.created_at || message.createdAt || new Date().toISOString(),
      }));
      setViewMessages((current) => {
        const unique = new Map(
          [...current, ...olderMessages].map((message) => [message.id, message]),
        );
        return [...unique.values()].sort(
          (a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt),
        );
      });
      setViewNextCursor(page.next);
    } catch {
      if (!controller.signal.aborted) setViewOlderError(true);
    } finally {
      if (!controller.signal.aborted) setViewLoadingOlder(false);
    }
  };

  const handleShare = async () => {
    if (!viewingSessionId || !canShare) return;
    const share = await chatApi.createShare(viewingSessionId);
    const url = `${window.location.origin}/shared/${share.token}`;
    if (navigator.share) await navigator.share({ title: t('conversation_history'), url });
    else await navigator.clipboard.writeText(url);
  };

  const resetCursor = () => setCursor(null);
  const hasFilters = Boolean(debouncedQuery.trim()) || timeFilter !== 'all' || statusFilter !== 'all';
  const recoveryLabel = (state: ChatSession['recoveryState']) => state
    ? t(`history_status_${state}`)
    : t('history_status_terminal');

  if (viewingSessionId) {
    return (
      <div className="page section-enter" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div className="page-head" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              viewRequestRef.current?.abort();
              setViewingSessionId(null);
              setViewMessages([]);
              setViewNextCursor(null);
              setViewLoadingOlder(false);
              setViewError(false);
              setViewOlderError(false);
            }}
            className="btn-press"
            aria-label={t('back_to_history')}
          />
          <h1 className="page-title" style={{ margin: 0, fontSize: 22 }}>
            {sessions.find((session) => session.id === viewingSessionId)?.title || t('new_conversation')}
          </h1>
        </div>
        <div className="page-inner" style={{ flex: 1, minHeight: 0, padding: '0 24px 24px' }}>
          {viewLoading ? (
            <div aria-label={t('loading')} className="skeleton-msg" style={{ width: '70%', padding: 18 }}>
              <div className="skeleton-line" style={{ width: '80%', height: 14 }} />
            </div>
          ) : viewError ? (
            <Alert
              showIcon
              type="error"
              message={t('load_error')}
              action={<Button onClick={() => handleSelectSession(viewingSessionId)}>{t('error_retry')}</Button>}
            />
          ) : (
            <div style={{ height: '100%', overflowY: 'auto', paddingRight: 4 }}>
              {viewOlderError && (
                <Alert
                  showIcon
                  type="error"
                  message={t('load_error')}
                  action={<Button onClick={loadOlderViewMessages}>{t('error_retry')}</Button>}
                  style={{ marginBottom: 12 }}
                />
              )}
              {viewNextCursor && (
                <div style={{ display: 'flex', justifyContent: 'center', paddingBottom: 12 }}>
                  <Button loading={viewLoadingOlder} onClick={loadOlderViewMessages}>
                    {t('load_older_messages', { ns: 'chat' })}
                  </Button>
                </div>
              )}
              {viewMessages.map((message) => <MessageBubble key={message.id} message={message} canShare={canShare} onShare={handleShare} />)}
              {viewMessages.length === 0 && <EmptyState icon="K" title={t('no_messages')} />}
              {viewMessages.length > 0 && (
                <>
                  <Divider />
                  <div style={{ display: 'flex', justifyContent: 'center' }}>
                    <Button
                      type="primary"
                      icon={<MessageOutlined />}
                      onClick={() => { setActiveSession(viewingSessionId); navigate('/chat'); }}
                    >
                      {t('continue_chat')}
                    </Button>
                  </div>
                </>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>
    );
  }

  const timeFilterOptions = [
    { label: t('filter_all'), value: 'all' },
    { label: t('filter_today'), value: 'today' },
    { label: t('filter_this_week'), value: 'this_week' },
    { label: t('filter_this_month'), value: 'this_month' },
    { label: t('filter_older'), value: 'older' },
  ];
  const statusFilterOptions = Array.from(STATUS_FILTERS.values()).map((value) => ({
    value,
    label: value === 'all' ? t('filter_all') : t(`history_status_${value}`),
  }));

  return (
    <div className="page section-enter" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <PageHeader title={t('conversation_history')} />
      <Surface className="page-inner kp-history-surface" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <Input.Search
            placeholder={t('search_history')}
            allowClear
            value={searchQuery}
            onChange={(event) => { setSearchQuery(event.target.value); resetCursor(); }}
            prefix={<SearchOutlined />}
            className="input-focus-float"
            style={{ maxWidth: 320, flex: '1 1 200px' }}
            aria-label={t('search_history')}
          />
          <Segmented
            options={timeFilterOptions}
            value={timeFilter}
            onChange={(value) => { setTimeFilter(value as HistoryTimeFilter); resetCursor(); }}
            aria-label={t('history_time_filter')}
          />
          <Select
            value={statusFilter}
            options={statusFilterOptions}
            onChange={(value) => { setStatusFilter(value); resetCursor(); }}
            aria-label={t('history_status_filter')}
            style={{ minWidth: 150 }}
          />
        </div>

        {loading ? (
          <div aria-label={t('loading')} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[1, 2, 3, 4].map((item) => (
              <div key={item} className="skeleton-msg" style={{ padding: 16 }}>
                <div className="skeleton-line" style={{ width: '60%', height: 14 }} />
              </div>
            ))}
          </div>
        ) : loadError ? (
          <Alert
            showIcon
            type="error"
            message={t('load_error')}
            action={<Button onClick={() => setRetryKey((value) => value + 1)}>{t('error_retry')}</Button>}
          />
        ) : sessions.length === 0 ? (
          <EmptyState
            className="kp-history-empty"
            icon="K"
            title={hasFilters ? t('no_search_results') : t('no_history')}
            action={!hasFilters ? (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/chat')}>
                {t('new_conversation')}
              </Button>
            ) : undefined}
          />
        ) : (
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', paddingRight: 4 }}>
            {(() => {
              const groupedSessions: Record<string, ChatSession[]> = {};
              sessions.forEach((session) => {
                const key = getDateGroupKey(session.updatedAt);
                (groupedSessions[key] ??= []).push(session);
              });
              return computeGroupOrder(groupedSessions).map((groupKey) => (
                <div key={groupKey} style={{ marginBottom: 16 }}>
                  <div className="kp-history-group-label">{getGroupLabel(groupKey, currentLang)}</div>
                  <List
                    dataSource={groupedSessions[groupKey]}
                    renderItem={(session) => (
                      <List.Item>
                        <Button
                          type="text"
                          onClick={() => handleSelectSession(session.id)}
                          className="btn-press"
                          style={{ width: '100%', textAlign: 'left', padding: '12px 16px', height: 'auto' }}
                          aria-label={`${session.title || t('new_conversation')}, ${formatDate(session.updatedAt)}`}
                        >
                          <List.Item.Meta
                            title={session.title || t('new_conversation')}
                            description={(
                              <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                <Text type="secondary">{formatDate(session.updatedAt)}</Text>
                                <Tag bordered={false}>{recoveryLabel(session.recoveryState)}</Tag>
                              </span>
                            )}
                          />
                        </Button>
                      </List.Item>
                    )}
                  />
                </div>
              ));
            })()}
            {(previousCursor || nextCursor) && (
              <div style={{ display: 'flex', justifyContent: 'center', gap: 8, paddingBottom: 8 }}>
                <Button disabled={!previousCursor} onClick={() => setCursor(previousCursor)}>{t('history_previous_page')}</Button>
                <Button disabled={!nextCursor} onClick={() => setCursor(nextCursor)}>{t('history_next_page')}</Button>
              </div>
            )}
          </div>
        )}
      </Surface>
    </div>
  );
}
