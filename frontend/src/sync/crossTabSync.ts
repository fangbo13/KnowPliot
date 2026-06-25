/**
 * V4.0 DEFECT-008: Cross-tab synchronization via BroadcastChannel.
 * V4.1 BUG-010: Added Toast feedback for cross-tab events so users see
 * a notification when another tab deletes/switches their active session.
 *
 * Each browser tab has its own Zustand store and StreamLifecycleManager module-level
 * variables. Without cross-tab sync, Tab B deleting a session that Tab A is actively
 * streaming causes inconsistency (Tab A continues streaming to a deleted session).
 *
 * This module:
 * 1. Broadcasts session-switch and session-delete events to other tabs
 * 2. Receives events from other tabs and aborts streams / resets state accordingly
 * 3. V4.1 BUG-010: Shows antd message.info Toast on cross-tab mutations
 *
 * [Source: V4.0/deep_sys_defect_list.md §DEFECT-008]
 * [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-010]
 */

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

    // Use dynamic imports to avoid circular dependency:
    // chatStore imports StreamLifecycleManager, and crossTabSync would import chatStore
    switch (type) {
      case 'session-switch':
        import('../stream/StreamLifecycleManager').then(({ abortActiveStream, getActiveStreamSessionId }) => {
          import('../stream/TokenBatchRenderer').then(({ resetTokenBatcher }) => {
            import('../store/chatStore').then(({ useChatStore }) => {
              // V4.1 BUG-010: Dynamic import antd message for Toast feedback
              import('antd').then(({ message: antMessage }) => {
                const ourStreamId = getActiveStreamSessionId();
                if (ourStreamId && ourStreamId !== sessionId) {
                  // Another tab switched sessions — if our tab is streaming a different session, abort
                  abortActiveStream();
                  resetTokenBatcher();
                  const store = useChatStore.getState();
                  store.setStreamPhase('idle');
                  store.unlockSend();
                  // Clear residual stream content using individual setters (Zustand set() not on ChatState type)
                  useChatStore.setState({ streamContent: '', sendError: null });
                  // V4.1 BUG-010: Toast feedback — user sees why their stream stopped
                  antMessage.info('另一个标签页正在查看不同会话，当前流已暂停');
                  // Conservative: only abort stream, don't force session change in our tab
                }
              });
            });
          });
        });
        break;

      case 'session-delete':
        import('../stream/StreamLifecycleManager').then(({ abortActiveStream, getActiveStreamSessionId }) => {
          import('../stream/TokenBatchRenderer').then(({ resetTokenBatcher }) => {
            import('../store/chatStore').then(({ useChatStore }) => {
              // V4.1 BUG-010: Dynamic import antd message for Toast feedback
              import('antd').then(({ message: antMessage }) => {
                const ourStreamId = getActiveStreamSessionId();
                if (ourStreamId === sessionId) {
                  // Another tab deleted our active session — abort stream + reset
                  abortActiveStream();
                  resetTokenBatcher();
                  useChatStore.getState().resetSession();
                  // V4.1 BUG-010: Toast feedback — user sees why their session disappeared
                  antMessage.info('另一个标签页删除了当前会话');
                }
                // Refresh session list to reflect deletion
                useChatStore.getState().loadSessions();
              });
            });
          });
        });
        break;
    }
  };
}
