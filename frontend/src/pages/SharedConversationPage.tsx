import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button } from 'antd';
import { useParams } from 'react-router-dom';

import { chatApi, type SharedConversation } from '../api/chat';
import MessageBubble from '../components/chat/MessageBubble';
import { EmptyState, PageHeader, Surface } from '../design/primitives';
import type { Message } from '../store/chatStore';

export default function SharedConversationPage() {
  const { t } = useTranslation('common');
  const { token = '' } = useParams<{ token: string }>();
  const [conversation, setConversation] = useState<SharedConversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    chatApi.getSharedConversation(token).then((value) => {
      if (active) setConversation(value);
    }).catch(() => {
      if (active) setError(true);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [retryKey, token]);

  const messages: Message[] = (conversation?.messages ?? []).map((message) => ({
    id: message.id ?? crypto.randomUUID(),
    role: message.role,
    content: message.content ?? '',
    citations: message.citations ?? [],
    createdAt: message.created_at ?? message.createdAt ?? '',
  }));

  return (
    <div className="page section-enter">
      <PageHeader
        title={conversation?.title || t('shared_conversation')}
        description={t('shared_conversation_read_only')}
      />
      <Surface>
        {loading ? (
          <div aria-label={t('loading')} className="skeleton-msg" style={{ padding: 20 }}>
            <div className="skeleton-line" style={{ width: '70%', height: 14 }} />
          </div>
        ) : error ? (
          <Alert
            showIcon
            type="error"
            message={t('shared_conversation_unavailable')}
            action={<Button onClick={() => setRetryKey((value) => value + 1)}>{t('error_retry')}</Button>}
          />
        ) : messages.length === 0 ? (
          <EmptyState icon="K" title={t('no_messages')} />
        ) : messages.map((message) => (
          <MessageBubble key={message.id} message={message} disableActions canShare={false} />
        ))}
      </Surface>
    </div>
  );
}
