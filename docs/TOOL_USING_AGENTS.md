# Tool-Using Agents

The current LangGraph implementation is real external framework execution, but it is a
bounded benchmark graph. To make the demo stronger, the next phase should turn it into a
full tool-using agent that can perform long-horizon work and be verified while it acts.

## Current State

The current LangGraph graph executes these nodes:

- `receive_goal`
- `load_memory`
- `call_model`
- `emit_trace`

That is enough to test model-authored memory claims against compressed context, but it is
not yet enough to claim the system evaluates autonomous coding or research agents.

## Target Agent Graph

The next LangGraph graph should look like this:

```text
receive_goal
  -> retrieve_memory
  -> plan_next_step
  -> choose_tool
  -> execute_tool
  -> ingest_observation
  -> update_memory
  -> verify_high_risk_claims
  -> decide_continue_or_finish
```

The graph should loop until the task budget is exhausted, the agent finishes with verified
evidence, or verification blocks a high-risk action.

## Required Tools

Minimum tool set for coding tasks:

- `read_file(path)`
- `write_file(path, content)` or patch-based editing
- `list_files(glob)`
- `run_shell(command, cwd, timeout)`
- `run_tests(command, cwd, timeout)`
- `inspect_git_status()`

Minimum tool set for research and non-coding tasks:

- `fetch_source(url_or_path)`
- `search_sources(query)`
- `quote_source(source_id, span)`
- `extract_table_or_data(source_id)`
- `run_analysis_script(code_or_command)`
- `write_report(path, content)`

Every tool result must become a trace event with:

- Tool name.
- Input.
- Output summary.
- Full output path or captured text where appropriate.
- Status and error.
- Timestamp or sequence number.
- Source type.
- Source event IDs.

## Evidence Ledger

The core upgrade is an evidence ledger. The agent should not only remember "tests passed"
or "source supports claim"; it should store the exact evidence event.

Ledger entries should include:

- Evidence ID.
- Source type: `tool_output`, `file_state`, `retrieved_source`, `user_instruction`,
  `model_response`, or `summary`.
- Event ID.
- Timestamp or sequence number.
- Freshness rules.
- Claims supported by this evidence.
- Claims contradicted by this evidence.

## Verification Gates

Verification should run before high-risk actions:

- Claiming tests pass.
- Claiming a task is complete.
- Claiming a file was changed.
- Claiming a source supports a statement.
- Claiming there are no errors.
- Asking the user to trust a summarized result.

The verified agent can still act, but only after attaching fresh evidence. If evidence is
missing, stale, contradicted, or provenance is lost, the gate blocks or forces a refresh.

## Baseline vs Verified Comparison

Each task should run two variants:

- Baseline: normal tool-using agent memory and summaries.
- Verified: same tools and model, but high-risk actions pass through verification.

Compare:

- Task success.
- False completion rate.
- Unsupported claims.
- Stale evidence use.
- Source attribution accuracy.
- Extra tool calls.
- Extra time/tokens.
- Number of blocked actions that prevented a bad claim.

## Implementation Checklist

1. Add a `tool_using_langgraph` framework mode or extend `framework=langgraph` behind a
   config flag.
2. Add a per-run workspace directory under the output artifact directory.
3. Implement safe file, shell, test, and source-fetch tools.
4. Make every tool call emit trace events in the existing schema.
5. Add evidence-ledger data to run metadata or trace events.
6. Update claim extraction to link claims to ledger evidence.
7. Run the same seed tasks under baseline and verified variants.
8. Add regression tests that prove unsupported completion claims are blocked.
9. Add at least one coding and one non-coding tool-using seed task.
10. Regenerate matrix reports across the first five models.

## Acceptance Bar

A full tool-using checkpoint should not be marked done until:

- At least five local model rows run successfully.
- At least one coding task uses real file edits and real tests.
- At least one non-coding task uses real source/data evidence.
- Baseline and verified variants both produce artifacts.
- Verification blocks at least one seeded unsupported high-risk claim.
- Focused research tests and full backend tests pass.
