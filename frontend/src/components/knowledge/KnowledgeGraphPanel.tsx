/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Spec §5 UI: Local Graph — force-directed document graph rendered as SVG.
// A small in-house simulation keeps the bundle budget intact (no heavy graph
// library). Node size = incoming links, colour = freshness, edge style by
// kind (term / explicit link / embedding similarity). Click highlights the
// neighbourhood and opens a side preview.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Empty, Select, Spin, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { vizApi } from '../../api/knowledge';
import type { GraphEdge, GraphNode, TaxonomyDimension } from '../../api/knowledge';

const WIDTH = 860;
const HEIGHT = 560;
const ITERATIONS = 220;

interface PositionedNode extends GraphNode {
  x: number;
  y: number;
}

/** Deterministic pseudo-random from a string id (stable initial layout). */
function seed(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return (h % 10000) / 10000;
}

/** Simple spring-electric force layout, run once per data load. */
function runLayout(nodes: GraphNode[], edges: GraphEdge[]): PositionedNode[] {
  const positioned: PositionedNode[] = nodes.map((node, i) => ({
    ...node,
    x: WIDTH / 2 + Math.cos(seed(node.id) * Math.PI * 2) * (120 + (i % 7) * 30),
    y: HEIGHT / 2 + Math.sin(seed(node.id + 'y') * Math.PI * 2) * (100 + (i % 5) * 30),
  }));
  const index = new Map(positioned.map((n, i) => [n.id, i]));
  const springLength = 130;
  for (let iter = 0; iter < ITERATIONS; iter++) {
    const temperature = 1 - iter / ITERATIONS;
    // Repulsion between all pairs.
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        const a = positioned[i];
        const b = positioned[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const distSq = Math.max(dx * dx + dy * dy, 1);
        const dist = Math.sqrt(distSq);
        const force = (2600 / distSq) * temperature;
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        a.x += dx; a.y += dy;
        b.x -= dx; b.y -= dy;
      }
    }
    // Spring attraction along edges.
    for (const edge of edges) {
      const si = index.get(edge.source);
      const ti = index.get(edge.target);
      if (si === undefined || ti === undefined) continue;
      const a = positioned[si];
      const b = positioned[ti];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const force = ((dist - springLength) / dist) * 0.045 * temperature;
      a.x += dx * force; a.y += dy * force;
      b.x -= dx * force; b.y -= dy * force;
    }
    // Keep nodes inside the viewport.
    for (const node of positioned) {
      node.x = Math.min(Math.max(node.x, 30), WIDTH - 30);
      node.y = Math.min(Math.max(node.y, 30), HEIGHT - 30);
    }
  }
  return positioned;
}

/** Freshness → colour: green (fresh) → amber → grey (stale). */
function freshnessColor(freshness: number, status: string): string {
  if (status === 'stale') return 'var(--color-warning)';
  if (freshness >= 0.7) return 'var(--color-success)';
  if (freshness >= 0.4) return '#d4a017';
  return 'var(--color-text-tertiary)';
}

const edgeStyle: Record<string, { stroke: string; dash?: string }> = {
  link: { stroke: 'var(--color-accent)' },
  term: { stroke: 'var(--color-border)' },
  similar: { stroke: 'var(--color-warning)', dash: '4 4' },
};

interface Props {
  dimensions: TaxonomyDimension[];
}

export function KnowledgeGraphPanel({ dimensions }: Props) {
  const { t } = useTranslation('common');
  const [nodes, setNodes] = useState<PositionedNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [termFilter, setTermFilter] = useState<string | undefined>(undefined);
  const [selected, setSelected] = useState<PositionedNode | null>(null);
  const loadedRef = useRef(false);

  const load = useCallback(async (term?: string) => {
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      const data = await vizApi.getGraph(term);
      setNodes(runLayout(data.nodes, data.edges));
      setEdges(data.edges);
    } catch {
      setError(t('graph_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    void load();
  }, [load]);

  const neighbours = useMemo(() => {
    if (!selected) return new Set<string>();
    const set = new Set<string>([selected.id]);
    edges.forEach((edge) => {
      if (edge.source === selected.id) set.add(edge.target);
      if (edge.target === selected.id) set.add(edge.source);
    });
    return set;
  }, [selected, edges]);

  const position = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const termOptions = dimensions.flatMap((dim) =>
    dim.terms.map((term) => ({ value: term.code, label: `${dim.name} / ${term.label}` })),
  );

  return (
    <div data-testid="knowledge-graph-panel">
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <Select
          allowClear
          showSearch
          style={{ minWidth: 260 }}
          placeholder={t('graph_term_filter')}
          value={termFilter}
          optionFilterProp="label"
          options={termOptions}
          onChange={(value) => { setTermFilter(value); void load(value); }}
        />
        <Button icon={<ReloadOutlined />} onClick={() => void load(termFilter)}>{t('refresh')}</Button>
        <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)' }}>
          {t('graph_legend')}
        </span>
      </div>
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
      <Spin spinning={loading}>
        {nodes.length === 0 && !loading ? (
          <Empty description={t('graph_empty')} />
        ) : (
          <div style={{ display: 'flex', gap: 16 }}>
            <svg
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              style={{
                flex: 1,
                minWidth: 0,
                border: '1px solid var(--color-border)',
                borderRadius: 12,
                background: 'var(--color-bg-container)',
              }}
              role="img"
              aria-label={t('graph_aria_label')}
            >
              {edges.map((edge, i) => {
                const a = position.get(edge.source);
                const b = position.get(edge.target);
                if (!a || !b) return null;
                const style = edgeStyle[edge.kind] || edgeStyle.term;
                const dimmed = selected && !(neighbours.has(edge.source) && neighbours.has(edge.target));
                return (
                  <line
                    key={`${edge.source}-${edge.target}-${edge.kind}-${i}`}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={style.stroke}
                    strokeDasharray={style.dash}
                    strokeWidth={edge.kind === 'link' ? 1.6 : 1}
                    opacity={dimmed ? 0.08 : 0.55}
                  />
                );
              })}
              {nodes.map((node) => {
                const radius = 7 + Math.min(node.incoming_links, 8) * 1.6;
                const dimmed = selected && !neighbours.has(node.id);
                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x},${node.y})`}
                    style={{ cursor: 'pointer' }}
                    opacity={dimmed ? 0.18 : 1}
                    onClick={() => setSelected((prev) => (prev?.id === node.id ? null : node))}
                  >
                    <circle
                      r={radius}
                      fill={freshnessColor(node.freshness, node.status)}
                      stroke={selected?.id === node.id ? 'var(--color-accent)' : 'var(--color-bg-container)'}
                      strokeWidth={selected?.id === node.id ? 3 : 1.5}
                    />
                    <text
                      y={radius + 12}
                      textAnchor="middle"
                      fontSize={10}
                      fill="var(--color-text-secondary)"
                    >
                      {node.title.length > 14 ? `${node.title.slice(0, 14)}…` : node.title}
                    </text>
                  </g>
                );
              })}
            </svg>
            {selected && (
              <div
                style={{
                  width: 260,
                  flexShrink: 0,
                  border: '1px solid var(--color-border)',
                  borderRadius: 12,
                  padding: 16,
                  background: 'var(--color-bg-container)',
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 8 }}>{selected.title}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
                  <Tag color="blue">v{selected.version}</Tag>
                  <Tag color={selected.status === 'stale' ? 'orange' : 'green'}>{selected.status}</Tag>
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginBottom: 8 }}>
                  <div>{t('graph_node_freshness')}: {(selected.freshness * 100).toFixed(0)}%</div>
                  <div>{t('graph_node_incoming')}: {selected.incoming_links}</div>
                  <div>{t('kb_created')}: {new Date(selected.updated_at).toLocaleDateString()}</div>
                </div>
                {selected.terms.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {selected.terms.map((code) => <Tag key={code}>{code}</Tag>)}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Spin>
    </div>
  );
}
