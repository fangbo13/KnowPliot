/**
 * VirtualizedMessageList — react-virtuoso (preserved V3.5/V3.7 architecture).
 *
 * Virtuoso remains THE ONLY scroll container in the chat area. Streaming content
 * and citations are read from refs to keep itemContent stable (no re-call of every
 * visible item per rAF frame). Visual layer restyled for the Claude system; the
 * streaming/virtualization logic is unchanged.
 */

import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { useCallback, useMemo, useRef } from 'react';
import { UpOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import MemoizedMessageBubble from './MessageBubble';
import type { Message, Citation } from '../../store/chatStore';

interface VirtualizedMessageListProps {
  messages: Message[];
  hasOlderMessages: boolean;
  onLoadOlder: () => void;
  isStreaming: boolean;
  streamContent: string;
  citations: Citation[];
  streamPhase: string;
  onRegenerate: () => void;
  virtuosoRef?: React.Ref<VirtuosoHandle>;
  onScrollToBottomChange?: (isAtBottom: boolean) => void;
}

export default function VirtualizedMessageList({
  messages,
  hasOlderMessages,
  onLoadOlder,
  isStreaming,
  streamContent,
  citations: _citations,
  streamPhase,
  onRegenerate,
  virtuosoRef,
  onScrollToBottomChange,
}: VirtualizedMessageListProps) {
  const { t } = useTranslation('chat');

  const streamContentRef = useRef(streamContent);
  streamContentRef.current = streamContent;
  const citationsRef = useRef(_citations);
  citationsRef.current = _citations;

  const data = useMemo(() => {
    const items: (Message | { id: 'load-older-marker'; role: 'system'; content: '' })[] = [];
    if (hasOlderMessages) {
      items.push({ id: 'load-older-marker', role: 'system', content: '' });
    }
    items.push(...messages);
    if (isStreaming && streamContent) {
      items.push({
        id: 'streaming',
        role: 'assistant',
        content: '',
        citations: [],
        createdAt: new Date().toISOString(),
      });
    }
    return items;
  }, [messages, hasOlderMessages, isStreaming, streamContent]);

  const itemContent = useCallback((_index: number, item: Message | { id: string; role: string; content: string }) => {
    if (item.id === 'load-older-marker') {
      return (
        <div className="msg-col" style={{ textAlign: 'center', padding: '10px 24px' }}>
          <button className="msg-action-btn" style={{ margin: '0 auto' }} onClick={onLoadOlder}>
            <UpOutlined />{t('load_older_messages') || 'Load earlier messages'}
          </button>
        </div>
      );
    }

    const msg = item as Message;
    const isStreamingBubble = msg.id === 'streaming';
    const streamingMessage = isStreamingBubble
      ? { ...msg, content: streamContentRef.current || '', citations: citationsRef.current || [] }
      : msg;

    return (
      <div className="msg-col">
        <MemoizedMessageBubble
          message={streamingMessage}
          isStreaming={isStreamingBubble}
          disableActions={isStreaming}
          onRegenerate={msg.role === 'assistant' && !isStreamingBubble ? onRegenerate : undefined}
        />
      </div>
    );
  }, [isStreaming, onRegenerate, onLoadOlder, t]);

  const thinkingIndicator = useMemo(() => {
    if (!isStreaming || streamContent) return null;
    return (
      <div className="msg-col">
        <div className="thinking">
          <div className="thinking-dots">
            {[0, 1, 2].map((i) => (
              <span key={i} className="thinking-dot" style={{ animationDelay: `${i * 0.16}s` }} />
            ))}
          </div>
          <span className="thinking-label">
            {streamPhase === 'connecting' ? t('thinking_connecting')
              : streamPhase === 'searching' ? t('thinking_searching')
              : t('thinking_generating')}
          </span>
        </div>
      </div>
    );
  }, [isStreaming, streamContent, streamPhase, t]);

  return (
    <Virtuoso
      ref={virtuosoRef}
      data={data}
      itemContent={itemContent}
      followOutput={isStreaming ? 'smooth' : false}
      initialTopMostItemIndex={data.length - 1}
      computeItemKey={(_index, item) => item.id}
      increaseViewportBy={{ top: 200, bottom: 200 }}
      defaultItemHeight={90}
      atBottomStateChange={(isAtBottom) => onScrollToBottomChange?.(!isAtBottom)}
      components={{
        Footer: () => (
          <>
            {thinkingIndicator}
            <div style={{ height: 150 }} />
          </>
        ),
      }}
      style={{ flex: 1, minHeight: 0 }}
    />
  );
}
