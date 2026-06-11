# Open Model Matrix

The model matrix defines local open-weight model rows for repeatable comparison on the
MacBook M4 Air with 24 GB RAM.

## Configured Models

Configured in `research/agents/model_matrix.json`:

| Family | Model | Role |
|---|---|---|
| Qwen | `qwen2.5-coder:7b` | coding/tool-use baseline |
| Llama | `llama3.2:3b` | small instruction-following baseline |
| Mistral | `devstral-small-2:24b` | primary local software-engineering agent |
| Mistral | `mistral:7b` | disabled historical general baseline |
| DeepSeek | `deepseek-r1:8b` | reasoning-heavy baseline |
| Gemma | `gemma3:4b` | compact reasoning baseline |
| Gemma | `gemma4:12b-mlx` | larger heavyweight local stress test |
| Phi | `phi4-mini:latest` | small reasoning-dense baseline |

Several models are open-weight rather than OSI open-source. For publication, report exact
tags and licenses separately.

## Historical First Five

The June 4, 2026 clean five-model LangGraph comparison counted:

- `qwen2.5-coder:7b`
- `llama3.2:3b`
- `mistral:7b`
- `gemma3:4b`
- `phi4-mini:latest`

These rows succeeded across all three seed tasks with real LangGraph/Ollama artifacts.

The current configuration replaces the active Mistral row with
`devstral-small-2:24b`. On June 11, 2026 it completed a real eight-action
`langgraph_tools` coding run with valid structured actions and independent evaluator
success. It fits narrowly on the 24 GB M4 Air at roughly 15.5 GiB total model/runtime
memory, so broad sweeps should run it sequentially.

## Historical Result

Manifest:

```text
/tmp/agent-memory-langgraph-5model-alltasks-m4air/model_matrix_manifest.json
```

Report:

```text
research/reports/langgraph_5model_alltasks_comparison_20260604.md
```

Aggregate:

- 5 successful model rows.
- 15 baseline task rows.
- 30 run artifacts.
- 15 verification artifacts.
- 15 score artifacts.
- 15 comparisons.
- Parse statuses: `json:11`, `json_repaired:2`, `unparsed:2`.
- Parsed claims: 29.
- High-risk labels: 19.
- Blocked actions: 19.

## Gemma 4 12B MLX Status

`gemma4:12b-mlx` is installed and runnable after updating Ollama, but it is not counted in
the clean comparison yet.

Reason:

- The current LangGraph benchmark call returns empty final content.
- The raw response uses the generation budget in `thinking`.
- A 1024-token probe still ended with no usable final JSON.

Interpretation:

- This is real runtime evidence.
- It is not yet usable parsed memory-corruption evidence.
- The next step is prompt/runtime tuning so Gemma 4 emits final structured content.

## Recommended Future Matrix

After the coding tool loop is stable, rerun:

- A five-family controlled comparison over the 10-task benchmark.
- At least full-history and one corruption condition per task.
- Task-state probes with an explicit `--probe-max-tokens` budget.
- Gemma 4 12B heavyweight comparison.
- Optional DeepSeek row if runtime performance is acceptable.
- A second framework adapter such as AutoGen or CrewAI.
