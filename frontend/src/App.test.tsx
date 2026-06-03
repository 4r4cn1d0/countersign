import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api/client", () => ({
  apiClient: {
    listSessions: vi.fn().mockResolvedValue({
      sessions: [],
      total: 0,
      limit: 10,
      offset: 0,
      has_more: false
    }),
    searchSessions: vi.fn(),
    getGraph: vi.fn(),
    getTrace: vi.fn()
  }
}));

vi.mock("./api/websocket", () => ({
  ObservabilityWebSocketClient: vi.fn().mockImplementation(() => ({
    connect: vi.fn(),
    close: vi.fn(),
    subscribe: vi.fn(),
    onMessage: vi.fn(() => vi.fn())
  }))
}));

describe("App", () => {
  it("renders the dashboard shell", async () => {
    render(<App />);

    expect(screen.getByText("Agent Observer")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Sessions" })).toBeInTheDocument();
  });

  it("routes to the research dashboard", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("tab", { name: "Research" }));

    expect(await screen.findByRole("heading", { name: "Memory safety reports" })).toBeInTheDocument();
    expect(screen.getByText("coding_stale_tests_001")).toBeInTheDocument();
  });
});
