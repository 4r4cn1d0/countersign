import { Box, Chip, Divider, Typography } from "@mui/material";
import type { TraceEvent } from "../types/observability";
import { formatDuration } from "../utils/format";

interface EventDetailPanelProps {
  event?: TraceEvent | null;
}

function renderValue(value: unknown): string {
  if (value == null) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

export function EventDetailPanel({ event }: EventDetailPanelProps) {
  if (!event) {
    return (
      <Box className="detail-panel">
        <Typography component="h2" variant="h6">
          Event detail
        </Typography>
        <Typography color="text.secondary" variant="body2">
          Select a graph node to inspect its trace payload.
        </Typography>
      </Box>
    );
  }

  const data = event.event_data;

  return (
    <Box className="detail-panel">
      <Box className="panel-heading compact">
        <Box>
          <Typography component="h2" variant="h6">
            {event.event_type.replaceAll("_", " ")}
          </Typography>
          <Typography color="text.secondary" variant="caption">
            #{event.sequence_number} / {new Date(event.timestamp).toLocaleString()}
          </Typography>
        </Box>
        <Chip label={event.status ?? "recorded"} size="small" />
      </Box>

      <Box className="metric-row">
        <span>Duration</span>
        <strong>{formatDuration(event.duration_ms)}</strong>
      </Box>
      <Box className="metric-row">
        <span>Event ID</span>
        <strong>{event.event_id.slice(0, 8)}</strong>
      </Box>

      <Divider />

      {event.event_type === "reasoning_step" ? (
        <Box className="detail-section">
          <Typography variant="subtitle2">Prompt</Typography>
          <pre>{renderValue(data.prompt ?? data.input ?? data.llm_prompt)}</pre>
          <Typography variant="subtitle2">Response</Typography>
          <pre>{renderValue(data.response ?? data.output ?? data.completion)}</pre>
        </Box>
      ) : null}

      {event.event_type === "tool_call" ? (
        <Box className="detail-section">
          <Typography variant="subtitle2">Tool</Typography>
          <Typography>{renderValue(data.tool_name)}</Typography>
          <Typography variant="subtitle2">Input</Typography>
          <pre>{renderValue(data.input_parameters ?? data.arguments ?? data.input)}</pre>
          <Typography variant="subtitle2">Output</Typography>
          <pre>{renderValue(data.output ?? data.result)}</pre>
          {data.error ? (
            <>
              <Typography color="error" variant="subtitle2">Error</Typography>
              <pre>{renderValue(data.error)}</pre>
            </>
          ) : null}
        </Box>
      ) : null}

      {event.event_type === "memory_access" ? (
        <Box className="detail-section">
          <Typography variant="subtitle2">Query</Typography>
          <pre>{renderValue(data.query)}</pre>
          <Typography variant="subtitle2">Results</Typography>
          <pre>{renderValue(data.results ?? data.retrieved_items)}</pre>
        </Box>
      ) : null}

      <Typography variant="subtitle2">Raw payload</Typography>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </Box>
  );
}
