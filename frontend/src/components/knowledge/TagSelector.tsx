/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Spec §2 UI: controlled-vocabulary tag selector. One multi-select per active
// dimension; required dimensions are marked and validated by the caller via
// missingRequiredDimensions().

import { Select, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import type { TaxonomyDimension, TaxonomyTerm } from '../../api/knowledge';

interface Props {
  dimensions: TaxonomyDimension[];
  value: string[]; // selected term ids across all dimensions
  onChange: (termIds: string[]) => void;
  disabled?: boolean;
}

/** Indent hierarchical terms below their parent for readability. */
function orderTerms(terms: TaxonomyTerm[]): Array<TaxonomyTerm & { depth: number }> {
  const byParent = new Map<string | null, TaxonomyTerm[]>();
  terms.forEach((term) => {
    const key = term.parent || null;
    const bucket = byParent.get(key) || [];
    bucket.push(term);
    byParent.set(key, bucket);
  });
  const ordered: Array<TaxonomyTerm & { depth: number }> = [];
  const visit = (parent: string | null, depth: number) => {
    (byParent.get(parent) || []).forEach((term) => {
      ordered.push({ ...term, depth });
      visit(term.id, depth + 1);
    });
  };
  visit(null, 0);
  // Terms whose parent is outside the active set still need to appear.
  const seen = new Set(ordered.map((t) => t.id));
  terms.forEach((t) => { if (!seen.has(t.id)) ordered.push({ ...t, depth: 0 }); });
  return ordered;
}

export function missingRequiredDimensions(
  dimensions: TaxonomyDimension[],
  selectedTermIds: string[],
): TaxonomyDimension[] {
  const selected = new Set(selectedTermIds);
  return dimensions.filter(
    (dim) => dim.required && !dim.terms.some((term) => selected.has(term.id)),
  );
}

export function TagSelector({ dimensions, value, onChange, disabled }: Props) {
  const { t } = useTranslation('common');
  if (!dimensions.length) {
    return (
      <div style={{ color: 'var(--color-text-tertiary)', fontSize: 13 }}>
        {t('taxonomy_no_dimensions')}
      </div>
    );
  }
  const selected = new Set(value);

  const handleDimensionChange = (dimension: TaxonomyDimension, ids: string[]) => {
    const dimTermIds = new Set(dimension.terms.map((term) => term.id));
    const others = value.filter((id) => !dimTermIds.has(id));
    onChange([...others, ...ids]);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {dimensions.map((dimension) => {
        const ordered = orderTerms(dimension.terms);
        const dimValue = dimension.terms.filter((term) => selected.has(term.id)).map((term) => term.id);
        return (
          <div key={dimension.id}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: 13 }}>
              {dimension.name}
              {dimension.required && (
                <Tag color="red" style={{ marginLeft: 8, fontSize: 11, lineHeight: '16px' }}>
                  {t('taxonomy_required')}
                </Tag>
              )}
            </label>
            <Select
              mode="multiple"
              style={{ width: '100%' }}
              placeholder={t('taxonomy_select_placeholder', { name: dimension.name })}
              value={dimValue}
              onChange={(ids) => handleDimensionChange(dimension, ids as string[])}
              disabled={disabled}
              optionFilterProp="label"
              options={ordered.map((term) => ({
                value: term.id,
                label: `${'　'.repeat(term.depth)}${term.label}`,
              }))}
            />
          </div>
        );
      })}
    </div>
  );
}
