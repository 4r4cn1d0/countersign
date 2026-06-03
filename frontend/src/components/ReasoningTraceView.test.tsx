import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TraceEvent } from "../types/observability";
import { ReasoningTraceView } from "./ReasoningTraceView";

const events: TraceEvent[] = [
  {
    event_id: "reason-1",
    session_id: "session-1",
    event_type: "reasoning_step",
    timestamp: "2026-06-03T00:00:00Z",
    sequence_number: 1,
    duration_ms: 100,
    status: "completed",
    event_data: {
      prompt: "Classify the incident",
      response: "{\"answer\":\"database latency\",\"severity\":\"high\"}",
      model: "gpt-4.1",
      temperature: 0.2,
      input_tokens: 18,
      output_tokens: 12,
      influence_markers: ["database latency"],
      generation_parameters: {
        top_p: 0.9
      }
    }
  },
  {
    event_id: "tool-1",
    session_id: "session-1",
    event_type: "tool_call",
    timestamp: "2026-06-03T00:00:01Z",
    sequence_number: 2,
    event_data: {}
  }
];

describe("ReasoningTraceView", () => {
  it("renders prompt, response, token counts, and generation parameters", () => {
    render(<ReasoningTraceView events={events} />);

    fireEvent.click(screen.getByText("Call 1"));

    expect(screen.getByText("Classify the incident")).toBeInTheDocument();
    expect(screen.getByText("gpt-4.1")).toBeInTheDocument();
    expect(screen.getByText("18 in")).toBeInTheDocument();
    expect(screen.getByText("12 out")).toBeInTheDocument();
    expect(screen.getByText(/top_p/)).toBeInTheDocument();
  });

  it("formats structured JSON responses and highlights influence markers", () => {
    render(<ReasoningTraceView events={events} />);
    fireEvent.click(screen.getByText("Call 1"));

    const response = screen.getByText((_, element) =>
      element?.tagName.toLowerCase() === "pre" &&
      element.textContent?.includes('"answer": "database latency"') === true
    );

    expect(response).toHaveClass("syntax-json");
    expect(screen.getByText("database latency")).toBeInTheDocument();
  });

  it("handles sessions without reasoning events", () => {
    render(<ReasoningTraceView events={[events[1]]} />);
    expect(screen.getByText("No reasoning events recorded for this session.")).toBeInTheDocument();
  });
});
