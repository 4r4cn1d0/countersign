import MockAdapter from "axios-mock-adapter";
import { describe, expect, it } from "vitest";
import { AgentObserverApiClient } from "./client";

const listPayload = {
  sessions: [],
  total: 0,
  limit: 10,
  offset: 0,
  has_more: false
};

describe("AgentObserverApiClient", () => {
  it("adds bearer authentication and lists sessions", async () => {
    const client = new AgentObserverApiClient({
      baseURL: "http://api.test/api/v1",
      tokenProvider: () => "test-token",
      maxRetries: 0
    });
    const mock = new MockAdapter(client.axios);

    mock.onGet("/sessions").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer test-token");
      expect(config.params).toEqual({ limit: 10, offset: 0, sort: "created_at:desc" });
      return [200, listPayload];
    });

    await expect(client.listSessions({ limit: 10, offset: 0, sort: "created_at:desc" })).resolves.toEqual(listPayload);
  });

  it("posts advanced search filters", async () => {
    const client = new AgentObserverApiClient({
      baseURL: "http://api.test/api/v1",
      tokenProvider: () => null,
      maxRetries: 0
    });
    const mock = new MockAdapter(client.axios);

    mock.onPost("/sessions/search").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({
        query: "latency",
        filters: {
          status: ["completed"],
          tags: ["prod"]
        },
        limit: 25,
        offset: 0
      });
      return [200, listPayload];
    });

    await client.searchSessions({
      query: "latency",
      filters: {
        status: ["completed"],
        tags: ["prod"]
      },
      limit: 25,
      offset: 0
    });
  });

  it("posts research runs for memory health reports", async () => {
    const client = new AgentObserverApiClient({
      baseURL: "http://api.test/api/v1",
      tokenProvider: () => null,
      maxRetries: 0
    });
    const mock = new MockAdapter(client.axios);

    mock.onPost("/research/memory-health").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({
        run: {
          run_id: "demo-run",
          events: []
        },
        task: {
          task_id: "demo-task"
        }
      });
      return [200, {
        schema_version: "agent-memory-health/v0.1",
        run_id: "demo-run",
        task_id: "demo-task",
        trace_event_count: 0
      }];
    });

    await expect(client.createMemoryHealthReport({
      run: {
        run_id: "demo-run",
        events: []
      },
      task: {
        task_id: "demo-task"
      }
    })).resolves.toMatchObject({
      schema_version: "agent-memory-health/v0.1",
      task_id: "demo-task"
    });
  });

  it("retries retryable failures", async () => {
    const client = new AgentObserverApiClient({
      baseURL: "http://api.test/api/v1",
      tokenProvider: () => null,
      maxRetries: 1,
      retryDelayMs: 1
    });
    const mock = new MockAdapter(client.axios);

    mock.onGet("/metrics/aggregate").replyOnce(503, {}).onGet("/metrics/aggregate").reply(200, {
      time_period_start: "2026-06-01T00:00:00",
      time_period_end: "2026-06-03T00:00:00",
      total_sessions: 1,
      completed_sessions: 1,
      failed_sessions: 0,
      success_rate: 1,
      avg_duration_ms: 100,
      median_duration_ms: 100,
      p95_duration_ms: 100,
      total_tokens_used: 10,
      avg_tokens_per_session: 10,
      total_cost: 0.01,
      avg_cost_per_session: 0.01,
      total_reasoning_steps: 1,
      avg_reasoning_steps_per_session: 1,
      total_tool_calls: 0,
      avg_tool_calls_per_session: 0,
      error_count: 0
    });

    await expect(client.getAggregateMetrics()).resolves.toMatchObject({ total_sessions: 1 });
  });
});
