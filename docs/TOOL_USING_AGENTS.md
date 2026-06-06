# Tool-Using Agents

The project now has two LangGraph paths:

- `langgraph`: a bounded benchmark graph used for the current five-model comparison.
- `langgraph_tools`: a coding-focused tool loop with a real isolated workspace, file
  reads/writes, Python test execution, an evidence ledger, and verification events.

The broader goal is still a full tool-using agent that can perform long-horizon work and
be verified while it acts.

## Current State

The bounded `langgraph` graph executes these nodes:

- `receive_goal`
- `load_memory`
- `call_model`
- `emit_trace`

The coding-focused `langgraph_tools` graph executes these nodes:

- `receive_goal`
- `retrieve_memory`
- `plan_next_step`
- `choose_tool`
- `execute_tool`
- `ingest_observation`
- `update_memory`
- `verify_high_risk_claims`
- `decide_continue_or_finish`
- `call_model`
- `emit_trace`

That tool loop is enough to evaluate a real coding workflow with files and tests. It is
not yet a general autonomous research/browser/data-analysis agent.

## Target Agent Graph

The implemented coding loop follows this shape:

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

Currently implemented in `langgraph_tools`:

- isolated coding workspace setup
- `list_files`
- `read_file`
- `write_file`
- `run_tests` via `python -m unittest discover -s .`

Still future for coding tasks:

- general shell command execution
- git status/diff inspection
- patch-style editing
- richer multi-file task fixtures

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

## Implemented Coding Checkpoint

Smoke artifact:

```text
/tmp/agent-memory-langgraph-tools-coding-smoke/coding_stale_tests_001_baseline.json
```

The run records:

- 44 trace events.
- 6 coding tool-loop iterations.
- real parser/test files in an isolated workspace.
- a stale pre-edit test-pass/task-complete claim after later file/test changes.
- a final post-edit test run with `Ran 2 tests ... OK`.
- memory-health detection of stale and false-completion claims.
- verified variant tests that block stale high-risk actions.

## Implementation Checklist

1. [x] Add a `langgraph_tools` framework mode for coding tasks.
2. [x] Add a per-run workspace directory under the output artifact directory.
3. [x] Implement safe file and test tools for the first coding fixture.
4. [x] Make every tool call emit trace events in the existing schema.
5. [x] Add evidence-ledger data to trace events.
6. [x] Preserve stale evidence so verification can block it.
7. [x] Add regression tests that prove stale completion claims are blocked.
8. [ ] Add general shell/git tools.
9. [ ] Add richer multi-file coding fixtures.
10. [ ] Add at least one non-coding tool-using seed task after coding stabilizes.
11. [ ] Regenerate matrix reports across the first five models with `langgraph_tools`.

## Acceptance Bar

A full tool-using checkpoint should not be marked done until:

- At least five local model rows run successfully.
- At least one coding task uses real file edits and real tests.
- At least one non-coding task uses real source/data evidence.
- Baseline and verified variants both produce artifacts.
- Verification blocks at least one seeded unsupported high-risk claim.
- Focused research tests and full backend tests pass.

The current coding checkpoint satisfies the coding-file/test-tool portion, but not the
five-model matrix or non-coding tool portions yet.
