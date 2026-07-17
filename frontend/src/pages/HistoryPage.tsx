/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import { useState, useEffect, useRef, useMemo } from 'react';
import { List, Typography, Button, Divider, Input, Segmented, Pagination } from 'antd';
import { PlusOutlined, ArrowLeftOutlined, MessageOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useChatStore, type Message } from '../store/chatStore';
import { chatApi } from '../api/chat';
import MessageBubble from '../components/chat/MessageBubble';
import { useDebounce } from '../hooks/useDebounce';
import { getDateGroupKey, getGroupLabel, computeGroupOrder, formatDate } from '../utils/dateGroup';
import i18n from '../i18n';
import { useAuthorization } from '../auth/CapabilityProvider';
import { EmptyState, PageHeader, Surface } from '../design/primitives';

const { Text } = Typography;

type TimeFilter = 'all' | 'today' | 'this_week' | 'this_month' | 'older';

export default function HistoryPage() {
  const { t } = useTranslation('common');
  const canShare = useAuthorization().has('chat.share');
  // V3.6 HIGH-001: Use i18n language for unified date group labels
  const currentLang = i18n.language?.startsWith('zh') ? 'zh' : 'en';
  const { sessions, loadSessions, setActiveSession } = useChatStore();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [viewingSessionId, setViewingSessionId] = useState<string | null>(null);
  const [viewMessages, setViewMessages] = useState<Message[]>([]);
  const [viewLoading, setViewLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('all');
  const debouncedQuery = useDebounce(searchQuery, 300);
  const [currentPage, setCurrentPage] = useState(1);
  const PAGE_SIZE = 20;

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedQuery, timeFilter]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadSessions().finally(() => setLoading(false));
  }, [loadSessions]);

  // Scroll to bottom when messages load
  useEffect(() => {
    if (viewingSessionId && viewMessages.length > 0) {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    }
  }, [viewMessages, viewingSessionId]);

  // Filter sessions based on search query and time filter
  const filteredSessions = useMemo(() => {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfWeek = new Date(startOfToday);
    startOfWeek.setDate(startOfToday.getDate() - startOfToday.getDay()); // Sunday
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

    return sessions.filter((session) => {
      // Search filter
      if (debouncedQuery) {
        const title = (session.title || '').toLowerCase();
        const query = searchQuery.toLowerCase();
        if (!title.includes(query)) return false;
      }

      // Time filter
      if (timeFilter === 'all') return true;

      const updatedAt = session.updatedAt ? new Date(session.updatedAt) : null;
      if (!updatedAt) return timeFilter === 'older';

      switch (timeFilter) {
        case 'today':
          return updatedAt >= startOfToday;
        case 'this_week':
          return updatedAt >= startOfWeek;
        case 'this_month':
          return updatedAt >= startOfMonth;
        // V4.1 BUG-013: Use 30-day threshold (matching sidebar's getDateGroupKey)
        // instead of startOfMonth to ensure consistent grouping between sidebar
        // and HistoryPage. Previously 'earlier' used startOfMonth which could
        // include sessions that sidebar groups as '30days'.
        // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-013]
        case 'older': {
          const thirtyDaysAgo = new Date(startOfToday.getTime() - 30 * 86400000);
          return updatedAt < thirtyDaysAgo;
        }
        default:
          return true;
      }
    });
  }, [sessions, debouncedQuery, timeFilter]);

  // P2-3: Pagination
  const paginatedSessions = filteredSessions.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  );

  const handleSelectSession = async (id: string) => {
    setViewingSessionId(id);
    setViewLoading(true);
    try {
      const { results: rawMessages } = await chatApi.getMessages(id);
      const messages: Message[] = rawMessages.map((m) => ({
        id: m.id || crypto.randomUUID(),
        role: m.role,
        content: m.content || '',
        citations: m.citations || [],
        createdAt: m.created_at || m.createdAt || new Date().toISOString(),
      })).sort((a, b) => {
        const aTime = Date.parse(a.createdAt);
        const bTime = Date.parse(b.createdAt);
        return Number.isNaN(aTime) || Number.isNaN(bTime) ? 0 : aTime - bTime;
      });
      setViewMessages(messages);
    } catch {
      setViewMessages([]);
    } finally {
      setViewLoading(false);
    }
  };

  const handleBack = () => {
    setViewingSessionId(null);
    setViewMessages([]);
  };

  const handleContinueChat = () => {
    setActiveSession(viewingSessionId!);
    navigate('/chat');
  };

  // Time filter options
  const timeFilterOptions = [
    { label: t('filter_all'), value: 'all' },
    { label: t('filter_today'), value: 'today' },
    { label: t('filter_this_week'), value: 'this_week' },
    { label: t('filter_this_month'), value: 'this_month' },
    { label: t('filter_older') || t('filter_earlier'), value: 'older' },
  ];

  // Viewing a specific session — show messages inline (read-only)
  if (viewingSessionId) {
    return (
      <div className="page section-enter" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div className="page-head" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={handleBack}
            className="btn-press"
            aria-label={t('back_to_history') || '返回历史列表'}
          />
          <h1 className="page-title" style={{ margin: 0, fontSize: 22, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {sessions.find(s => s.id === viewingSessionId)?.title || t('new_conversation')}
          </h1>
        </div>
        <div className="page-inner" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '0 24px 24px' }}>
        {viewLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '24px 0' }}>
            <div className="skeleton-msg" style={{ alignSelf: 'flex-start', width: '70%', padding: '14px 18px', borderRadius: 20 }}>
              {[100, 85].map((w, i) => <div key={i} className="skeleton-line" style={{ width: `${w}%`, height: 14 }} />)}
            </div>
            <div className="skeleton-msg" style={{ alignSelf: 'flex-end', width: '60%', padding: '14px 18px', borderRadius: 20 }}>
              {[100, 100, 65].map((w, i) => <div key={i} className="skeleton-line" style={{ width: `${w}%`, height: 14 }} />)}
            </div>
          </div>
        ) : (
          <div style={{
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            overflowX: 'hidden',
            padding: '8px 4px 0 0',
          }}>
            {viewMessages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} canShare={canShare} />
            ))}
            {viewMessages.length === 0 && (
              <EmptyState className="kp-history-empty" icon="K" title={t('no_messages') || '暂无消息'} />
            )}
            {viewMessages.length > 0 && (
              <>
                <Divider style={{ margin: '16px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0' }}>
                  <Button
                    type="primary"
                    icon={<MessageOutlined />}
                    onClick={handleContinueChat}
                    style={{ borderRadius: 12, fontWeight: 500 }}
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

  if (loading) {
    return (
      <div className="page section-enter" style={{ flex: 1, minHeight: 0, padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="skeleton-msg" style={{ width: '100%', padding: '16px', borderRadius: 12 }}>
            <div className="skeleton-line" style={{ width: '40%', height: 16, marginBottom: 8 }} />
            <div className="skeleton-line" style={{ width: '80%', height: 12 }} />
          </div>
        ))}
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="page section-enter kp-history-empty-page">
        <Surface>
          <EmptyState
            icon="K"
            title={t('no_history')}
            action={(
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/chat')}>
                {t('new_conversation')}
              </Button>
            )}
          />
        </Surface>
      </div>
    );
  }

  return (
    <div className="page section-enter" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <PageHeader title={t('conversation_history')} />
      <Surface className="page-inner kp-history-surface" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      {/* Search and filter toolbar */}
      <div style={{
        display: 'flex',
        gap: 12,
        marginBottom: 16,
        flexWrap: 'wrap',
        alignItems: 'center',
        flexShrink: 0,
      }}>
        <Input.Search
          placeholder={t('search_history') || '搜索对话'}
          allowClear
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          prefix={<SearchOutlined />}
          className="input-focus-float"
          style={{ maxWidth: 320, flex: '1 1 200px' }}
          aria-label={t('search_history') || '搜索对话'}
        />
        <Segmented
          className="hover-lift"
          options={timeFilterOptions}
          value={timeFilter}
          onChange={(value) => setTimeFilter(value as TimeFilter)}
          aria-label={t('filter_all') || '时间筛选'}
        />
      </div>

      {filteredSessions.length === 0 ? (
        <EmptyState className="kp-history-empty" icon="K" title={t('no_search_results') || '没有找到匹配的对话'} />
      ) : (
        <div style={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
          paddingRight: 4,
        }}>
          {/* Unified date grouping uses the same helpers as the AppLayout sidebar. */}
          {(() => {
            const groupedSessions: Record<string, typeof paginatedSessions> = {};
            for (const s of paginatedSessions) {
              const gk = getDateGroupKey(s.updatedAt);
              if (!groupedSessions[gk]) groupedSessions[gk] = [];
              groupedSessions[gk].push(s);
            }
            const groupOrder = computeGroupOrder(groupedSessions);
            return groupOrder.map((groupKey) => {
              const groupSessions = groupedSessions[groupKey];
              if (!groupSessions || groupSessions.length === 0) return null;

              const groupLabel = getGroupLabel(groupKey, currentLang);

            return (
              <div key={groupKey} style={{ marginBottom: 16 }}>
                <div style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--color-text-secondary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  padding: '8px 16px 4px',
                }}>
                  {groupLabel}
                </div>
                <List
                  dataSource={groupSessions}
                  renderItem={(session) => (
                    <List.Item>
                      <Button
                        type="text"
                        onClick={() => handleSelectSession(session.id)}
                        className="hover-lift btn-press"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            handleSelectSession(session.id);
                          }
                        }}
                        style={{
                          cursor: 'pointer',
                          width: '100%',
                          textAlign: 'left',
                          padding: '12px 16px',
                          height: 'auto',
                        }}
                        aria-label={`${session.title || t('new_conversation')}, ${session.updatedAt ? formatDate(session.updatedAt) : t('filter_earlier')}`}
                      >
                        <List.Item.Meta
                          title={session.title || t('new_conversation')}
                          description={<Text type="secondary">{session.updatedAt ? formatDate(session.updatedAt) : t('filter_earlier')}</Text>}
                        />
                      </Button>
                    </List.Item>
                  )}
                />
              </div>
            );
          });
        })()}
          {filteredSessions.length > PAGE_SIZE && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16, paddingBottom: 4 }}>
              <Pagination
                current={currentPage}
                pageSize={PAGE_SIZE}
                total={filteredSessions.length}
                onChange={(page) => setCurrentPage(page)}
                showSizeChanger={false}
                size="small"
              />
            </div>
          )}
        </div>
      )}
      </Surface>
    </div>
  );
}
