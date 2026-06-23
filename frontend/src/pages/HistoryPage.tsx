import { useTranslation } from 'react-i18next';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, List, Typography, Empty } from 'antd';
import { useChatStore } from '../store/chatStore';

const { Text } = Typography;

export default function HistoryPage() {
  const { t } = useTranslation('common');
  const { sessions, loadSessions, setActiveSession } = useChatStore();
  const navigate = useNavigate();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleSelectSession = (id: string) => {
    setActiveSession(id);
    navigate('/chat');
  };

  if (sessions.length === 0) {
    return <Empty description={t('no_history')} />;
  }

  return (
    <Card
      title={
        <span style={{ fontFamily: "'Calistoga', Georgia, serif", fontWeight: 400 }}>
          {t('conversation_history')}
        </span>
      }
    >
      <List
        dataSource={sessions}
        renderItem={(session) => (
          <List.Item
            style={{ cursor: 'pointer' }}
            onClick={() => handleSelectSession(session.id)}
          >
            <List.Item.Meta
              title={session.title || t('new_conversation')}
              description={<Text type="secondary">{session.updatedAt}</Text>}
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
