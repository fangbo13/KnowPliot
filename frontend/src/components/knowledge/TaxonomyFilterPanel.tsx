/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Spec §2 UI: multi-dimension pivot filter panel (科目 × FY × 阶段 × SCOT).
// Not a fixed folder tree — any term combination narrows the document list.
// Includes the "我负责的科目" quick view backed by /documents/my-terms/.

import { useEffect, useRef, useState } from 'react';
import { Checkbox, Collapse, Spin, Tag, Typography } from 'antd';
import { StarOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { taxonomyApi } from '../../api/knowledge';
import type { TaxonomyDimension, TermOwnership } from '../../api/knowledge';

interface Props {
  dimensions: TaxonomyDimension[];
  loading: boolean;
  selectedCodes: string[];
  onChange: (codes: string[]) => void;
}

export function TaxonomyFilterPanel({ dimensions, loading, selectedCodes, onChange }: Props) {
  const { t } = useTranslation('common');
  const [myTerms, setMyTerms] = useState<TermOwnership[]>([]);
  // Controlled activeKey so panels auto-expand when dimensions are async-loaded.
  // defaultActiveKey only applies on first render (when dimensions is still empty).
  const [activeKeys, setActiveKeys] = useState<string[]>([]);
  // Track whether the one-time auto-expand has already run so collapsing all
  // panels does not trigger re-expansion.
  const autoExpandedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    taxonomyApi.getMyTerms()
      .then((data) => { if (!cancelled) setMyTerms(data.terms || []); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  // Auto-expand all dimension panels once dimensions data arrives.
  useEffect(() => {
    if (dimensions.length > 0 && !autoExpandedRef.current) {
      autoExpandedRef.current = true;
      setActiveKeys(dimensions.map((d) => d.code));
    }
  }, [dimensions]);

  const toggle = (code: string, checked: boolean) => {
    if (checked) onChange([...selectedCodes, code]);
    else onChange(selectedCodes.filter((c) => c !== code));
  };

  if (loading) {
    return <div style={{ padding: 24, textAlign: 'center' }}><Spin size="small" /></div>;
  }
  if (!dimensions.length) {
    return (
      <div style={{ padding: 12, color: 'var(--color-text-tertiary)', fontSize: 13 }}>
        {t('taxonomy_no_dimensions')}
      </div>
    );
  }

  const selected = new Set(selectedCodes);
  const myCodes = myTerms.map((o) => o.term_code);

  return (
    <div data-testid="taxonomy-filter-panel">
      {myCodes.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Typography.Text strong style={{ fontSize: 13 }}>
            <StarOutlined style={{ marginRight: 6, color: 'var(--color-warning)' }} />
            {t('taxonomy_my_terms')}
          </Typography.Text>
          <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {myTerms.map((o) => (
              <Tag.CheckableTag
                key={o.id}
                checked={selected.has(o.term_code)}
                onChange={(checked) => toggle(o.term_code, checked)}
              >
                {o.term_label}
              </Tag.CheckableTag>
            ))}
          </div>
        </div>
      )}
      <Collapse
        ghost
        size="small"
        activeKey={activeKeys}
        onChange={(keys) => setActiveKeys(keys as string[])}
        items={dimensions.map((dimension) => ({
          key: dimension.code,
          label: (
            <span style={{ fontWeight: 500, fontSize: 13 }}>
              {dimension.name}
              {dimension.required && <span style={{ color: 'var(--color-error)', marginLeft: 4 }}>*</span>}
            </span>
          ),
          children: (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {dimension.terms.map((term) => (
                <Checkbox
                  key={term.id}
                  checked={selected.has(term.code)}
                  onChange={(e) => toggle(term.code, e.target.checked)}
                  style={{ marginLeft: term.parent ? 16 : 0, fontSize: 13 }}
                >
                  {term.label}
                </Checkbox>
              ))}
            </div>
          ),
        }))}
      />
      {selectedCodes.length > 0 && (
        <a
          role="button"
          onClick={() => onChange([])}
          style={{ fontSize: 12, display: 'inline-block', marginTop: 8 }}
        >
          {t('taxonomy_clear_filters')}
        </a>
      )}
    </div>
  );
}
