/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Collapse,
  Drawer,
  Empty,
  Input,
  InputNumber,
  Segmented,
  Select,
  Slider,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  AimOutlined,
  CompressOutlined,
  ExpandOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import { vizApi } from '../../api/knowledge';
import type {
  GraphEdgeKind,
  GraphNode,
  GraphQueryRequest,
  GraphResponse,
  TaxonomyDimension,
} from '../../api/knowledge';
import type { GraphRenderSettings } from './GraphRenderer';
import './KnowledgeGraphPanel.css';


const GraphRenderer = lazy(() => import('./GraphRenderer'));

const GRAPH_COPY: Record<'en' | 'zh', Record<string, string>> = {
  en: {
    graph_query_placeholder: 'Search graph: file:, content:, tag:, status:, owner:, updated:, links-to:…',
    graph_direction: 'Link direction', graph_direction_both: 'Both', graph_direction_in: 'Incoming', graph_direction_out: 'Outgoing',
    graph_relation_types: 'Relation types', graph_show_ghosts: 'Show unresolved links', graph_fit: 'Fit to viewport',
    graph_fullscreen: 'Fullscreen', graph_settings: 'Graph settings', graph_save_scene: 'Save investigation scene', graph_scene_saved: 'Investigation scene saved',
    graph_filters: 'Filters', graph_groups: 'Groups', graph_groups_hint: 'Group queries are evaluated on the server; the first matching group sets the base node color.',
    graph_group_color: 'Group color', graph_group_name: 'Group name', graph_group_query: 'Group DSL query', graph_add_group: 'Add group',
    graph_display: 'Display', graph_forces: 'Forces', graph_label_density: 'Label density', graph_node_size: 'Node size', graph_edge_width: 'Edge width',
    graph_center_force: 'Center force', graph_repulsion: 'Repulsion', graph_restore_defaults: 'Restore defaults', graph_owner: 'Owner',
    graph_open_document: 'Open document', graph_set_center: 'Set as Local center', graph_selected_none: 'Select a node to inspect it',
    graph_nodes: 'nodes', graph_edges: 'relations', graph_truncated: 'Result truncated to budget', graph_load_more: 'Load more', graph_list_view: 'Accessible list view',
    graph_evidence: 'Relationship evidence',
    graph_expand_node: 'Expand up to 25 neighbors',
  },
  zh: {
    graph_query_placeholder: '搜索图谱：file:、content:、tag:、status:、owner:、updated:、links-to:…',
    graph_direction: '链接方向', graph_direction_both: '双向', graph_direction_in: '入链', graph_direction_out: '出链',
    graph_relation_types: '关系类型', graph_show_ghosts: '显示未解析链接', graph_fit: '适配视口', graph_fullscreen: '全屏', graph_settings: '图谱设置',
    graph_save_scene: '保存调查场景', graph_scene_saved: '调查场景已保存', graph_filters: '筛选', graph_groups: '分组',
    graph_groups_hint: '分组查询由服务端解析；首个匹配分组决定节点基础颜色。', graph_group_color: '分组颜色', graph_group_name: '分组名称',
    graph_group_query: '分组 DSL 查询', graph_add_group: '添加分组', graph_display: '显示', graph_forces: '力参数', graph_label_density: '标签密度',
    graph_node_size: '节点大小', graph_edge_width: '边宽', graph_center_force: '中心力', graph_repulsion: '斥力', graph_restore_defaults: '恢复默认',
    graph_owner: '作者', graph_open_document: '打开文档', graph_set_center: '设为 Local 中心', graph_selected_none: '选择节点以查看详情',
    graph_nodes: '节点', graph_edges: '关系', graph_truncated: '结果已按预算截断', graph_load_more: '继续加载', graph_list_view: '无障碍列表视图',
    graph_evidence: '关系证据',
    graph_expand_node: '展开最多 25 个邻居',
  },
};

interface Props {
  dimensions: TaxonomyDimension[];
  initialCenterId?: string;
  compact?: boolean;
  onOpenDocument?: (documentId: string) => void;
}

type GraphMode = 'global' | 'local';
type Direction = 'in' | 'out' | 'both';
type GraphGroup = { id: string; name: string; query: string; color: string };

const DEFAULT_SETTINGS: GraphRenderSettings = {
  labelDensity: 1,
  nodeScale: 1,
  edgeScale: 1,
  centerForce: 1,
  repulsion: 10,
  reducedMotion: false,
};

function mergeResponse(current: GraphResponse, next: GraphResponse): GraphResponse {
  const nodes = new Map(current.nodes.map((node) => [node.id, node]));
  const edges = new Map(current.edges.map((edge) => [edge.id, edge]));
  next.nodes.forEach((node) => nodes.set(node.id, node));
  next.edges.forEach((edge) => edges.set(edge.id, edge));
  return {
    ...next,
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    meta: {
      ...next.meta,
      returned_nodes: nodes.size,
      returned_edges: edges.size,
    },
  };
}

function apiErrorMessage(error: unknown, fallback: string): string {
  if (typeof error !== 'object' || error === null) return fallback;
  const response = (error as { response?: { data?: Record<string, unknown> } }).response;
  const data = response?.data;
  if (!data) return fallback;
  const detail = typeof data.detail === 'string' ? data.detail : fallback;
  const position = typeof data.position === 'number' ? ` (${data.position})` : '';
  const hint = typeof data.hint === 'string' ? ` — ${data.hint}` : '';
  return `${detail}${position}${hint}`;
}

export function KnowledgeGraphPanel({
  dimensions,
  initialCenterId,
  compact = false,
  onOpenDocument,
}: Props) {
  const { t: translate, i18n } = useTranslation('common');
  const language = i18n?.language?.startsWith('zh') ? 'zh' : 'en';
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) => GRAPH_COPY[language][key] ?? translate(key, options),
    [language, translate],
  );
  const tRef = useRef(t);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const requestRef = useRef(0);
  const [mode, setMode] = useState<GraphMode>(initialCenterId ? 'local' : 'global');
  const [centerId, setCenterId] = useState(initialCenterId);
  const [depth, setDepth] = useState<1 | 2 | 3>(1);
  const [direction, setDirection] = useState<Direction>('both');
  const [edgeKinds, setEdgeKinds] = useState<GraphEdgeKind[]>(['links_to']);
  const [includeGhosts, setIncludeGhosts] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<GraphResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fitToken, setFitToken] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [groups, setGroups] = useState<GraphGroup[]>([]);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [expanding, setExpanding] = useState(false);

  useEffect(() => {
    tRef.current = t;
  }, [t]);

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!media) return undefined;
    const update = () => setSettings((current) => ({ ...current, reducedMotion: media.matches }));
    update();
    media.addEventListener?.('change', update);
    return () => media.removeEventListener?.('change', update);
  }, []);

  useEffect(() => {
    if (!initialCenterId) return;
    setCenterId(initialCenterId);
    setMode('local');
  }, [initialCenterId]);

  const request = useMemo<GraphQueryRequest>(() => ({
    schema_version: 'graph.query.v1',
    scope: {
      mode,
      ...(mode === 'local' && centerId ? { center_id: centerId, depth, direction } : {}),
    },
    edge_kinds: edgeKinds,
    include_ghosts: includeGhosts,
    query: query || undefined,
    groups: groups.filter((group) => group.name.trim() && group.query.trim()),
    limits: { nodes: compact ? 150 : 300, edges: compact ? 750 : 1500 },
  }), [centerId, compact, depth, direction, edgeKinds, groups, includeGhosts, mode, query]);

  const load = useCallback(async () => {
    if (request.scope.mode === 'local' && !request.scope.center_id) {
      setResult(null);
      return;
    }
    const requestId = ++requestRef.current;
    setLoading(true);
    setError(null);
    try {
      const response = await vizApi.queryGraph(request);
      if (requestId !== requestRef.current) return;
      setResult(response);
      setSelectedId(null);
      setEvidence(null);
    } catch (caught) {
      if (requestId !== requestRef.current) return;
      setError(apiErrorMessage(caught, tRef.current('graph_load_failed')));
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => result?.nodes.find((node) => node.id === selectedId) ?? null,
    [result?.nodes, selectedId],
  );

  const openNode = useCallback((node: GraphNode) => {
    setSelectedId(node.id);
    setInspectorOpen(true);
    if (node.resource_id && onOpenDocument) onOpenDocument(node.resource_id);
  }, [onOpenDocument]);

  const makeCenter = useCallback((node: GraphNode) => {
    if (!node.resource_id || node.type !== 'document') return;
    setCenterId(node.resource_id);
    setMode('local');
  }, []);

  const selectEdge = useCallback(async (edgeId: string) => {
    const edge = result?.edges.find((item) => item.id === edgeId);
    if (!edge) return;
    setSelectedId(null);
    setEvidenceLoading(true);
    setInspectorOpen(true);
    if (edge.evidence.ref.startsWith('aggregate:')) {
      setEvidence({
        ref: edge.evidence.ref,
        kind: edge.kind,
        anchor_text: edge.evidence.summary,
        count: edge.evidence.count,
      });
      setEvidenceLoading(false);
      return;
    }
    try {
      setEvidence(await vizApi.getEvidence(edge.evidence.ref));
    } catch (caught) {
      setError(apiErrorMessage(caught, tRef.current('graph_load_failed')));
    } finally {
      setEvidenceLoading(false);
    }
  }, [result?.edges]);

  const expandNode = useCallback(async (node: GraphNode) => {
    if (!node.resource_id) return;
    setExpanding(true);
    try {
      const expanded = await vizApi.expandGraph({
        schema_version: 'graph.expand.v1',
        center_id: node.resource_id,
        depth: 1,
        direction,
        edge_kinds: edgeKinds,
        include_ghosts: includeGhosts,
        query: query || undefined,
        limit: 25,
      });
      setResult((current) => current ? mergeResponse(current, expanded) : expanded);
    } catch (caught) {
      setError(apiErrorMessage(caught, tRef.current('graph_load_failed')));
    } finally {
      setExpanding(false);
    }
  }, [direction, edgeKinds, includeGhosts, query]);

  const evidenceOccurrences = Array.isArray(evidence?.occurrences)
    ? evidence.occurrences as Array<Record<string, unknown>>
    : [];

  const loadMore = useCallback(async () => {
    const cursor = result?.meta.continuations.nodes;
    if (!cursor || !result) return;
    setLoadingMore(true);
    setError(null);
    try {
      const next = await vizApi.queryGraph({ ...request, cursor });
      setResult((current) => current ? mergeResponse(current, next) : next);
    } catch (caught) {
      setError(apiErrorMessage(caught, t('graph_load_failed')));
    } finally {
      setLoadingMore(false);
    }
  }, [request, result, t]);

  const toggleFullscreen = useCallback(async () => {
    const root = rootRef.current;
    if (!root) return;
    try {
      if (!document.fullscreenElement && root.requestFullscreen) await root.requestFullscreen();
      else if (document.fullscreenElement) await document.exitFullscreen();
      else setFullscreen((value) => !value);
    } catch {
      setFullscreen((value) => !value);
    }
  }, []);

  useEffect(() => {
    const update = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', update);
    return () => document.removeEventListener('fullscreenchange', update);
  }, []);

  const saveScene = useCallback(async () => {
    try {
      await vizApi.createScene({
        name: `${mode === 'local' ? t('graph_mode_local') : t('graph_mode_global')} ${new Date().toLocaleDateString()}`,
        visibility: 'private',
        canonical_query: request,
        layout: { center_id: centerId, selected_id: selectedId, settings },
      });
      void message.success(t('graph_scene_saved'));
    } catch (caught) {
      setError(apiErrorMessage(caught, t('graph_load_failed')));
    }
  }, [centerId, mode, request, selectedId, settings, t]);

  const relationOptions: Array<{ value: GraphEdgeKind; label: string }> = [
    { value: 'links_to', label: t('graph_edge_link') },
    { value: 'tagged_with', label: t('graph_edge_term') },
    { value: 'similar_to', label: t('graph_edge_similar') },
  ];
  const termCount = dimensions.reduce((count, dimension) => count + dimension.terms.length, 0);

  return (
    <div
      ref={rootRef}
      className={`knowledge-graph-workspace${compact ? ' knowledge-graph-workspace--compact' : ''}${fullscreen ? ' is-fullscreen' : ''}`}
      data-testid="knowledge-graph-panel"
    >
      <header className="graph-toolbar">
        <Input.Search
          className="graph-query"
          allowClear
          value={queryInput}
          placeholder={t('graph_query_placeholder')}
          enterButton
          onChange={(event) => setQueryInput(event.target.value)}
          onSearch={(value) => setQuery(value.trim())}
          aria-label={t('graph_query_placeholder')}
        />
        <Segmented
          value={mode}
          options={[
            { value: 'global', label: t('graph_mode_global') },
            { value: 'local', label: t('graph_mode_local') },
          ]}
          onChange={(value) => setMode(value as GraphMode)}
        />
        {mode === 'local' && (
          <>
            <Select
              className="graph-center-select"
              showSearch
              value={centerId}
              placeholder={t('graph_center_placeholder')}
              optionFilterProp="label"
              options={(result?.nodes ?? [])
                .filter((node) => node.type === 'document' && node.resource_id)
                .map((node) => ({ value: node.resource_id!, label: node.label }))}
              onChange={setCenterId}
            />
            <Select
              value={depth}
              aria-label={t('graph_depth')}
              options={[1, 2, 3].map((value) => ({ value, label: `${value} ${t('graph_depth')}` }))}
              onChange={(value) => setDepth(value as 1 | 2 | 3)}
            />
            <Select
              value={direction}
              aria-label={t('graph_direction')}
              options={[
                { value: 'both', label: t('graph_direction_both') },
                { value: 'in', label: t('graph_direction_in') },
                { value: 'out', label: t('graph_direction_out') },
              ]}
              onChange={(value) => setDirection(value as Direction)}
            />
          </>
        )}
        <Space.Compact className="graph-toolbar-actions">
          <Tooltip title={t('graph_fit')}><Button aria-label={t('graph_fit')} icon={<AimOutlined />} onClick={() => setFitToken((value) => value + 1)} /></Tooltip>
          <Tooltip title={t('refresh')}><Button aria-label={t('refresh')} icon={<ReloadOutlined />} onClick={() => void load()} /></Tooltip>
          {!compact && <Tooltip title={t('graph_save_scene')}><Button aria-label={t('graph_save_scene')} icon={<SaveOutlined />} onClick={() => void saveScene()} /></Tooltip>}
          <Tooltip title={t('graph_settings')}><Button aria-label={t('graph_settings')} icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)} /></Tooltip>
          <Tooltip title={t('graph_fullscreen')}><Button aria-label={t('graph_fullscreen')} icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={() => void toggleFullscreen()} /></Tooltip>
        </Space.Compact>
      </header>

      <div className="graph-relation-bar" aria-label={t('graph_relation_types')}>
        <Checkbox.Group
          value={edgeKinds}
          options={relationOptions}
          onChange={(values) => setEdgeKinds(values as GraphEdgeKind[])}
        />
        <Switch checked={includeGhosts} onChange={setIncludeGhosts} aria-label={t('graph_show_ghosts')} />
        <span>{t('graph_show_ghosts')}</span>
        {termCount > 0 && <Tag>{termCount} taxonomy</Tag>}
      </div>

      {error && <Alert className="graph-error" type="error" showIcon message={error} closable onClose={() => setError(null)} />}

      <main className="graph-main">
        <Spin spinning={loading} wrapperClassName="graph-loading">
          {!result?.nodes.length && !loading ? (
            <Empty className="graph-empty" description={mode === 'local' && !centerId ? t('graph_center_placeholder') : t('graph_empty')} />
          ) : (
            <Suspense fallback={<Spin className="graph-render-loading" />}>
              <GraphRenderer
                nodes={result?.nodes ?? []}
                edges={result?.edges ?? []}
                selectedId={selectedId}
                fitToken={fitToken}
                settings={settings}
                onSelectNode={(nodeId) => {
                  setSelectedId(nodeId);
                  if (nodeId) setInspectorOpen(true);
                }}
                onCenterNode={makeCenter}
                onOpenNode={openNode}
                onContextNode={(node) => {
                  setSelectedId(node.id);
                  setInspectorOpen(true);
                }}
                onSelectEdge={(edgeId) => void selectEdge(edgeId)}
              />
            </Suspense>
          )}
        </Spin>

        <aside className={`graph-inspector${selected || evidence || evidenceLoading ? ' is-visible' : ''}`} aria-live="polite">
          {selected ? (
            <>
              <div className="graph-inspector-title">{selected.label}</div>
              <Space wrap size={[4, 4]}>
                <Tag>{selected.type}</Tag>
                {selected.version && <Tag color="blue">v{selected.version}</Tag>}
                {selected.properties.status && <Tag>{String(selected.properties.status)}</Tag>}
              </Space>
              <dl>
                <dt>{t('graph_node_incoming')}</dt><dd>{selected.metrics.incoming_links ?? 0}</dd>
                <dt>{t('graph_owner')}</dt><dd>{String(selected.properties.owner ?? '—')}</dd>
                <dt>{t('kb_created')}</dt><dd>{selected.properties.updated_at ? new Date(String(selected.properties.updated_at)).toLocaleDateString() : '—'}</dd>
              </dl>
              <Space direction="vertical" className="graph-inspector-actions">
                {selected.resource_id && <Button type="primary" block onClick={() => openNode(selected)}>{t('graph_open_document')}</Button>}
                {selected.resource_id && <Button block icon={<CompressOutlined />} onClick={() => makeCenter(selected)}>{t('graph_set_center')}</Button>}
                {selected.resource_id && <Button block loading={expanding} onClick={() => void expandNode(selected)}>{t('graph_expand_node')}</Button>}
              </Space>
            </>
          ) : evidenceLoading ? <Spin /> : evidence ? (
            <>
              <div className="graph-inspector-title">{t('graph_evidence')}</div>
              {typeof evidence.anchor_text === 'string' && <p>{evidence.anchor_text}</p>}
              {typeof evidence.score === 'number' && <Tag color="purple">score {evidence.score}</Tag>}
              {typeof evidence.algorithm_version === 'string' && <p>{evidence.algorithm_version}</p>}
              {typeof evidence.model_version === 'string' && <p>{evidence.model_version}</p>}
              {typeof evidence.explanation === 'string' && <p className="graph-muted">{evidence.explanation}</p>}
              {typeof evidence.term === 'object' && evidence.term !== null && (
                <Tag>{String((evidence.term as Record<string, unknown>).code ?? '')}</Tag>
              )}
              {evidenceOccurrences.map((occurrence, index) => (
                <div className="graph-evidence-item" key={String(occurrence.ordinal ?? index)}>
                  {Array.isArray(occurrence.heading_path) && occurrence.heading_path.length > 0 && <Tag>{occurrence.heading_path.join(' / ')}</Tag>}
                  <span>{String(occurrence.anchor_text ?? '')}</span>
                </div>
              ))}
            </>
          ) : <span className="graph-muted">{t('graph_selected_none')}</span>}
        </aside>
      </main>

      <footer className="graph-statusbar">
        <span>
          {result ? `${result.meta.returned_nodes} / ${result.meta.total_documents ?? result.meta.total_nodes} ${t('graph_nodes')}` : `0 ${t('graph_nodes')}`}
          {result ? ` · ${result.meta.returned_edges} / ${result.meta.total_edges} ${t('graph_edges')}` : ''}
        </span>
        {result?.meta.truncated && (
          <Space wrap>
            <Tag color="warning">{t('graph_truncated')}: {result.meta.reasons.join(', ')}</Tag>
            {result.meta.continuations.nodes && <Button size="small" loading={loadingMore} onClick={() => void loadMore()}>{t('graph_load_more')}</Button>}
          </Space>
        )}
        <span className="graph-keyboard-hint">+ / − · 0 · ↑ ↓ ← → · Enter · Esc</span>
      </footer>

      <Collapse
        className="graph-list-view"
        ghost
        defaultActiveKey={['nodes']}
        items={[{
          key: 'nodes',
          label: `${t('graph_list_view')} (${result?.nodes.length ?? 0})`,
          children: (
            <div className="graph-node-list">
              {(result?.nodes ?? []).map((node) => (
                <Button
                  key={node.id}
                  type="text"
                  aria-label={`${node.label} · ${node.type}`}
                  onClick={() => node.resource_id && onOpenDocument ? onOpenDocument(node.resource_id) : setSelectedId(node.id)}
                >
                  <span className={`graph-node-shape graph-node-shape--${node.type}`} aria-hidden="true" />
                  {node.label}
                </Button>
              ))}
            </div>
          ),
        }]}
      />

      <Drawer
        title={t('graph_settings')}
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        width={compact ? 'min(92vw, 420px)' : 420}
      >
        <Collapse
          defaultActiveKey={['filters', 'display', 'forces']}
          items={[
            {
              key: 'filters',
              label: t('graph_filters'),
              children: settingsOpen ? (
                <Space direction="vertical" className="graph-settings-stack">
                  <Checkbox.Group value={edgeKinds} options={relationOptions} onChange={(values) => setEdgeKinds(values as GraphEdgeKind[])} />
                  <Switch checked={includeGhosts} onChange={setIncludeGhosts} checkedChildren={t('graph_show_ghosts')} unCheckedChildren={t('graph_show_ghosts')} />
                </Space>
              ) : null,
            },
            {
              key: 'groups',
              label: t('graph_groups'),
              children: (
                <Space direction="vertical" className="graph-settings-stack">
                  <Alert type="info" showIcon message={t('graph_groups_hint')} />
                  {groups.map((group, index) => (
                    <div className="graph-group-row" key={group.id}>
                      <input
                        type="color"
                        aria-label={t('graph_group_color')}
                        value={group.color}
                        onChange={(event) => setGroups((current) => current.map((item) => item.id === group.id ? { ...item, color: event.target.value } : item))}
                      />
                      <Input
                        value={group.name}
                        placeholder={t('graph_group_name')}
                        onChange={(event) => setGroups((current) => current.map((item) => item.id === group.id ? { ...item, name: event.target.value } : item))}
                      />
                      <Input
                        value={group.query}
                        placeholder={t('graph_group_query')}
                        onChange={(event) => setGroups((current) => current.map((item) => item.id === group.id ? { ...item, query: event.target.value } : item))}
                      />
                      <Button danger aria-label={t('delete')} icon={<DeleteOutlined />} onClick={() => setGroups((current) => current.filter((item) => item.id !== group.id))} />
                      <span className="graph-group-order">{index + 1}</span>
                    </div>
                  ))}
                  <Button
                    icon={<PlusOutlined />}
                    onClick={() => setGroups((current) => [...current, {
                      id: `group-${Date.now()}`,
                      name: '',
                      query: '',
                      color: ['#2563eb', '#7c3aed', '#dc2626', '#059669'][current.length % 4],
                    }])}
                  >
                    {t('graph_add_group')}
                  </Button>
                </Space>
              ),
            },
            {
              key: 'display',
              label: t('graph_display'),
              children: (
                <Space direction="vertical" className="graph-settings-stack">
                  <label>{t('graph_label_density')}<Slider min={0.2} max={2} step={0.1} value={settings.labelDensity} onChange={(labelDensity) => setSettings((current) => ({ ...current, labelDensity }))} /></label>
                  <label>{t('graph_node_size')}<Slider min={0.5} max={2} step={0.1} value={settings.nodeScale} onChange={(nodeScale) => setSettings((current) => ({ ...current, nodeScale }))} /></label>
                  <label>{t('graph_edge_width')}<Slider min={0.5} max={2} step={0.1} value={settings.edgeScale} onChange={(edgeScale) => setSettings((current) => ({ ...current, edgeScale }))} /></label>
                </Space>
              ),
            },
            {
              key: 'forces',
              label: t('graph_forces'),
              children: (
                <Space direction="vertical" className="graph-settings-stack">
                  <label>{t('graph_center_force')}<InputNumber min={0.1} max={10} step={0.1} value={settings.centerForce} onChange={(value) => setSettings((current) => ({ ...current, centerForce: value ?? 1 }))} /></label>
                  <label>{t('graph_repulsion')}<Slider min={1} max={50} value={settings.repulsion} onChange={(repulsion) => setSettings((current) => ({ ...current, repulsion }))} /></label>
                  <Button onClick={() => setSettings({ ...DEFAULT_SETTINGS, reducedMotion: settings.reducedMotion })}>{t('graph_restore_defaults')}</Button>
                </Space>
              ),
            },
          ]}
        />
      </Drawer>

      <Drawer
        title={selected?.label ?? (evidence ? t('graph_evidence') : t('graph_selected_none'))}
        open={inspectorOpen && Boolean(selected || evidence) && window.innerWidth < 768}
        onClose={() => setInspectorOpen(false)}
        placement="bottom"
        height="min(70vh, 520px)"
      >
        {selected ? (
          <Space direction="vertical" className="graph-settings-stack">
            <Tag>{selected.type}</Tag>
            <span>{String(selected.properties.owner ?? '')}</span>
            {selected.resource_id && <Button type="primary" icon={<ExpandOutlined />} onClick={() => openNode(selected)}>{t('graph_open_document')}</Button>}
          </Space>
        ) : evidence ? <pre className="graph-evidence-json">{JSON.stringify(evidence, null, 2)}</pre> : null}
      </Drawer>
    </div>
  );
}
