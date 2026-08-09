// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { vizApi, type GraphResponse } from '../../api/knowledge';
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


describe('KnowledgeGraphPanel graph workspace', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(vizApi.queryGraph).mockResolvedValue(response);
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
      occurrences: [{ ordinal: 0, anchor_text: 'Policy B', heading_path: ['Sources'] }],
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
  });
});
