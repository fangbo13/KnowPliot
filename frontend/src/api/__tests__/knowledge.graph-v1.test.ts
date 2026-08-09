import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { vizApi, type GraphQueryRequest } from '../knowledge';


describe('typed graph workspace API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('posts the complete local graph semantics instead of hiding edges client-side', async () => {
    const response = {
      schema_version: 'graph.response.v1' as const,
      scope: { mode: 'local' as const, center_id: 'doc:lineage', depth: 2, direction: 'both' as const },
      nodes: [],
      edges: [],
      meta: {
        revision: 7,
        total_nodes: 0,
        total_edges: 0,
        returned_nodes: 0,
        returned_edges: 0,
        truncated: false,
        reasons: [],
        continuations: {},
        missing_node_ids: [],
      },
    };
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: response });
    const request: GraphQueryRequest = {
      schema_version: 'graph.query.v1',
      scope: { mode: 'local', center_id: 'resource-id', depth: 2, direction: 'both' },
      edge_kinds: ['links_to'],
      include_ghosts: true,
      query: 'tag:audit',
      limits: { nodes: 300, edges: 1500 },
    };

    await vizApi.queryGraph(request);

    expect(post).toHaveBeenCalledWith('/documents/graph/query/', request);
  });

  it('exposes typed explainable-path and scene resolution calls', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { paths: [] } });

    await vizApi.findGraphPaths({
      schema_version: 'graph.path.v1',
      source_id: 'doc:a',
      target_id: 'doc:b',
      edge_kinds: ['links_to', 'tagged_with'],
      max_paths: 3,
    });
    await vizApi.resolveScene('scene-id');

    expect(post).toHaveBeenNthCalledWith(1, '/documents/graph/path/', expect.objectContaining({ max_paths: 3 }));
    expect(post).toHaveBeenNthCalledWith(2, '/documents/graph/scenes/scene-id/resolve/', {});
  });
});
