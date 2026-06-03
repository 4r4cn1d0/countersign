import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import { Box, Chip, Typography } from "@mui/material";
import type {
  ExecutionGraphEdge,
  ExecutionGraphNode,
  ExecutionGraphResponse,
  TraceEvent
} from "../types/observability";
import { eventLabel, formatDuration } from "../utils/format";

interface ExecutionGraphProps {
  graph: ExecutionGraphResponse;
  liveEvents?: TraceEvent[];
  selectedNodeId?: string | null;
  onSelectNode?: (node: ExecutionGraphNode) => void;
}

const emptyEvents: TraceEvent[] = [];

type LayoutNode = ExecutionGraphNode & {
  x: number;
  y: number;
  live?: boolean;
};

type LayoutEdge = {
  source: LayoutNode;
  target: LayoutNode;
};

const eventColors: Record<string, string> = {
  reasoning_step: "#2f6fed",
  tool_call: "#0f8a77",
  memory_access: "#b06b00",
  decision_point: "#8b3fbf",
  planning_phase: "#5f6b7a",
  custom_metric: "#5a7d25",
  annotation: "#9b4c58"
};

function eventToNode(event: TraceEvent): ExecutionGraphNode {
  return {
    event_id: event.event_id,
    event_type: event.event_type,
    label: eventLabel(event),
    duration_ms: event.duration_ms,
    status: event.status,
    timestamp: event.timestamp
  };
}

function eventToEdge(event: TraceEvent): ExecutionGraphEdge | null {
  if (!event.parent_event_id) {
    return null;
  }
  return {
    source_event_id: event.parent_event_id,
    target_event_id: event.event_id
  };
}

export function ExecutionGraph({
  graph,
  liveEvents = emptyEvents,
  selectedNodeId,
  onSelectNode
}: ExecutionGraphProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [nodes, setNodes] = useState<LayoutNode[]>([]);
  const [edges, setEdges] = useState<LayoutEdge[]>([]);
  const [transform, setTransform] = useState("translate(0,0) scale(1)");
  const [tooltipNode, setTooltipNode] = useState<LayoutNode | null>(null);

  const merged = useMemo(() => {
    const nodeMap = new Map<string, ExecutionGraphNode & { live?: boolean }>();
    graph.nodes.forEach((node) => nodeMap.set(node.event_id, node));
    liveEvents.forEach((event) => nodeMap.set(event.event_id, { ...eventToNode(event), live: true }));

    const edgeMap = new Map<string, ExecutionGraphEdge>();
    graph.edges.forEach((edge) => edgeMap.set(`${edge.source_event_id}:${edge.target_event_id}`, edge));
    liveEvents.forEach((event) => {
      const edge = eventToEdge(event);
      if (edge) {
        edgeMap.set(`${edge.source_event_id}:${edge.target_event_id}`, edge);
      }
    });

    return {
      nodes: Array.from(nodeMap.values()),
      edges: Array.from(edgeMap.values())
    };
  }, [graph.edges, graph.nodes, liveEvents]);

  const errorAndDependentIds = useMemo(() => {
    const errorIds = new Set(merged.nodes.filter((node) => node.status === "error" || node.status === "failed").map((node) => node.event_id));
    let changed = true;
    while (changed) {
      changed = false;
      for (const edge of merged.edges) {
        if (errorIds.has(edge.source_event_id) && !errorIds.has(edge.target_event_id)) {
          errorIds.add(edge.target_event_id);
          changed = true;
        }
      }
    }
    return errorIds;
  }, [merged.edges, merged.nodes]);

  useEffect(() => {
    const width = 960;
    const height = 560;
    const layoutNodes: LayoutNode[] = merged.nodes.map((node, index) => ({
      ...node,
      x: 120 + (index % 6) * 130,
      y: 120 + Math.floor(index / 6) * 110
    }));

    const nodeById = new Map(layoutNodes.map((node) => [node.event_id, node]));
    const layoutEdges: LayoutEdge[] = merged.edges
      .map((edge) => {
        const source = nodeById.get(edge.source_event_id);
        const target = nodeById.get(edge.target_event_id);
        return source && target ? { source, target } : null;
      })
      .filter((edge): edge is LayoutEdge => edge !== null);

    for (let iteration = 0; iteration < 140; iteration += 1) {
      for (let i = 0; i < layoutNodes.length; i += 1) {
        for (let j = i + 1; j < layoutNodes.length; j += 1) {
          const a = layoutNodes[i];
          const b = layoutNodes[j];
          const dx = a.x - b.x || 0.01;
          const dy = a.y - b.y || 0.01;
          const distance = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = Math.min(1300 / (distance * distance), 2);
          const xForce = (dx / distance) * force;
          const yForce = (dy / distance) * force;
          a.x += xForce;
          a.y += yForce;
          b.x -= xForce;
          b.y -= yForce;
        }
      }

      for (const edge of layoutEdges) {
        const dx = edge.target.x - edge.source.x;
        const dy = edge.target.y - edge.source.y;
        const distance = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const force = (distance - 130) * 0.018;
        const xForce = (dx / distance) * force;
        const yForce = (dy / distance) * force;
        edge.source.x += xForce;
        edge.source.y += yForce;
        edge.target.x -= xForce;
        edge.target.y -= yForce;
      }

      for (const node of layoutNodes) {
        node.x += (width / 2 - node.x) * 0.006;
        node.y += (height / 2 - node.y) * 0.006;
        node.x = Math.max(70, Math.min(width - 70, node.x));
        node.y = Math.max(70, Math.min(height - 70, node.y));
      }
    }

    setNodes([...layoutNodes]);
    setEdges([...layoutEdges]);
  }, [merged.edges, merged.nodes]);

  useEffect(() => {
    if (!svgRef.current) {
      return undefined;
    }
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.35, 3])
      .on("zoom", (event) => setTransform(event.transform.toString()));

    d3.select(svgRef.current).call(zoom);
    return () => {
      d3.select(svgRef.current).on(".zoom", null);
    };
  }, []);

  return (
    <Box className="graph-shell">
      <Box className="graph-toolbar">
        <Typography component="h2" variant="h6">
          Execution graph
        </Typography>
        <Box className="legend-row">
          {Object.entries(eventColors).slice(0, 5).map(([type, color]) => (
            <Chip
              key={type}
              label={type.replaceAll("_", " ")}
              size="small"
              sx={{ borderColor: color, color }}
              variant="outlined"
            />
          ))}
        </Box>
      </Box>
      <Box className="graph-canvas">
        <svg aria-label="Execution graph" className="graph-svg" ref={svgRef} viewBox="0 0 960 560">
          <defs>
            <marker id="arrow" markerHeight="7" markerWidth="7" orient="auto" refX="7" refY="3.5">
              <path d="M0,0 L7,3.5 L0,7 Z" fill="#8b95a3" />
            </marker>
          </defs>
          <g transform={transform}>
            {edges.map((edge) => {
              const isErrorPath = errorAndDependentIds.has(edge.source.event_id) && errorAndDependentIds.has(edge.target.event_id);
              return (
                <g key={`${edge.source.event_id}:${edge.target.event_id}`}>
                  <line
                    markerEnd="url(#arrow)"
                    stroke={isErrorPath ? "#c83349" : "#9aa5b1"}
                    strokeWidth={isErrorPath ? 2.5 : 1.5}
                    x1={edge.source.x}
                    x2={edge.target.x}
                    y1={edge.source.y}
                    y2={edge.target.y}
                  />
                  <text
                    className="edge-label"
                    x={(edge.source.x + edge.target.x) / 2}
                    y={(edge.source.y + edge.target.y) / 2 - 6}
                  >
                    {formatDuration(edge.target.duration_ms)}
                  </text>
                </g>
              );
            })}
            {nodes.map((node) => {
              const failed = errorAndDependentIds.has(node.event_id);
              const selected = selectedNodeId === node.event_id;
              const color = failed ? "#c83349" : eventColors[node.event_type] ?? "#617084";
              return (
                <g
                  className={node.live ? "graph-node graph-node-live" : "graph-node"}
                  data-testid="graph-node"
                  key={node.event_id}
                  onClick={() => onSelectNode?.(node)}
                  onMouseEnter={() => setTooltipNode(node)}
                  onMouseLeave={() => setTooltipNode(null)}
                  role="button"
                  tabIndex={0}
                  transform={`translate(${node.x}, ${node.y})`}
                >
                  <circle
                    fill={selected ? "#ffffff" : color}
                    r={selected ? 34 : 30}
                    stroke={color}
                    strokeWidth={selected ? 4 : 2}
                  />
                  <text className="node-label" dy="-0.15em" textAnchor="middle">
                    {node.label.length > 16 ? `${node.label.slice(0, 15)}...` : node.label}
                  </text>
                  <text className="node-duration" dy="1.25em" textAnchor="middle">
                    {formatDuration(node.duration_ms)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
        {tooltipNode ? (
          <Box className="graph-tooltip">
            <Typography variant="subtitle2">{tooltipNode.label}</Typography>
            <Typography color="text.secondary" variant="caption">
              {tooltipNode.event_type.replaceAll("_", " ")} / {formatDuration(tooltipNode.duration_ms)}
            </Typography>
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
