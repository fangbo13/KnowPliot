import { useTranslation } from 'react-i18next';
import { useState, useEffect, useRef, useMemo } from 'react';
import { Card, List, Typography, Empty, Button, Spin, Divider, Input, Segmented } from 'antd';
import { PlusOutlined, ArrowLeftOutlined, MessageOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useChatStore, type Message } from '../store/chatStore';
import { chatApi } from '../api/chat';
import MessageBubble from '../components/chat/MessageBubble';

const { Text } = Typography;

type TimeFilter = 'all' | 'today' | 'this_week' | 'this_month' | 'earlier';

export default function HistoryPage() {
  const { t } = useTranslation('common');
  const { sessions, loadSessions, setActiveSession } = useChatStore();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [viewingSessionId, setViewingSessionId] = useState<string | null>(null);
  const [viewMessages, setViewMessages] = useState<Message[]>([]);
  const [viewLoading, setViewLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('all');
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
      if (searchQuery) {
        const title = (session.title || '').toLowerCase();
        const query = searchQuery.toLowerCase();
        if (!title.includes(query)) return false;
      }

      // Time filter
      if (timeFilter === 'all') return true;

      const updatedAt = session.updatedAt ? new Date(session.updatedAt) : null;
      if (!updatedAt) return timeFilter === 'earlier';

      switch (timeFilter) {
        case 'today':
          return updatedAt >= startOfToday;
        case 'this_week':
          return updatedAt >= startOfWeek;
        case 'this_month':
          return updatedAt >= startOfMonth;
        case 'earlier':
          return updatedAt < startOfMonth;
        default:
          return true;
      }
    });
  }, [sessions, searchQuery, timeFilter]);

  const handleSelectSession = async (id: string) => {
    setViewingSessionId(id);
    setViewLoading(true);
    try {
      const rawMessages = await chatApi.getMessages(id);
      const messages: Message[] = rawMessages.map((m: any) => ({
        id: m.id || crypto.randomUUID(),
        role: m.role,
        content: m.content || '',
        citations: m.citations || [],
        createdAt: m.created_at || m.createdAt || new Date().toISOString(),
      }));
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
    { label: t('filter_earlier'), value: 'earlier' },
  ];

  // Viewing a specific session — show messages inline (read-only)
  if (viewingSessionId) {
    return (
      <Card
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={handleBack}
              aria-label={t('back_to_history') || '返回历史列表'}
            />
            <span style={{ fontFamily: "'Calistoga', Georgia, serif", fontWeight: 400 }}>
              {sessions.find(s => s.id === viewingSessionId)?.title || t('new_conversation')}
            </span>
          </div>
        }
      >
        {viewLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '48px 0' }}>
            <Spin size="large" tip={t('loading_messages') || '加载中...'} />
          </div>
        ) : (
          <div style={{ maxHeight: '60vh', overflowY: 'auto', padding: '8px 0' }}>
            {viewMessages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {viewMessages.length === 0 && (
              <Empty description={t('no_messages') || '暂无消息'} image={Empty.PRESENTED_IMAGE_SIMPLE} />
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
                    继续对话
                  </Button>
                </div>
              </>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </Card>
    );
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
        <Spin size="large" tip={t('loading') || '加载中...'} />
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <Empty
        description={t('no_history')}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      >
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate('/chat')}
        >
          {t('new_conversation')}
        </Button>
      </Empty>
    );
  }

  return (
    <Card
      title={
        <span style={{ fontFamily: "'Calistoga', Georgia, serif", fontWeight: 400 }}>
          {t('conversation_history')}
        </span>
      }
    >
      {/* Search and filter toolbar */}
      <div style={{
        display: 'flex',
        gap: 12,
        marginBottom: 16,
        flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        <Input.Search
          placeholder={t('search_history') || '搜索对话'}
          allowClear
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          prefix={<SearchOutlined />}
          style={{ maxWidth: 320, flex: '1 1 200px' }}
          aria-label={t('search_history') || '搜索对话'}
        />
        <Segmented
          options={timeFilterOptions}
          value={timeFilter}
          onChange={(value) => setTimeFilter(value as TimeFilter)}
          aria-label={t('filter_all') || '时间筛选'}
        />
      </div>

      {filteredSessions.length === 0 ? (
        <Empty
          description={t('no_search_results') || '没有找到匹配的对话'}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <List
          dataSource={filteredSessions}
          renderItem={(session) => (
            <List.Item>
              <Button
                type="text"
                onClick={() => handleSelectSession(session.id)}
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
                aria-label={`${session.title || t('new_conversation')}, ${session.updatedAt}`}
              >
                <List.Item.Meta
                  title={session.title || t('new_conversation')}
                  description={<Text type="secondary">{session.updatedAt}</Text>}
                />
              </Button>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}
