import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type FA2Layout from 'graphology-layout-forceatlas2/worker';
import type Sigma from 'sigma';

import type { GraphEdge, GraphNode } from '../../api/knowledge';


export interface GraphRenderSettings {
  labelDensity: number;
  nodeScale: number;
  edgeScale: number;
  centerForce: number;
  repulsion: number;
  reducedMotion: boolean;
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: string | null;
  fitToken: number;
  settings: GraphRenderSettings;
  onSelectNode: (nodeId: string | null) => void;
  onCenterNode: (node: GraphNode) => void;
  onOpenNode: (node: GraphNode) => void;
  onContextNode: (node: GraphNode) => void;
  onSelectEdge: (edgeId: string) => void;
}

function cssColor(element: HTMLElement, variable: string, fallback: string): string {
  return getComputedStyle(element).getPropertyValue(variable).trim() || fallback;
}

function fallbackPosition(index: number, total: number) {
  const angle = (index / Math.max(total, 1)) * Math.PI * 2;
  const radius = 12 + Math.sqrt(Math.max(total, 1)) * 2;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

function SvgFallback({ nodes, edges, selectedId, onSelectNode, onCenterNode, onSelectEdge }: Pick<Props, 'nodes' | 'edges' | 'selectedId' | 'onSelectNode' | 'onCenterNode' | 'onSelectEdge'>) {
  const visibleNodes = nodes.slice(0, 80);
  const positions = new Map(
    visibleNodes.map((node, index) => {
      const angle = (index / Math.max(visibleNodes.length, 1)) * Math.PI * 2;
      return [node.id, { x: 250 + Math.cos(angle) * 185, y: 190 + Math.sin(angle) * 145 }] as const;
    }),
  );
  return (
    <svg className="graph-svg-fallback" viewBox="0 0 500 380" role="img" aria-label="graph_aria_label">
      {edges.slice(0, 240).map((edge) => {
        const source = positions.get(edge.source);
        const target = positions.get(edge.target);
        if (!source || !target) return null;
        return (
          <line
            key={edge.id}
            x1={source.x}
            y1={source.y}
            x2={target.x}
            y2={target.y}
            className={`graph-svg-edge graph-svg-edge--${edge.provenance}`}
            onClick={() => onSelectEdge(edge.id)}
          />
        );
      })}
      {visibleNodes.map((node) => {
        const position = positions.get(node.id)!;
        return (
          <g
            key={node.id}
            transform={`translate(${position.x},${position.y})`}
            className={selectedId === node.id ? 'is-selected' : ''}
            onClick={() => onSelectNode(node.id)}
            onDoubleClick={() => onCenterNode(node)}
          >
            <circle r={node.type === 'term' ? 9 : 7} className={`graph-svg-node graph-svg-node--${node.type}`} />
            <text y="18" textAnchor="middle">{node.label.slice(0, 22)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function GraphRenderer(props: Props) {
  const {
    nodes,
    edges,
    fitToken,
    settings,
    onCenterNode,
    onContextNode,
    onOpenNode,
    onSelectNode,
    onSelectEdge,
    selectedId,
  } = props;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<Sigma | null>(null);
  const callbacksRef = useRef({ onCenterNode, onContextNode, onOpenNode, onSelectEdge, onSelectNode });
  const selectedRef = useRef<string | null>(selectedId);
  const neighborsRef = useRef<Set<string>>(new Set());
  const [fallback, setFallback] = useState(false);
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  useEffect(() => {
    callbacksRef.current = { onCenterNode, onContextNode, onOpenNode, onSelectEdge, onSelectNode };
  }, [onCenterNode, onContextNode, onOpenNode, onSelectEdge, onSelectNode]);

  useEffect(() => {
    selectedRef.current = selectedId;
    const neighbors = new Set<string>();
    if (selectedId) {
      neighbors.add(selectedId);
      edges.forEach((edge) => {
        if (edge.source === selectedId) neighbors.add(edge.target);
        if (edge.target === selectedId) neighbors.add(edge.source);
      });
    }
    neighborsRef.current = neighbors;
    rendererRef.current?.refresh();
  }, [edges, selectedId]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !nodes.length) return undefined;
    setFallback(false);
    if (typeof WebGL2RenderingContext === 'undefined') {
      setFallback(true);
      return undefined;
    }

    let cancelled = false;
    let layout: FA2Layout | null = null;
    let stopTimer: number | undefined;
    let renderer: Sigma | null = null;

    const setup = async () => {
      try {
        const [{ default: Graph }, { default: Layout }, { default: SigmaRenderer }, { EdgeArrowProgram }] = await Promise.all([
          import('graphology'),
          import('graphology-layout-forceatlas2/worker'),
          import('sigma'),
          import('sigma/rendering'),
        ]);
        if (cancelled) return;
        const graph = new Graph({ multi: true, type: 'mixed' });
        nodes.forEach((node, index) => {
      const position = fallbackPosition(index, nodes.length);
      const freshness = Number(node.properties.freshness ?? 0.5);
      const groupColor = typeof node.properties.group_color === 'string' ? node.properties.group_color : null;
      const color = groupColor ?? (node.type === 'term'
        ? cssColor(container, '--graph-node-mid', '#8b5cf6')
        : node.type === 'ghost'
          ? cssColor(container, '--color-text-tertiary', '#94a3b8')
          : freshness >= 0.7
            ? cssColor(container, '--graph-node-fresh', '#22d3ee')
            : freshness >= 0.4
              ? cssColor(container, '--graph-node-mid', '#3b82f6')
              : cssColor(container, '--graph-node-stale', '#f59e0b'));
      graph.addNode(node.id, {
        ...position,
        label: node.label,
        color,
        size: (5 + Math.min(node.metrics.incoming_links ?? 0, 8)) * settings.nodeScale,
        nodeKind: node.type,
      });
        });
        edges.forEach((edge) => {
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) return;
      const attributes = {
        size: Math.max(0.7, edge.weight) * settings.edgeScale,
        color: edge.provenance === 'explicit'
          ? cssColor(container, '--graph-edge-link', '#64748b')
          : edge.provenance === 'taxonomy'
            ? cssColor(container, '--graph-edge-term', '#8b5cf6')
            : cssColor(container, '--graph-edge-similar', '#94a3b8'),
        type: edge.directed ? 'arrow' : 'line',
        provenance: edge.provenance,
      };
      if (edge.directed) graph.addDirectedEdgeWithKey(edge.id, edge.source, edge.target, attributes);
      else graph.addUndirectedEdgeWithKey(edge.id, edge.source, edge.target, attributes);
        });

      renderer = new SigmaRenderer(graph, container, {
        allowInvalidContainer: true,
        edgeProgramClasses: { arrow: EdgeArrowProgram },
        labelDensity: settings.labelDensity,
        labelGridCellSize: 90,
        labelRenderedSizeThreshold: 8,
        hideEdgesOnMove: nodes.length > 120,
        hideLabelsOnMove: nodes.length > 80,
        minCameraRatio: 0.08,
        maxCameraRatio: 8,
        nodeReducer: (node, data) => {
          const selected = selectedRef.current;
          if (!selected) return data;
          if (node === selected) return { ...data, highlighted: true, forceLabel: true, zIndex: 2 };
          if (neighborsRef.current.has(node)) return { ...data, zIndex: 1 };
          return { ...data, color: '#94a3b8', hidden: false, zIndex: 0 };
        },
        edgeReducer: (edge, data) => {
          const selected = selectedRef.current;
          if (!selected) return data;
          const extremities = graph.extremities(edge);
          return extremities.includes(selected) ? { ...data, size: data.size * 1.5 } : { ...data, hidden: true };
        },
      });
      rendererRef.current = renderer;
      renderer.on('clickNode', ({ node }) => callbacksRef.current.onSelectNode(node));
      renderer.on('clickEdge', ({ edge }) => callbacksRef.current.onSelectEdge(edge));
      renderer.on('doubleClickNode', ({ node, preventSigmaDefault }) => {
        preventSigmaDefault();
        const item = nodeById.get(node);
        if (item) callbacksRef.current.onCenterNode(item);
      });
      renderer.on('rightClickNode', ({ node, preventSigmaDefault }) => {
        preventSigmaDefault();
        const item = nodeById.get(node);
        if (item) callbacksRef.current.onContextNode(item);
      });
      renderer.on('clickStage', () => callbacksRef.current.onSelectNode(null));

      let draggedNode: string | null = null;
      renderer.on('downNode', ({ node, event }) => {
        draggedNode = node;
        graph.setNodeAttribute(node, 'highlighted', true);
        renderer?.getCamera().disable();
        event.preventSigmaDefault();
      });
      renderer.getMouseCaptor().on('mousemovebody', (event) => {
        if (!draggedNode || !renderer) return;
        const position = renderer.viewportToGraph(event);
        graph.mergeNodeAttributes(draggedNode, { x: position.x, y: position.y });
        event.preventSigmaDefault();
      });
      renderer.getMouseCaptor().on('mouseup', () => {
        if (draggedNode) graph.removeNodeAttribute(draggedNode, 'highlighted');
        draggedNode = null;
        renderer?.getCamera().enable();
      });

      if (!settings.reducedMotion && nodes.length > 1) {
        layout = new Layout(graph, {
          settings: {
            barnesHutOptimize: true,
            gravity: settings.centerForce,
            scalingRatio: settings.repulsion,
            slowDown: 2,
            strongGravityMode: false,
          },
        });
        layout.start();
        stopTimer = window.setTimeout(() => layout?.stop(), 1800);
      }
      container.querySelectorAll('canvas').forEach((canvas) => {
        canvas.addEventListener('webglcontextlost', (event) => {
          event.preventDefault();
          setFallback(true);
        }, { once: true });
      });
      } catch {
        if (!cancelled) setFallback(true);
      }
    };
    void setup();
    return () => {
      cancelled = true;
      if (stopTimer) window.clearTimeout(stopTimer);
      layout?.kill();
      renderer?.kill();
      rendererRef.current = null;
    };
  }, [edges, nodeById, nodes, settings]);

  useEffect(() => {
    if (fitToken > 0) void rendererRef.current?.getCamera().animatedReset({ duration: settings.reducedMotion ? 0 : 250 });
  }, [fitToken, settings.reducedMotion]);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const renderer = rendererRef.current;
    if (!renderer) return;
    const camera = renderer.getCamera();
    const step = event.shiftKey ? 0.15 : 0.05;
    if (event.key === '+' || event.key === '=') void camera.animatedZoom();
    else if (event.key === '-') void camera.animatedUnzoom();
    else if (event.key === '0') void camera.animatedReset({ duration: settings.reducedMotion ? 0 : 250 });
    else if (event.key === 'ArrowLeft') camera.updateState((state) => ({ x: state.x - step * state.ratio }));
    else if (event.key === 'ArrowRight') camera.updateState((state) => ({ x: state.x + step * state.ratio }));
    else if (event.key === 'ArrowUp') camera.updateState((state) => ({ y: state.y - step * state.ratio }));
    else if (event.key === 'ArrowDown') camera.updateState((state) => ({ y: state.y + step * state.ratio }));
    else if (event.key === 'Enter' && selectedId) {
      const node = nodeById.get(selectedId);
      if (node) callbacksRef.current.onOpenNode(node);
    } else if (event.key === 'Escape') callbacksRef.current.onSelectNode(null);
    else return;
    event.preventDefault();
  };

  if (fallback) {
    return (
      <SvgFallback
        nodes={nodes}
        edges={edges}
        selectedId={selectedId}
        onSelectNode={onSelectNode}
        onCenterNode={onCenterNode}
        onSelectEdge={onSelectEdge}
      />
    );
  }
  return (
    <div
      ref={containerRef}
      className="graph-renderer"
      role="application"
      aria-label="graph_aria_label"
      tabIndex={0}
      onKeyDown={handleKeyDown}
    />
  );
}
