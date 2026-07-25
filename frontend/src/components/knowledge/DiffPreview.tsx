/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useMemo } from 'react';
import { Tag, Space, Spin, Empty } from 'antd';
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
 */
export function DiffPreview({ data, loading, error }: DiffPreviewProps) {
  const { t } = useTranslation('common');

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
          </Space>
        </div>
      )}

      {/* Diff blocks */}
      <div className="diff-preview__blocks">
        {data.diff.map((block, idx) => (
          <DiffBlockView key={idx} block={block} />
        ))}
      </div>
    </div>
  );
}

/** Render a single diff block. */
function DiffBlockView({ block }: { block: DiffBlock }) {
  const { t } = useTranslation('common');
  const color = TAG_COLORS[block.tag];
  const label = t(TAG_I18N[block.tag]);

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
              <span className="diff-line__text">{line}</span>
            </div>
          ))}
        {(block.tag === 'insert' || block.tag === 'replace') &&
          block.new_lines.map((line, i) => (
            <div key={`n${i}`} className="diff-line diff-line--new">
              <span className="diff-line__marker">+</span>
              <span className="diff-line__text">{line}</span>
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
