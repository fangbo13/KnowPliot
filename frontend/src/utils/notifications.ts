type NotificationKind = 'success' | 'error' | 'warning' | 'info';

/**
 * Ant Design's notification runtime is interaction-owned. Keeping this import
 * literal and deferred prevents toast infrastructure from joining `/chat`'s
 * authenticated welcome bundle while preserving the existing notification UI.
 */
export async function notify(kind: NotificationKind, content: string): Promise<void> {
  const { default: message } = await import('antd/es/message');
  message[kind](content);
}
