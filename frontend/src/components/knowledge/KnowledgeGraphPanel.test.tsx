// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  vizApi,
  type GraphPathResponse,
  type GraphResponse,
  type GraphScene,
} from '../../api/knowledge';
import { KnowledgeGraphPanel } from './KnowledgeGraphPanel';


vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../../api/knowledge', async () => {
  const actual = await vi.importActual<typeof import('../../api/knowledge')>('../../api/knowledge');
  return {
    ...actual,
    vizApi: {
      ...actual.vizApi,
      getGraph: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
      queryGraph: vi.fn(),
      getEvidence: vi.fn(),
      expandGraph: vi.fn(),
      findGraphPaths: vi.fn(),
      listScenes: vi.fn(),
      createScene: vi.fn(),
      updateScene: vi.fn(),
      deleteScene: vi.fn(),
      resolveScene: vi.fn(),
      copyScene: vi.fn(),
    },
  };
});


const response: GraphResponse = {
  schema_version: 'graph.response.v1',
  scope: { mode: 'local', center_id: 'doc:lineage-a', depth: 1, direction: 'both' },
  nodes: [
    {
      id: 'doc:lineage-a',
      type: 'document',
      label: 'Policy A',
      resource_id: 'resource-a',
      version: 2,
      properties: { status: 'active', freshness: 0.9, owner: 'Alice' },
      metrics: { incoming_links: 3 },
    },
    {
      id: 'doc:lineage-b',
      type: 'document',
      label: 'Policy B',
      resource_id: 'resource-b',
      version: 1,
      properties: { status: 'stale', freshness: 0.3, owner: 'Bob' },
      metrics: { incoming_links: 1 },
    },
  ],
  edges: [
    {
      id: 'link:1',
      kind: 'links_to',
      source: 'doc:lineage-a',
      target: 'doc:lineage-b',
      directed: true,
      weight: 1,
      provenance: 'explicit',
      evidence: { ref: 'link:1', summary: 'Policy B', count: 1 },
    },
  ],
  meta: {
    revision: 4,
    total_nodes: 5000,
    total_edges: 12000,
    returned_nodes: 2,
    returned_edges: 1,
    truncated: true,
    reasons: ['node_limit'],
    continuations: { nodes: 'next' },
    missing_node_ids: [],
  },
};

const pathResponse: GraphPathResponse = {
  schema_version: 'graph.path.response.v1',
  paths: [{ nodes: response.nodes, edges: response.edges }],
  meta: { ...response.meta, truncated: false, reasons: [], continuations: {} },
};

const sharedScene: GraphScene = {
  id: 'scene-shared',
  name: 'Approval investigation',
  visibility: 'workspace',
  owner_id: 'other-user',
  canonical_query: {
    schema_version: 'graph.query.v1',
    scope: { mode: 'local', center_id: 'resource-a', depth: 1, direction: 'both' },
    edge_kinds: ['links_to'],
  },
  layout: { hidden_node_ids: ['doc:hidden'] },
  resolved_versions: {},
  schema_version: 'graph.scene.v1',
  graph_revision: 4,
  revision: 1,
  created_at: '2026-08-09T00:00:00Z',
  updated_at: '2026-08-09T00:00:00Z',
  editable: false,
};
const privateScene: GraphScene = {
  ...sharedScene,
  id: 'scene-private',
  name: 'My investigation',
  visibility: 'private',
  owner_id: 'current-user',
  editable: true,
};
const nativeGetComputedStyle = window.getComputedStyle.bind(window);


describe('KnowledgeGraphPanel graph workspace', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element) => nativeGetComputedStyle(element));
    window.history.replaceState({}, '', '/');
    vi.mocked(vizApi.queryGraph).mockResolvedValue(response);
    vi.mocked(vizApi.expandGraph).mockResolvedValue(response);
    vi.mocked(vizApi.findGraphPaths).mockResolvedValue(pathResponse);
    vi.mocked(vizApi.listScenes).mockResolvedValue({ results: [] });
    vi.mocked(vizApi.resolveScene).mockResolvedValue({
      scene: sharedScene,
      graph: response,
      changes: { added: [], removed: [], updated: [] },
    });
    vi.mocked(vizApi.copyScene).mockResolvedValue({ ...sharedScene, id: 'scene-copy', visibility: 'private' });
  });

  it('opens a document-centered local graph with explicit links only', async () => {
    render(
      <KnowledgeGraphPanel
        dimensions={[]}
        initialCenterId="resource-a"
        compact
      />,
    );

    await waitFor(() => expect(vizApi.queryGraph).toHaveBeenCalledTimes(1));
    expect(vizApi.queryGraph).toHaveBeenCalledWith(expect.objectContaining({
      schema_version: 'graph.query.v1',
      scope: { mode: 'local', center_id: 'resource-a', depth: 1, direction: 'both' },
      edge_kinds: ['links_to'],
    }));
  });

  it('re-queries on relation changes and exposes a keyboard-readable list', async () => {
    const onOpenDocument = vi.fn();
    render(
      <KnowledgeGraphPanel
        dimensions={[]}
        initialCenterId="resource-a"
        onOpenDocument={onOpenDocument}
      />,
    );
    const nodeButton = await screen.findByRole('button', { name: /Policy A/ });

    fireEvent.click(screen.getByRole('checkbox', { name: 'graph_edge_term' }));
    await waitFor(() => expect(vizApi.queryGraph).toHaveBeenLastCalledWith(
      expect.objectContaining({ edge_kinds: ['links_to', 'tagged_with'] }),
    ));
    expect(screen.getByText(/2 \/ 5000/)).toBeTruthy();
    fireEvent.click(nodeButton);
    expect(onOpenDocument).toHaveBeenCalledWith('resource-a');
  });

  it('loads permission-scoped evidence when an edge is selected', async () => {
    vi.mocked(vizApi.getEvidence).mockResolvedValue({
      ref: 'link:1',
      kind: 'links_to',
      anchor_text: 'Policy B',
      occurrences: [{
        ordinal: 0,
        anchor_text: 'Policy B',
        heading_path: ['Sources'],
        snippet: 'The approval policy depends on [[Policy B]] for evidence.',
      }],
    });
    const { container } = render(<KnowledgeGraphPanel dimensions={[]} initialCenterId="resource-a" />);
    await screen.findByRole('button', { name: /Policy A/ });
    const edge = await waitFor(() => {
      const element = container.querySelector('.graph-svg-edge');
      expect(element).toBeTruthy();
      return element!;
    });

    fireEvent.click(edge);

    await waitFor(() => expect(vizApi.getEvidence).toHaveBeenCalledWith('link:1'));
    expect(await screen.findByText('Sources')).toBeTruthy();
    expect(screen.getByText(/approval policy depends/)).toBeTruthy();
  });

  it('paginates repeated relationship evidence without replacing prior occurrences', async () => {
    vi.mocked(vizApi.getEvidence)
      .mockResolvedValueOnce({
        ref: 'link:1',
        kind: 'links_to',
        occurrences: [{ ordinal: 0, anchor_text: 'first occurrence' }],
        pagination: { total: 2, offset: 0, limit: 1, next_offset: 1 },
      })
      .mockResolvedValueOnce({
        ref: 'link:1',
        kind: 'links_to',
        occurrences: [{ ordinal: 1, anchor_text: 'second occurrence' }],
        pagination: { total: 2, offset: 1, limit: 1, next_offset: null },
      });
    const { container } = render(<KnowledgeGraphPanel dimensions={[]} initialCenterId="resource-a" />);
    await screen.findByRole('button', { name: /Policy A/ });
    fireEvent.click(container.querySelector('.graph-svg-edge')!);

    fireEvent.click(await screen.findByRole('button', { name: 'Load more evidence' }));

    await waitFor(() => expect(vizApi.getEvidence).toHaveBeenLastCalledWith('link:1', { offset: 1, limit: 50 }));
    expect(screen.getByText('first occurrence')).toBeTruthy();
    expect(await screen.findByText('second occurrence')).toBeTruthy();
  });

  it('dismisses nodes and restores investigation state with undo and redo', async () => {
    render(<KnowledgeGraphPanel dimensions={[]} initialCenterId="resource-a" />);
    fireEvent.click(await screen.findByRole('button', { name: /Policy A/ }));

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss from scene' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /Policy A/ })).toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Undo investigation action' }));
    expect(await screen.findByRole('button', { name: /Policy A/ })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Redo investigation action' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /Policy A/ })).toBeNull());
  });

  it('finds up to three explainable paths without inferred edges by default', async () => {
    render(<KnowledgeGraphPanel dimensions={[]} initialCenterId="resource-a" />);
    fireEvent.click(await screen.findByRole('button', { name: /Policy A/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Use as path start' }));
    fireEvent.click(screen.getByRole('button', { name: /Policy B/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Find paths to this node' }));

    await waitFor(() => expect(vizApi.findGraphPaths).toHaveBeenCalledWith({
      schema_version: 'graph.path.v1',
      source_id: 'doc:lineage-a',
      target_id: 'doc:lineage-b',
      edge_kinds: ['links_to', 'tagged_with'],
      include_inferred: false,
      max_paths: 3,
      max_depth: 6,
    }));
    expect(await screen.findByText('Policy A → Policy B')).toBeTruthy();
  });

  it('runs deterministic team insight presets through the server query', async () => {
    render(<KnowledgeGraphPanel dimensions={[]} />);
    await screen.findByRole('button', { name: /Policy A/ });

    fireEvent.click(screen.getByRole('button', { name: 'Isolated documents' }));

    await waitFor(() => expect(vizApi.queryGraph).toHaveBeenLastCalledWith(
      expect.objectContaining({ insight_preset: 'isolated' }),
    ));
  });

  it('opens shared scenes through permission re-projection and copies before editing', async () => {
    vi.mocked(vizApi.listScenes).mockResolvedValue({ results: [sharedScene] });
    render(<KnowledgeGraphPanel dimensions={[]} initialCenterId="resource-a" />);
    fireEvent.click(screen.getByRole('button', { name: 'Investigation scenes' }));

    expect(await screen.findByText('Approval investigation')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Open scene Approval investigation' }));
    await waitFor(() => expect(vizApi.resolveScene).toHaveBeenCalledWith('scene-shared'));

    fireEvent.click(screen.getByRole('button', { name: 'Copy scene Approval investigation' }));
    await waitFor(() => expect(vizApi.copyScene).toHaveBeenCalledWith('scene-shared'));
  });

  it('updates an owned scene with the current investigation state', async () => {
    vi.mocked(vizApi.listScenes).mockResolvedValue({ results: [privateScene] });
    vi.mocked(vizApi.resolveScene).mockResolvedValue({
      scene: privateScene,
      graph: response,
      changes: { added: [], removed: [], updated: [] },
    });
    vi.mocked(vizApi.updateScene).mockResolvedValue({ ...privateScene, revision: 2 });
    render(<KnowledgeGraphPanel dimensions={[]} initialCenterId="resource-a" />);
    fireEvent.click(screen.getByRole('button', { name: 'Investigation scenes' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Open scene My investigation' }));

    fireEvent.click(await screen.findByRole('button', { name: 'Update current scene' }));

    await waitFor(() => expect(vizApi.updateScene).toHaveBeenCalledWith(
      'scene-private',
      expect.objectContaining({
        canonical_query: expect.objectContaining({ schema_version: 'graph.query.v1' }),
        layout: expect.objectContaining({ hidden_node_ids: ['doc:hidden'] }),
      }),
      1,
    ));
  });

  it('resolves a deep-linked scene with the current user permissions', async () => {
    window.history.replaceState({}, '', '/knowledge?graph_scene=scene-shared');
    render(<KnowledgeGraphPanel dimensions={[]} />);

    await waitFor(() => expect(vizApi.resolveScene).toHaveBeenCalledWith('scene-shared'));
    expect(await screen.findByRole('button', { name: /Policy A/ })).toBeTruthy();
  });
});
