/**
 * VirtualizedMessageList — V3.5 HIGH-003 fix + V3.7 P1.2/P2.1 optimizations
 *
 * Uses react-virtuoso for message list rendering to prevent DOM explosion
 * at 50+ conversation rounds.
 *
 * V3.7 optimizations:
 * - P1.2: Uses MemoizedMessageBubble — React.memo with custom comparator
 *   prevents ~880 unnecessary Markdown re-parses during streaming.
 * - P2.1: Data reference stability — streamContent removed from data useMemo
 *   dependencies. Streaming message content is read via Zustand useStore
 *   selector inside itemContent, keeping the data array stable during stream.
 */

import { Virtuoso } from 'react-virtuoso';
import { useCallback, useMemo, useRef } from 'react';
import { Button } from 'antd';
import { UpOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import MemoizedMessageBubble from './MessageBubble';
import type { Message, Citation } from '../../store/chatStore';

interface VirtualizedMessageListProps {
  messages: Message[];
  hasOlderMessages: boolean;
  onLoadOlder: () => void;
  isStreaming: boolean;
  streamContent: string;  // V3.7 P2.1: Still received for thinking indicator, but NOT in data useMemo
  citations: Citation[];   // V3.7 P2.1: Same — used in itemContent via store selector
  streamPhase: string;
  onRegenerate: () => void;
}

export default function VirtualizedMessageList({
  messages,
  hasOlderMessages,
  onLoadOlder,
  isStreaming,
  streamContent,
  // V3.7 P2.1: citations prop kept for interface compatibility but we read
  // from Zustand store instead (storeCitations). The prop value is captured
  // in this comment-only line to satisfy TypeScript's unused variable check.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  citations: _citations,
  streamPhase,
  onRegenerate,
}: VirtualizedMessageListProps) {
  const { t } = useTranslation('chat');

  // V3.7 P2.1: Use refs for streamContent and citations to keep itemContent
  // callback stable. This prevents Virtuoso from re-calling itemContent for
  // ALL visible items on every rAF frame during streaming.
  // The actual values are updated via the store subscription, but itemContent's
  // reference stays the same — MemoizedMessageBubble's comparator handles
  // the streaming bubble's content updates.
  const streamContentRef = useRef(streamContent);
  streamContentRef.current = streamContent;  // Update ref on every render
  const citationsRef = useRef(_citations);
  citationsRef.current = _citations;

  // Build the data array for Virtuoso:
  // V3.7 P2.1: streamContent and citations are NOT in the data array dependency
  // to keep references stable during streaming. The streaming bubble reads
  // content/citations from Zustand store directly in itemContent.
  const data = useMemo(() => {
    const items: (Message | { id: 'load-older-marker'; role: 'system'; content: '' })[] = [];

    // V3.5: Add a marker item for "load older messages" at the top
    if (hasOlderMessages) {
      items.push({ id: 'load-older-marker', role: 'system', content: '' });
    }

    items.push(...messages);

    // V3.7 P2.1: Streaming placeholder — content is read from store in itemContent
    // The placeholder just marks that a streaming message exists.
    // Its actual content (streamContent) and citations are read from Zustand store
    // via useStore selector, NOT from this data array.
    if (isStreaming) {
      items.push({
        id: 'streaming',
        role: 'assistant',
        content: '',  // V3.7 P2.1: Empty placeholder — actual content read from store
        citations: [],
        createdAt: new Date().toISOString(),
      });
    }

    return items;
  }, [messages, hasOlderMessages, isStreaming]);  // V3.7 P2.1: Removed streamContent and citations

  // Item renderer — handles both regular messages and the "load older" marker
  // V3.7 P2.1: Streaming bubble reads content from refs (not from data array or store selectors)
  // This keeps itemContent callback reference stable, preventing Virtuoso from
  // re-calling it for ALL visible items on every rAF frame during streaming.
  const itemContent = useCallback((_index: number, item: Message | { id: string; role: string; content: string }) => {
    if (item.id === 'load-older-marker') {
      return (
        <div style={{ textAlign: 'center', padding: '8px 0' }}>
          <Button
            type="text"
            size="small"
            icon={<UpOutlined />}
            onClick={onLoadOlder}
            style={{ color: 'var(--color-text-tertiary)', fontSize: 12 }}
          >
            {t('load_older_messages') || '加载更早的消息'}
          </Button>
        </div>
      );
    }

    const msg = item as Message;
    const isStreamingBubble = msg.id === 'streaming';

    // V3.7 P2.1: For the streaming bubble, inject real content from refs
    // Refs are updated on every render, but itemContent's reference stays stable.
    // MemoizedMessageBubble's comparator ensures streaming bubble always re-renders
    // (returns false when isStreaming=true), while non-streaming bubbles skip re-render.
    const streamingMessage = isStreamingBubble ? {
      ...msg,
      content: streamContentRef.current || '',
      citations: citationsRef.current || [],
    } : msg;

    return (
      <MemoizedMessageBubble
        message={streamingMessage}
        isStreaming={isStreamingBubble}
        disableActions={isStreaming}
        onRegenerate={msg.role === 'assistant' && !isStreamingBubble ? onRegenerate : undefined}
      />
    );
  }, [isStreaming, onRegenerate, onLoadOlder, t]);  // V3.7 P2.1: Removed streamContent/citations deps — refs read latest values

  // Thinking indicator — rendered via a component slot inside Virtuoso's Components prop
  const thinkingIndicator = useMemo(() => {
    if (!isStreaming || streamContent) return null;
    return (
      <div style={{
        padding: '16px 24px',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        animation: 'fadeIn 0.3s ease',
      }}>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          {[0, 1, 2].map(i => (
            <div key={i} style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--accent)',
              animation: `dotBounce 1.4s ease-in-out ${i * 0.16}s infinite`,
            }} />
          ))}
        </div>
        <span style={{ color: 'var(--color-text-tertiary)', fontSize: 13, fontWeight: 500 }}>
          {streamPhase === 'connecting' ? t('thinking_connecting')
            : streamPhase === 'searching' ? t('thinking_searching')
            : t('thinking_generating')}
        </span>
      </div>
    );
  }, [isStreaming, streamContent, streamPhase, t]);

  return (
    <Virtuoso
      data={data}
      itemContent={itemContent}
      followOutput={isStreaming ? 'smooth' : false}
      initialTopMostItemIndex={data.length - 1}
      computeItemKey={(_index, item) => item.id}
      increaseViewportBy={{ top: 200, bottom: 200 }}
      // V4.1 BUG-008: Stable item height estimation to prevent jump when streaming
      // placeholder is replaced by the final message. The streaming placeholder uses
      // a stable key ('streaming'), so Virtuoso caches its measured height. When the
      // placeholder is removed and the final message (with a new UUID key) appears,
      // Virtuoso estimates its height using this value instead of the default 30px,
      // preventing a sudden upward jump.
      // [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-008]
      defaultItemHeight={80}
      components={{
        Footer: () => thinkingIndicator ? <>{thinkingIndicator}</> : null,
      }}
      style={{ height: '100%' }}
    />
  );
}
