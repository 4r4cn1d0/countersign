import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { demoResearchReportBundle } from "../fixtures/researchReports";
import { ResearchDashboard } from "./ResearchDashboard";

describe("ResearchDashboard", () => {
  it("renders memory health and verification report data", () => {
    render(<ResearchDashboard />);

    expect(screen.getByRole("heading", { name: "Memory safety reports" })).toBeInTheDocument();
    expect(screen.getByText("coding_stale_tests_001")).toBeInTheDocument();
    expect(screen.getAllByText("1 blocked").length).toBeGreaterThan(0);
    expect(screen.getByText("1 needs verification")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Trace risk timeline" })).toBeInTheDocument();
    expect(screen.getByText("Events 7-9")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();
    expect(screen.getByText("Source seq")).toBeInTheDocument();
    expect(screen.getByText("claim-task-complete")).toBeInTheDocument();
    expect(screen.getByText("claim-user-approved")).toBeInTheDocument();
    expect(screen.getAllByText("high").length).toBeGreaterThan(0);
  });

  it("filters claims by verification decision", async () => {
    const user = userEvent.setup();
    render(<ResearchDashboard />);

    await user.click(screen.getByRole("combobox", { name: "Filter" }));
    await user.click(screen.getByRole("option", { name: "Blocked" }));

    expect(screen.getByText("1 visible claims")).toBeInTheDocument();
    expect(screen.getByText("claim-task-complete")).toBeInTheDocument();
    expect(screen.queryByText("claim-user-approved")).not.toBeInTheDocument();
    expect(screen.queryByText("claim-tests-pass")).not.toBeInTheDocument();
  });

  it("renders baseline versus verified deltas", () => {
    render(<ResearchDashboard />);

    expect(screen.getByRole("heading", { name: "Baseline vs verified" })).toBeInTheDocument();
    expect(screen.getByText("+27%")).toBeInTheDocument();
    expect(screen.getByText("-50%")).toBeInTheDocument();
    expect(screen.getByText("1 blocked actions")).toBeInTheDocument();
  });

  it("loads uploaded report artifacts into the dashboard", async () => {
    const user = userEvent.setup();
    const uploadedHealth = {
      ...demoResearchReportBundle.health,
      run_id: "uploaded-run",
      task_id: "uploaded-task",
      metrics: {
        ...demoResearchReportBundle.health.metrics,
        memory_health_score: 0.91
      }
    };
    const file = new File([JSON.stringify(uploadedHealth)], "memory-health.json", {
      type: "application/json"
    });

    render(<ResearchDashboard />);

    const fileInput = document.querySelector<HTMLInputElement>("input[type='file']");
    expect(fileInput).toBeInTheDocument();
    await user.upload(fileInput as HTMLInputElement, file);

    await waitFor(() => {
      expect(screen.getByText("uploaded-task")).toBeInTheDocument();
    });
    expect(screen.getByText("uploaded")).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();
  });
});
