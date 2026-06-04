# Dashboard

The dashboard is the inspection and demo layer. The research workflow should still work
from the terminal without the frontend, but the dashboard helps humans inspect traces and
reports.

## Current Role

The frontend supports:

- Session list and filtering.
- Execution graph visualization.
- Reasoning trace inspection.
- Tool-call monitoring.
- Research report views for memory health, claims, high-risk labels, and comparisons.

## Where It Fits

```text
research CLI artifacts
  -> JSON / Markdown reports
  -> dashboard fixtures or API-backed report loading
  -> human inspection
```

The dashboard should not be the source of truth for empirical claims. The source of truth
is the saved artifact bundle or matrix manifest.

## Demo Value

For a MATS-style demo, the dashboard should show:

- Baseline trace where the agent makes or approaches a bad memory claim.
- Verification-augmented trace where the bad claim is blocked or forced through fresh
  evidence.
- Memory health metrics before and after verification.
- Source provenance for claims.
- A clear list of blocked high-risk actions.

## Future Dashboard Work

Useful next upgrades:

- Load arbitrary local report bundles from the UI.
- Show the model matrix report as a sortable table.
- Link claim rows directly to source trace events.
- Show evidence freshness and provenance chain visualization.
- Compare baseline and verified graph timelines side by side.
