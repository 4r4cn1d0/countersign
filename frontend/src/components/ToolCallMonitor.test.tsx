import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TraceEvent } from "../types/observability";
import { ToolCallMonitor } from "./ToolCallMonitor";

const events: TraceEvent[] = [
  {
    event_id: "tool-1",
    session_id: "session-1",
    event_type: "tool_call",
    timestamp: "2026-06-03T00:00:01Z",
    sequence_number: 1,
    duration_ms: 1250,
    status: "completed",
    event_data: {
      tool_name: "web_search",
      tool_type: "api",
      inputs: { query: "latency" },
      outputs: { result: "docs" }
    }
  },
  {
    event_id: "tool-2",
    session_id: "session-1",
    event_type: "tool_call",
    timestamp: "2026-06-03T00:00:02Z",
    sequence_number: 2,
    duration_ms: 6400,
    status: "failed",
    error_type: "TimeoutError",
    error_message: "Search timed out",
    event_data: {
      tool_name: "web_search",
      tool_type: "api",
      inputs: { query: "slow endpoint" },
      outputs: null,
      stack_trace: "Traceback: timeout",
      error: {
        context: {
          endpoint: "/search",
          attempt: 2
        }
      }
    }
  },
  {
    event_id: "tool-3",
    session_id: "session-1",
    event_type: "tool_call",
    timestamp: "2026-06-03T00:00:03Z",
    sequence_number: 3,
    duration_ms: 800,
    status: "completed",
    event_data: {
      tool_name: "database_query",
      tool_type: "database",
      inputs: { sql: "select 1" },
      outputs: { rows: 1 }
    }
  },
  {
    event_id: "reason-1",
    session_id: "session-1",
    event_type: "reasoning_step",
    timestamp: "2026-06-03T00:00:04Z",
    sequence_number: 4,
    event_data: {}
  }
];

describe("ToolCallMonitor", () => {
  it("renders chronological tool calls with inputs, outputs, status, and slow flag", () => {
    render(<ToolCallMonitor events={events} />);

    expect(screen.getByText("3 matching calls")).toBeInTheDocument();
    expect(screen.getByText("Total calls")).toBeInTheDocument();
    expect(screen.getByText("Failure rate")).toBeInTheDocument();
    expect(screen.getAllByText("web_search").length).toBeGreaterThan(0);
    expect(screen.getAllByText("database_query").length).toBeGreaterThan(0);
    expect(screen.getByText(/latency/)).toBeInTheDocument();
    expect(screen.getByText(/docs/)).toBeInTheDocument();
    expect(screen.getByText("slow")).toBeInTheDocument();
  });

  it("filters by tool name, status, and duration range", () => {
    render(<ToolCallMonitor events={events} />);

    fireEvent.change(screen.getByLabelText("Tool"), { target: { value: "database" } });
    expect(screen.getByText("1 matching calls")).toBeInTheDocument();
    expect(screen.getAllByText("database_query").length).toBeGreaterThan(0);
    expect(screen.queryByText("TimeoutError")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Tool"), { target: { value: "" } });
    fireEvent.mouseDown(screen.getByLabelText("Status"));
    fireEvent.click(screen.getByRole("option", { name: "Failed" }));
    expect(screen.getByText("1 matching calls")).toBeInTheDocument();
    expect(screen.getByText("TimeoutError")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Min duration"), { target: { value: "5000" } });
    fireEvent.change(screen.getByLabelText("Max duration"), { target: { value: "7000" } });
    expect(screen.getByText("1 matching calls")).toBeInTheDocument();
    expect(screen.getByText("Search timed out")).toBeInTheDocument();
  });

  it("calculates aggregate and per-tool statistics", () => {
    render(<ToolCallMonitor events={events} />);

    const statTiles = screen.getAllByText("3");
    expect(statTiles.length).toBeGreaterThan(0);
    expect(screen.getByText("33%")).toBeInTheDocument();
    expect(screen.getByText(/2 calls \/ 1 failed/)).toBeInTheDocument();
    expect(screen.getByText(/1 calls \/ 0 failed/)).toBeInTheDocument();
  });

  it("shows failed tool error details, stack trace, and execution context", () => {
    render(<ToolCallMonitor events={events} />);

    const errorRow = screen.getByText("TimeoutError").closest(".tool-error");
    expect(errorRow).not.toBeNull();
    expect(within(errorRow as HTMLElement).getByText("Search timed out")).toBeInTheDocument();
    expect(within(errorRow as HTMLElement).getByText("Traceback: timeout")).toBeInTheDocument();
    expect(within(errorRow as HTMLElement).getByText(/endpoint/)).toBeInTheDocument();
  });
});
