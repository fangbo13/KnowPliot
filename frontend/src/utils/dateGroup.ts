/**
 * Shared date grouping utilities used by AppLayout sidebar and HistoryPage.
 * V3.5: Extended with month-level grouping for "earlier" category.
 */

export type DateGroupKey = 'today' | 'yesterday' | '7days' | '30days' | string;
// string format for month keys: '2026-05', '2026-04', etc.

/**
 * Assign a date string to a date group key.
 * Groups: today / yesterday / last 7 days / last 30 days / month-level keys (e.g. '2026-05')
 */
export function getDateGroupKey(dateStr: string | undefined): DateGroupKey {
  if (!dateStr) return '30days'; // Default fallback for undefined dates

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

  // V3.5: Month-level grouping for sessions older than 30 days
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/**
 * Get the display label for a date group key, supporting i18n.
 * V3.5: Month keys like '2026-05' render as "2026年5月" (zh) or "May 2026" (en).
 */
export function getGroupLabel(key: string, lang: 'zh' | 'en'): string {
  switch (key) {
    case 'today': return lang === 'zh' ? '今天' : 'Today';
    case 'yesterday': return lang === 'zh' ? '昨天' : 'Yesterday';
    case '7days': return lang === 'zh' ? '过去7天' : 'Last 7 Days';
    case '30days': return lang === 'zh' ? '过去30天' : 'Last 30 Days';
    default:
      // Month key format: '2026-05'
      if (/^\d{4}-\d{2}$/.test(key)) {
        const [year, month] = key.split('-');
        return lang === 'zh'
          ? `${year}年${parseInt(month)}月`
          : new Date(+year, +month - 1).toLocaleDateString('en', { month: 'long', year: 'numeric' });
      }
      return key;
  }
}

/**
 * Compute the display order for date groups.
 * V3.5: Recent groups first (today/yesterday/7days/30days), then month groups
 * in reverse chronological order (most recent month first).
 */
export function computeGroupOrder(groups: Record<string, any[]>): string[] {
  const recentKeys = ['today', 'yesterday', '7days', '30days'];
  const recentPresent = recentKeys.filter(k => k in groups && groups[k].length > 0);

  // Month keys in reverse chronological order (most recent first)
  const monthKeys = Object.keys(groups)
    .filter(k => /^\d{4}-\d{2}$/.test(k) && groups[k].length > 0)
    .sort((a, b) => b.localeCompare(a));

  return [...recentPresent, ...monthKeys];
}

/** @deprecated V4.1 BUG-013: Legacy static order — no longer used by sidebar (sidebar
 * uses computeGroupOrder). Kept for backward compatibility with HistoryPage which now
 * uses computeGroupOrder too. The 'earlier' key is deprecated in favor of 30-day threshold.
 * [Source: V4.1/ui_ux/ui_bug_list_V4.1.md §BUG-013] */
export const DATE_GROUP_ORDER: DateGroupKey[] = ['today', 'yesterday', '7days', '30days'];

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
