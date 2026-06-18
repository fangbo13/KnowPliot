import { useEffect } from 'react';
import { Card, List, Typography, Empty } from 'antd';
import { useChatStore } from '../store/chatStore';

const { Text } = Typography;

export default function HistoryPage() {
  const { sessions, loadSessions, setActiveSession } = useChatStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleSelectSession = (id: string) => {
    setActiveSession(id);
    window.location.href = `/chat`;
  };

  if (sessions.length === 0) {
    return <Empty description="No conversation history yet" />;
  }

  return (
    <Card title="Conversation History">
      <List
        dataSource={sessions}
        renderItem={(session) => (
          <List.Item
            style={{ cursor: 'pointer' }}
            onClick={() => handleSelectSession(session.id)}
          >
            <List.Item.Meta
              title={session.title || 'New Conversation'}
              description={<Text type="secondary">{session.updatedAt}</Text>}
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
