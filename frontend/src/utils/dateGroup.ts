/**
 * Shared date grouping utilities used by AppLayout sidebar and HistoryPage.
 */

export type DateGroupKey = 'today' | 'yesterday' | '7days' | '30days' | 'earlier';

/**
 * Assign a date string to a date group key.
 * Groups: today / yesterday / last 7 days / last 30 days / earlier
 */
export function getDateGroupKey(dateStr: string | undefined): DateGroupKey {
  if (!dateStr) return 'earlier';

  const d = new Date(dateStr);
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 86400000);
  const sevenDaysAgo = new Date(todayStart.getTime() - 7 * 86400000);
  const thirtyDaysAgo = new Date(todayStart.getTime() - 30 * 86400000);

  if (d >= todayStart) return 'today';
  if (d >= yesterdayStart) return 'yesterday';
  if (d >= sevenDaysAgo) return '7days';
  if (d >= thirtyDaysAgo) return '30days';
  return 'earlier';
}

/** Display order for date groups */
export const DATE_GROUP_ORDER: DateGroupKey[] = ['today', 'yesterday', '7days', '30days', 'earlier'];

/** Format a date for display (relative time) */
export function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);

  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  if (hours < 24) return `${hours} 小时前`;

  return d.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
