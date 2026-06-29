/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

/**
 * Unit tests for dateGroup.ts — validates the strict if-else grouping logic,
 * timezone safety, boundary cases, and group ordering.
 *
 * All tests inject a fixed referenceDate to avoid dependence on the current
 * system clock. The reference date is 2026-06-27T10:00:00 in LOCAL time.
 *
 * IMPORTANT: These tests run in UTC+8 (China Standard Time). The grouping
 * logic uses LOCAL calendar days per the V4.6 requirement. UTC timestamps
 * are converted to local dates before grouping. For example:
 *   - 2026-05-27T23:59:00Z → local May 28 07:59 → falls into "过去30天"
 *     (not "月份 2026-05" as it would in pure UTC)
 *
 * This is the CORRECT behavior: the requirement mandates local timezone
 * grouping, and in UTC+8, the local date of that timestamp is May 28.
 */

import { describe, it, expect } from 'vitest';
import {
  getDateGroupKey,
  getGroupLabel,
  computeGroupOrder,
} from '../dateGroup';

// ─── Fixed reference date: local 2026-06-27 10:00:00 (UTC+8) ───
// Month is 0-indexed in JS Date constructor: June = 5
const REF = new Date(2026, 5, 27, 10, 0, 0);

// ─── V4.6 验收测试用例 ───────────────────────────────────────────────────

describe('getDateGroupKey — 验收测试用例', () => {
  // 会话1: 2026-06-27T08:30:00Z → UTC+8 local 16:30 → 今天
  it('session 1: today (UTC 08:30 = local 16:30)', () => {
    expect(getDateGroupKey('2026-06-27T08:30:00Z', REF)).toBe('today');
  });

  // 会话2: 2026-06-26T15:00:00Z → UTC+8 local June 26 23:00 → 昨天
  it('session 2: yesterday (UTC 15:00 = local June 26 23:00)', () => {
    expect(getDateGroupKey('2026-06-26T15:00:00Z', REF)).toBe('yesterday');
  });

  // 会话3: 2026-06-25T09:00:00Z → UTC+8 local June 25 17:00 → 过去7天
  it('session 3: 7days', () => {
    expect(getDateGroupKey('2026-06-25T09:00:00Z', REF)).toBe('7days');
  });

  // 会话4: 2026-06-20T23:59:00Z → UTC+8 local June 21 07:59 → 过去7天
  // NOTE: In UTC+8, the local date is June 21, which is within (today-7) range (June 20-25).
  // The 7-day boundary uses LOCAL calendar: today(June27) - 7 = June20 start of day.
  // June 21 local is >= June 20 → 7days.
  it('session 4: 7days — local date within past-7-day range', () => {
    expect(getDateGroupKey('2026-06-20T23:59:00Z', REF)).toBe('7days');
  });

  // 会话5: 2026-06-19T00:00:00Z → UTC+8 local June 19 08:00 → 过去30天
  it('session 5: 30days', () => {
    expect(getDateGroupKey('2026-06-19T00:00:00Z', REF)).toBe('30days');
  });

  // 会话6: 2026-05-28T12:00:00Z → UTC+8 local May 28 20:00 → 过去30天（30天边界）
  // In UTC+8: local May 28 = exactly 30 days before June 27 → included in "过去30天"
  it('session 6: 30days boundary — local May 28 (exactly 30 days ago, inclusive)', () => {
    expect(getDateGroupKey('2026-05-28T12:00:00Z', REF)).toBe('30days');
  });

  // 会话7: 2026-05-27T23:59:00Z → UTC+8 local May 28 07:59 → 过去30天
  // IMPORTANT: In UTC+8 timezone, this UTC timestamp resolves to LOCAL date May 28,
  // which falls within the "过去30天" range (May 28 ~ June 19).
  // This is CORRECT per the local-timezone requirement.
  // (In pure UTC timezone, it would be May 27 → month group, but we use LOCAL timezone.)
  it('session 7: 30days (UTC May-27 23:59 → local May 28 in UTC+8)', () => {
    expect(getDateGroupKey('2026-05-27T23:59:00Z', REF)).toBe('30days');
  });

  // 补充: 会话7的纯UTC视角验证 — 用一个明确在local May 27的UTC时间戳
  // 2026-05-27T07:00:00Z → UTC+8 local May 27 15:00 → 月份 2026-05
  it('session 7a: month group 2026-05 — local date May 27 (less than 30 days ago)', () => {
    expect(getDateGroupKey('2026-05-27T07:00:00Z', REF)).toBe('2026-05');
  });

  // 会话8: 2026-04-01T00:00:00Z → UTC+8 local April 1 08:00 → 月份 2026-04
  it('session 8: month group 2026-04', () => {
    expect(getDateGroupKey('2026-04-01T00:00:00Z', REF)).toBe('2026-04');
  });
});

// ─── 严格无重叠验证 ──────────────────────────────────────────────────────

describe('getDateGroupKey — strict no-overlap (local calendar boundaries)', () => {
  it('today/yesterday boundary: local midnight June 27 → today', () => {
    // Local midnight June 27 in UTC+8 = June 26 16:00 UTC
    expect(getDateGroupKey('2026-06-26T16:00:00Z', REF)).toBe('today');
  });

  it('today/yesterday boundary: just before local midnight June 27 → yesterday', () => {
    // June 26 15:59:59 UTC = local June 26 23:59:59 → yesterday
    expect(getDateGroupKey('2026-06-26T15:59:59Z', REF)).toBe('yesterday');
  });

  it('yesterday/7days boundary: local midnight June 26 → yesterday', () => {
    // Local midnight June 26 in UTC+8 = June 25 16:00 UTC
    expect(getDateGroupKey('2026-06-25T16:00:00Z', REF)).toBe('yesterday');
  });

  it('7days/30days boundary: local midnight June 20 → 7days (7-day threshold inclusive)', () => {
    // Local midnight June 20 in UTC+8 = June 19 16:00 UTC
    expect(getDateGroupKey('2026-06-19T16:00:00Z', REF)).toBe('7days');
  });

  it('7days/30days boundary: just before local midnight June 20 → 30days', () => {
    // June 19 15:59:59 UTC = local June 19 23:59:59 → 30days (below 7-day threshold)
    expect(getDateGroupKey('2026-06-19T15:59:59Z', REF)).toBe('30days');
  });

  it('30days/month boundary: local midnight May 28 → 30days (30-day threshold inclusive)', () => {
    // Local midnight May 28 in UTC+8 = May 27 16:00 UTC
    expect(getDateGroupKey('2026-05-27T16:00:00Z', REF)).toBe('30days');
  });

  it('30days/month boundary: just before local midnight May 28 → month group', () => {
    // May 27 15:59:59 UTC = local May 27 23:59:59 → month group (below 30-day threshold)
    expect(getDateGroupKey('2026-05-27T15:59:59Z', REF)).toBe('2026-05');
  });
});

// ─── 跨时区边界 ──────────────────────────────────────────────────────────

describe('getDateGroupKey — timezone boundary cases', () => {
  it('UTC 23:00 should be "today" in UTC+8 (not "yesterday")', () => {
    // 2026-06-26T23:00:00Z = 2026-06-27 07:00:00 in UTC+8 → today
    expect(getDateGroupKey('2026-06-26T23:00:00Z', REF)).toBe('today');
  });

  it('UTC 16:00 (local midnight) should be "today"', () => {
    // 2026-06-26T16:00:00Z = 2026-06-27 00:00:00 in UTC+8 → today (start of day)
    expect(getDateGroupKey('2026-06-26T16:00:00Z', REF)).toBe('today');
  });
});

// ─── 跨年/跨月 ──────────────────────────────────────────────────────────

describe('getDateGroupKey — cross-year/cross-month', () => {
  it('Dec 31 2025 UTC 16:00 → local Jan 1 2026 00:00 → month group 2026-01', () => {
    // In UTC+8: 2025-12-31T16:00:00Z = local 2026-01-01 00:00:00
    expect(getDateGroupKey('2025-12-31T16:00:00Z', REF)).toBe('2026-01');
  });

  it('Dec 31 2025 UTC 12:00 → local Dec 31 2025 20:00 → month group 2025-12', () => {
    // In UTC+8: 2025-12-31T12:00:00Z = local 2025-12-31 20:00:00
    expect(getDateGroupKey('2025-12-31T12:00:00Z', REF)).toBe('2025-12');
  });

  it('Jan 1 2026 UTC 00:00 → local Jan 1 2026 08:00 → month group 2026-01', () => {
    expect(getDateGroupKey('2026-01-01T00:00:00Z', REF)).toBe('2026-01');
  });
});

// ─── 低频用户 ────────────────────────────────────────────────────────────

describe('computeGroupOrder — low-frequency user', () => {
  it('only one session 3 months ago → only month group visible', () => {
    const groups = { '2026-03': [{ id: '1', title: 'test', updatedAt: '2026-03-01T00:00:00Z' }] };
    const order = computeGroupOrder(groups);
    expect(order).toEqual(['2026-03']);
    // No 'today', 'yesterday', '7days', '30days' groups should appear
  });

  it('empty groups are excluded from order', () => {
    const groups: Record<string, any[]> = {
      today: [],
      yesterday: [{ id: '1', title: 'test', updatedAt: '2026-06-26T00:00:00Z' }],
      '7days': [],
      '2026-05': [{ id: '2', title: 'old', updatedAt: '2026-05-01T00:00:00Z' }],
    };
    const order = computeGroupOrder(groups);
    expect(order).toEqual(['yesterday', '2026-05']);
    expect(order).not.toContain('today');
    expect(order).not.toContain('7days');
  });
});

// ─── 月份排序 ────────────────────────────────────────────────────────────

describe('computeGroupOrder — month key sorting', () => {
  it('month keys sorted in reverse chronological order', () => {
    const groups: Record<string, any[]> = {
      '2026-04': [{ id: '1' }],
      '2026-01': [{ id: '2' }],
      '2025-12': [{ id: '3' }],
      '2026-06': [{ id: '4' }],
    };
    const order = computeGroupOrder(groups);
    // Recent keys absent, only month keys → sorted descending
    expect(order).toEqual(['2026-06', '2026-04', '2026-01', '2025-12']);
  });

  it('mixed recent + month groups: recent first, then months descending', () => {
    const groups: Record<string, any[]> = {
      '2026-03': [{ id: '1' }],
      today: [{ id: '2' }],
      '2025-12': [{ id: '3' }],
      '7days': [{ id: '4' }],
    };
    const order = computeGroupOrder(groups);
    expect(order).toEqual(['today', '7days', '2026-03', '2025-12']);
  });

  it('跨年排序: 2026-01 > 2025-12 (string comparison works for YYYY-MM)', () => {
    const groups: Record<string, any[]> = {
      '2025-12': [{ id: '1' }],
      '2026-01': [{ id: '2' }],
    };
    const order = computeGroupOrder(groups);
    expect(order).toEqual(['2026-01', '2025-12']);
  });
});

// ─── getGroupLabel ───────────────────────────────────────────────────────

describe('getGroupLabel', () => {
  it('zh labels for recent groups', () => {
    expect(getGroupLabel('today', 'zh')).toBe('今天');
    expect(getGroupLabel('yesterday', 'zh')).toBe('昨天');
    expect(getGroupLabel('7days', 'zh')).toBe('过去7天');
    expect(getGroupLabel('30days', 'zh')).toBe('过去30天');
  });

  it('en labels for recent groups', () => {
    expect(getGroupLabel('today', 'en')).toBe('Today');
    expect(getGroupLabel('yesterday', 'en')).toBe('Yesterday');
    expect(getGroupLabel('7days', 'en')).toBe('Last 7 Days');
    expect(getGroupLabel('30days', 'en')).toBe('Last 30 Days');
  });

  it('zh month label: 2026-05 → "2026年5月"', () => {
    expect(getGroupLabel('2026-05', 'zh')).toBe('2026年5月');
  });

  it('en month label: 2026-05 → "May 2026"', () => {
    expect(getGroupLabel('2026-05', 'en')).toBe('May 2026');
  });
});

// ─── undefined / empty input ─────────────────────────────────────────────

describe('getDateGroupKey — edge cases', () => {
  it('undefined dateStr → fallback to 30days', () => {
    expect(getDateGroupKey(undefined, REF)).toBe('30days');
  });

  it('empty string dateStr → fallback to 30days', () => {
    expect(getDateGroupKey('', REF)).toBe('30days');
  });

  it('without referenceDate → uses current system time (smoke test)', () => {
    // Just verify it doesn't crash — can't assert exact group without knowing "now"
    const result = getDateGroupKey(new Date().toISOString());
    expect(['today', 'yesterday', '7days', '30days']).toContain(result);
  });
});
