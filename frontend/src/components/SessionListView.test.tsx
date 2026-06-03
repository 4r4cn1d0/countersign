import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Session } from "../types/observability";
import { SessionListView } from "./SessionListView";

const sessions: Session[] = [
  {
    session_id: "session-1",
    user_id: "user-1",
    agent_type: "planner",
    goal: "Investigate latency spike",
    status: "completed",
    created_at: "2026-06-03T00:00:00Z",
    completed_at: "2026-06-03T00:01:00Z",
    duration_ms: 61000,
    total_reasoning_steps: 3,
    total_tool_calls: 2,
    total_memory_accesses: 1,
    total_tokens: 1200,
    total_cost: 0.034,
    error_count: 0,
    metadata: null,
    tags: ["prod"],
    coordination_id: null
  },
  {
    session_id: "session-2",
    user_id: "user-1",
    agent_type: "researcher",
    goal: "Review failed job",
    status: "failed",
    created_at: "2026-06-03T01:00:00Z",
    completed_at: null,
    duration_ms: 8000,
    total_reasoning_steps: 1,
    total_tool_calls: 1,
    total_memory_accesses: 0,
    total_tokens: 300,
    total_cost: 0.006,
    error_count: 1,
    metadata: null,
    tags: ["ci"],
    coordination_id: null
  }
];

function createClient() {
  return {
    listSessions: vi.fn().mockResolvedValue({
      sessions,
      total: sessions.length,
      limit: 10,
      offset: 0,
      has_more: false
    }),
    searchSessions: vi.fn().mockResolvedValue({
      sessions: [sessions[0]],
      total: 1,
      limit: 10,
      offset: 0,
      has_more: false
    })
  };
}

describe("SessionListView", () => {
  it("renders sessions with filtering metadata", async () => {
    const client = createClient();
    render(<SessionListView client={client} />);

    expect(await screen.findByText("Investigate latency spike")).toBeInTheDocument();
    expect(screen.getByText("Review failed job")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(client.listSessions).toHaveBeenCalledWith({
      limit: 10,
      offset: 0,
      sort: "created_at:desc"
    });
  });

  it("calls full-text search and highlights matching text", async () => {
    const client = createClient();
    render(<SessionListView client={client} />);
    await screen.findByText("Investigate latency spike");

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "latency" } });

    await waitFor(() => {
      expect(client.searchSessions).toHaveBeenCalledWith(expect.objectContaining({
        query: "latency",
        limit: 10,
        offset: 0
      }));
    });
    expect(await screen.findByText("latency")).toBeInTheDocument();
  });

  it("sends duration range filters to search", async () => {
    const client = createClient();
    render(<SessionListView client={client} />);
    await screen.findByText("Investigate latency spike");

    fireEvent.change(screen.getByLabelText("Min duration"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Max duration"), { target: { value: "5000" } });

    await waitFor(() => {
      expect(client.searchSessions).toHaveBeenCalledWith(expect.objectContaining({
        filters: expect.objectContaining({
          duration_range: {
            min: 1000,
            max: 5000
          }
        })
      }));
    });
  });

  it("selects a session row", async () => {
    const client = createClient();
    const onSelectSession = vi.fn();
    render(<SessionListView client={client} onSelectSession={onSelectSession} />);

    fireEvent.click(await screen.findByText("Investigate latency spike"));
    expect(onSelectSession).toHaveBeenCalledWith(sessions[0]);
  });
});
