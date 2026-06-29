/**
 * V4.0 DEFECT-008: Cross-tab synchronization via BroadcastChannel.
 * V4.1 BUG-010: Added Toast feedback for cross-tab events.
 * V4.2 SYS-V4.2-017: Changed from 4-layer nested dynamic imports to
 *   static imports — eliminates ~200ms abort delay caused by module
 *   resolution + eval of each nested import() chain.
 *
 * Previous: Each event handler used 4 chained dynamic imports:
 *   import(StreamLifecycleManager).then(() =>
 *     import(TokenBatchRenderer).then(() =>
 *       import(chatStore).then(() =>
 *         import(antd).then(() => ...))))
 *   Each import ~50ms → total delay ~200ms → 10-20 wasted tokens.
 *
 * Now: All modules are imported at module initialization time.
 * The only remaining dynamic import is antd message (for Toast),
 * which is ~5ms (antd is likely already loaded by the app).
 *
 * [Source: V4.0/deep_sys_defect_list.md §DEFECT-008]
 * [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-010]
 * [Source: V4.2/deep_sys/deep_sys_defect_list_V4.2.md §SYS-V4.2-017]
 */

// V4.2 SYS-V4.2-017: Static imports — eliminates 4-layer dynamic import delay
import { abortActiveStream, getActiveStreamSessionId } from '../stream/StreamLifecycleManager';
import { resetTokenBatcher } from '../stream/TokenBatchRenderer';
import { useChatStore } from '../store/chatStore';

const channel = new BroadcastChannel('ey-onboarding-sync');

/** Broadcast: notify other tabs that the active session switched */
export function broadcastSessionSwitch(sessionId: string | null) {
  channel.postMessage({ type: 'session-switch', sessionId, timestamp: Date.now() });
}

/** Broadcast: notify other tabs that a session was deleted */
export function broadcastSessionDelete(sessionId: string) {
  channel.postMessage({ type: 'session-delete', sessionId, timestamp: Date.now() });
}

/** Initialize the cross-tab listener. Call once at app startup. */
export function initCrossTabSync() {
  channel.onmessage = (event: MessageEvent) => {
    const { type, sessionId } = event.data;

    // V4.2 SYS-V4.2-017: Only antd message remains as dynamic import (~5ms)
    // All other modules are now statically imported at module init time
    switch (type) {
      case 'session-switch':
        import('antd').then(({ message: antMessage }) => {
          const ourStreamId = getActiveStreamSessionId();
          if (ourStreamId && ourStreamId !== sessionId) {
            // Another tab switched sessions — abort our stream if different
            abortActiveStream();
            resetTokenBatcher();
            const store = useChatStore.getState();
            store.setStreamPhase('idle');
            store.unlockSend();
            useChatStore.setState({ streamContent: '', sendError: null });
            // V4.1 BUG-010: Toast feedback
            antMessage.info('另一个标签页正在查看不同会话，当前流已暂停');
          }
        });
        break;

      case 'session-delete':
        import('antd').then(({ message: antMessage }) => {
          const ourStreamId = getActiveStreamSessionId();
          if (ourStreamId === sessionId) {
            // Another tab deleted our active session — abort + reset
            abortActiveStream();
            resetTokenBatcher();
            useChatStore.getState().resetSession();
            // V4.1 BUG-010: Toast feedback
            antMessage.info('另一个标签页删除了当前会话');
          }
          // Refresh session list to reflect deletion
          useChatStore.getState().loadSessions();
        });
        break;
    }
  };
}
