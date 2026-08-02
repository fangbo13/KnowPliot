/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useMemo, useState } from 'react';
import { Tag, Space, Spin, Empty, Segmented } from 'antd';
import { useTranslation } from 'react-i18next';
import './DiffPreview.css';

/** A single diff block returned by the preview-diff endpoint. */
export interface DiffBlock {
  tag: 'equal' | 'replace' | 'delete' | 'insert';
  old_start: number;
  old_end: number;
  new_start: number;
  new_end: number;
  old_lines: string[];
  new_lines: string[];
}

/** Statistics returned by the preview-diff endpoint. */
export interface DiffStats {
  old_lines: number;
  new_lines: number;
  changed_blocks: number;
}

/** Full preview-diff response shape. */
export interface DiffPreviewData {
  document_id: string;
  old_version: number;
  diff: DiffBlock[];
  stats: DiffStats;
}

interface DiffPreviewProps {
  /** The diff data from preview-diff endpoint, or null while loading. */
  data: DiffPreviewData | null;
  /** Loading state. */
  loading?: boolean;
  /** Optional error message. */
  error?: string | null;
}

/** Color per diff tag, using CSS variables for theme support. */
const TAG_COLORS: Record<DiffBlock['tag'], string> = {
  equal: 'var(--color-text-secondary)',
  replace: 'var(--color-warning)',
  delete: 'var(--color-error)',
  insert: 'var(--color-success)',
};

/** i18n key per diff tag. */
const TAG_I18N: Record<DiffBlock['tag'], string> = {
  equal: 'kb_diff_equal',
  replace: 'kb_diff_replace',
  delete: 'kb_diff_delete',
  insert: 'kb_diff_insert',
};

/**
 * KB-12-Features §6: Diff preview component.
 *
 * Renders structured line-level differences from the preview-diff endpoint.
 * Each block is colored by type (equal/replace/delete/insert) using CSS
 * variables for light/dark mode support.
 *
 * KB optimization spec §5.4: Obsidian-style upgrades — word-level highlight
 * inside replace blocks and a unified / side-by-side view toggle.
 */
export function DiffPreview({ data, loading, error }: DiffPreviewProps) {
  const { t } = useTranslation('common');
  const [viewMode, setViewMode] = useState<'unified' | 'split'>('unified');

  const stats = useMemo(() => {
    if (!data) return null;
    const counts = { equal: 0, replace: 0, delete: 0, insert: 0 };
    for (const block of data.diff) {
      counts[block.tag]++;
    }
    return { counts, ...data.stats };
  }, [data]);

  if (loading) {
    return (
      <div className="diff-preview__loading">
        <Spin size="small" />
        <span style={{ marginLeft: 8, color: 'var(--color-text-secondary)' }}>
          {t('kb_diff_loading')}
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="diff-preview__error">
        <span style={{ color: 'var(--color-error)' }}>{error}</span>
      </div>
    );
  }

  if (!data || !data.diff || data.diff.length === 0) {
    return (
      <div className="diff-preview__empty">
        <Empty description={t('kb_no_diff')} />
      </div>
    );
  }

  return (
    <div className="diff-preview__container">
      {/* Statistics bar */}
      {stats && (
        <div className="diff-preview__stats">
          <Space size="small" wrap>
            <Tag color="default">
              {t('kb_diff_equal')}: {stats.counts.equal}
            </Tag>
            <Tag color="warning">
              {t('kb_diff_replace')}: {stats.counts.replace}
            </Tag>
            <Tag color="error">
              {t('kb_diff_delete')}: {stats.counts.delete}
            </Tag>
            <Tag color="success">
              {t('kb_diff_insert')}: {stats.counts.insert}
            </Tag>
            <span className="diff-preview__line-counts">
              {stats.old_lines} → {stats.new_lines}
            </span>
            <Segmented
              size="small"
              value={viewMode}
              onChange={(v) => setViewMode(v as 'unified' | 'split')}
              options={[
                { label: t('kb_diff_unified'), value: 'unified' },
                { label: t('kb_diff_side_by_side'), value: 'split' },
              ]}
            />
          </Space>
        </div>
      )}

      {/* Diff blocks */}
      <div className="diff-preview__blocks">
        {data.diff.map((block, idx) => (
          <DiffBlockView key={idx} block={block} viewMode={viewMode} />
        ))}
      </div>
    </div>
  );
}

/** Tokenize a line for word-level diffing (words / CJK chars / spaces). */
function tokenize(line: string): string[] {
  return line.match(/[A-Za-z0-9_]+|[\u4e00-\u9fff]|\s+|./g) || [];
}

/**
 * LCS-based inline diff between two lines. Returns marked segments for the
 * old side (removed) and new side (added) — Obsidian-style word highlight.
 */
function inlineDiff(oldLine: string, newLine: string) {
  const a = tokenize(oldLine);
  const b = tokenize(newLine);
  const m = a.length;
  const n = b.length;
  // LCS table (capped to keep worst case cheap on very long lines).
  if (m * n > 40000) {
    return {
      oldSegs: [{ text: oldLine, changed: true }],
      newSegs: [{ text: newLine, changed: true }],
    };
  }
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const oldSegs: Array<{ text: string; changed: boolean }> = [];
  const newSegs: Array<{ text: string; changed: boolean }> = [];
  const push = (segs: Array<{ text: string; changed: boolean }>, text: string, changed: boolean) => {
    const last = segs[segs.length - 1];
    if (last && last.changed === changed) last.text += text;
    else segs.push({ text, changed });
  };
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      push(oldSegs, a[i], false);
      push(newSegs, b[j], false);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      push(oldSegs, a[i], true);
      i++;
    } else {
      push(newSegs, b[j], true);
      j++;
    }
  }
  while (i < m) push(oldSegs, a[i++], true);
  while (j < n) push(newSegs, b[j++], true);
  return { oldSegs, newSegs };
}

function InlineSegments({ segs, kind }: { segs: Array<{ text: string; changed: boolean }>; kind: 'old' | 'new' }) {
  return (
    <>
      {segs.map((seg, i) =>
        seg.changed ? (
          <mark key={i} className={`diff-word diff-word--${kind}`}>
            {seg.text}
          </mark>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </>
  );
}

/** Render a single diff block (unified or side-by-side). */
function DiffBlockView({ block, viewMode }: { block: DiffBlock; viewMode: 'unified' | 'split' }) {
  const { t } = useTranslation('common');
  const color = TAG_COLORS[block.tag];
  const label = t(TAG_I18N[block.tag]);

  // Word-level pairing for replace blocks: pair lines by index.
  const inline = useMemo(() => {
    if (block.tag !== 'replace') return null;
    const pairs = Math.max(block.old_lines.length, block.new_lines.length);
    return Array.from({ length: pairs }, (_, i) =>
      inlineDiff(block.old_lines[i] ?? '', block.new_lines[i] ?? ''),
    );
  }, [block]);

  if (viewMode === 'split' && block.tag !== 'equal') {
    const rows = Math.max(block.old_lines.length, block.new_lines.length);
    return (
      <div className={`diff-block diff-block--${block.tag}`}>
        <div className="diff-block__tag" style={{ color }}>
          {label}
        </div>
        <div className="diff-block__split">
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="diff-split__row">
              <div className="diff-line diff-line--old diff-split__cell">
                {block.old_lines[i] !== undefined && (
                  <>
                    <span className="diff-line__marker">-</span>
                    <span className="diff-line__text">
                      {inline ? <InlineSegments segs={inline[i].oldSegs} kind="old" /> : block.old_lines[i]}
                    </span>
                  </>
                )}
              </div>
              <div className="diff-line diff-line--new diff-split__cell">
                {block.new_lines[i] !== undefined && (
                  <>
                    <span className="diff-line__marker">+</span>
                    <span className="diff-line__text">
                      {inline ? <InlineSegments segs={inline[i].newSegs} kind="new" /> : block.new_lines[i]}
                    </span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`diff-block diff-block--${block.tag}`}>
      <div className="diff-block__tag" style={{ color }}>
        {label}
      </div>
      <div className="diff-block__lines">
        {(block.tag === 'delete' || block.tag === 'replace') &&
          block.old_lines.map((line, i) => (
            <div key={`o${i}`} className="diff-line diff-line--old">
              <span className="diff-line__marker">-</span>
              <span className="diff-line__text">
                {inline && inline[i] ? <InlineSegments segs={inline[i].oldSegs} kind="old" /> : line}
              </span>
            </div>
          ))}
        {(block.tag === 'insert' || block.tag === 'replace') &&
          block.new_lines.map((line, i) => (
            <div key={`n${i}`} className="diff-line diff-line--new">
              <span className="diff-line__marker">+</span>
              <span className="diff-line__text">
                {inline && inline[i] ? <InlineSegments segs={inline[i].newSegs} kind="new" /> : line}
              </span>
            </div>
          ))}
        {block.tag === 'equal' &&
          block.new_lines.map((line, i) => (
            <div key={`e${i}`} className="diff-line diff-line--equal">
              <span className="diff-line__marker"> </span>
              <span className="diff-line__text">{line}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

export default DiffPreview;
