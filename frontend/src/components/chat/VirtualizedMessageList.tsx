/**
 * VirtualizedMessageList — V3.5 HIGH-003 fix + V3.7 P1.2/P2.1 optimizations
 *
 * Uses react-virtuoso for message list rendering to prevent DOM explosion
 * at 50+ conversation rounds.
 *
 * FIX: Virtuoso is now THE ONLY scroll container in the chat area.
 * Previous layout had 3 nested scroll containers (main, scrollContainerRef, Virtuoso)
 * which prevented Virtuoso from calculating its viewport height, causing messages
 * to not render. Now the parent provides a bounded height (flex: 1 + minHeight: 0 +
 * overflow: hidden) and Virtuoso manages all scrolling internally.
 */

import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
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
  // V3.7 P2.1: citations prop kept for interface compatibility but we read
  // from Zustand store instead (storeCitations).
  citations: _citations,
  streamPhase,
  onRegenerate,
  virtuosoRef,
  onScrollToBottomChange,
}: VirtualizedMessageListProps) {
  const { t } = useTranslation('chat');

  // V3.7 P2.1: Use refs for streamContent and citations to keep itemContent
  // callback stable. This prevents Virtuoso from re-calling itemContent for
  // ALL visible items on every rAF frame during streaming.
  const streamContentRef = useRef(streamContent);
  streamContentRef.current = streamContent;
  const citationsRef = useRef(_citations);
  citationsRef.current = _citations;

  // Build the data array for Virtuoso:
  const data = useMemo(() => {
    const items: (Message | { id: 'load-older-marker'; role: 'system'; content: '' })[] = [];

    // V3.5: Add a marker item for "load older messages" at the top
    if (hasOlderMessages) {
      items.push({ id: 'load-older-marker', role: 'system', content: '' });
    }

    items.push(...messages);

    // V3.7 P2.1: Streaming placeholder — content is read from store in itemContent
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

  // Item renderer — handles both regular messages and the "load older" marker
  const itemContent = useCallback((_index: number, item: Message | { id: string; role: string; content: string }) => {
    if (item.id === 'load-older-marker') {
      return (
        <div style={{ textAlign: 'center', padding: '8px 24px' }}>
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
  }, [isStreaming, onRegenerate, onLoadOlder, t]);

  // Thinking indicator — rendered via Virtuoso's Footer component slot
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
      ref={virtuosoRef}
      data={data}
      itemContent={itemContent}
      followOutput={isStreaming ? 'smooth' : false}
      initialTopMostItemIndex={data.length - 1}
      computeItemKey={(_index, item) => item.id}
      increaseViewportBy={{ top: 200, bottom: 200 }}
      defaultItemHeight={80}
      // FIX: isScrolling callback detects when user scrolls away from bottom.
      // This replaces the manual IntersectionObserver approach.
      atBottomStateChange={(isAtBottom) => {
        onScrollToBottomChange?.(!isAtBottom);
      }}
      // FIX: Bottom padding to prevent last message being hidden behind the
      // floating input bar (fixed position, ~120px from viewport bottom including
      // disclaimer text). Virtuoso respects this padding in its scroll calculation.
      components={{
        Footer: () => (
          <>
            {thinkingIndicator}
            <div style={{ height: 120 }} />
          </>
        ),
      }}
      // FIX: Virtuoso must fill its parent's bounded height.
      // No explicit height or overflow — Virtuoso calculates its own viewport
      // from the parent's dimensions (parent has flex:1 + minHeight:0 + overflow:hidden).
      style={{ flex: 1, minHeight: 0 }}
    />
  );
}
