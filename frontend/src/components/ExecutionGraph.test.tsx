import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ExecutionGraphResponse } from "../types/observability";
import { ExecutionGraph } from "./ExecutionGraph";

const graph: ExecutionGraphResponse = {
  session_id: "session-1",
  nodes: [
    {
      event_id: "event-1",
      event_type: "reasoning_step",
      label: "Reasoning: gpt-4",
      duration_ms: 120,
      status: "completed",
      timestamp: "2026-06-03T00:00:00Z"
    },
    {
      event_id: "event-2",
      event_type: "tool_call",
      label: "Tool: search",
      duration_ms: 900,
      status: "error",
      timestamp: "2026-06-03T00:00:01Z"
    }
  ],
  edges: [
    {
      source_event_id: "event-1",
      target_event_id: "event-2"
    }
  ]
};

describe("ExecutionGraph", () => {
  it("renders graph nodes, edge timing, and legend", () => {
    render(<ExecutionGraph graph={graph} />);

    expect(screen.getByLabelText("Execution graph")).toBeInTheDocument();
    expect(screen.getByText("reasoning step")).toBeInTheDocument();
    expect(screen.getByText("tool call")).toBeInTheDocument();
    expect(screen.getAllByText("900 ms").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("graph-node")).toHaveLength(2);
  });

  it("selects nodes and shows tooltip details", () => {
    const onSelectNode = vi.fn();
    render(<ExecutionGraph graph={graph} onSelectNode={onSelectNode} />);

    const nodes = screen.getAllByTestId("graph-node");
    fireEvent.mouseEnter(nodes[0]);
    expect(screen.getAllByText("Reasoning: gpt-4").length).toBeGreaterThan(0);

    fireEvent.click(nodes[1]);
    expect(onSelectNode).toHaveBeenCalledWith(expect.objectContaining({ event_id: "event-2" }));
  });

  it("adds live events incrementally", () => {
    render(
      <ExecutionGraph
        graph={graph}
        liveEvents={[
          {
            event_id: "event-3",
            session_id: "session-1",
            event_type: "memory_access",
            timestamp: "2026-06-03T00:00:02Z",
            sequence_number: 3,
            parent_event_id: "event-2",
            duration_ms: 44,
            status: "completed",
            event_data: { memory_type: "vector" }
          }
        ]}
      />
    );

    expect(screen.getAllByTestId("graph-node")).toHaveLength(3);
    expect(screen.getByText("memory access")).toBeInTheDocument();
  });
});
