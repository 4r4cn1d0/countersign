import { useMemo, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Chip,
  Divider,
  Typography
} from "@mui/material";
import ExpandMoreIconModule from "@mui/icons-material/ExpandMore";
import type { TraceEvent } from "../types/observability";
import { detectStructuredOutput, formatStructuredOutput, toNumber, toStringArray } from "../utils/format";
import { unwrapMuiIcon } from "../utils/muiIcon";

const ExpandMoreIcon = unwrapMuiIcon(ExpandMoreIconModule);

interface ReasoningTraceViewProps {
  events: TraceEvent[];
}

function stringField(data: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string") {
      return value;
    }
  }
  return "";
}

function numberField(data: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = toNumber(data[key]);
    if (value != null) {
      return value;
    }
  }
  return undefined;
}

function highlightInfluence(text: string, markers: string[]) {
  if (markers.length === 0) {
    return text;
  }
  const escaped = markers.map((marker) => marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "i");
  return text.split(pattern).filter(Boolean).map((part, index) =>
    pattern.test(part) ? <mark key={`${part}-${index}`}>{part}</mark> : part
  );
}

export function ReasoningTraceView({ events }: ReasoningTraceViewProps) {
  const [expanded, setExpanded] = useState<string | false>(false);
  const reasoningEvents = useMemo(
    () => events.filter((event) => event.event_type === "reasoning_step").sort((a, b) => a.sequence_number - b.sequence_number),
    [events]
  );

  return (
    <Box className="reasoning-panel">
      <Box className="panel-heading">
        <Box>
          <Typography component="h2" variant="h6">
            Reasoning trace
          </Typography>
          <Typography color="text.secondary" variant="body2">
            {reasoningEvents.length} LLM calls
          </Typography>
        </Box>
      </Box>

      {reasoningEvents.length === 0 ? (
        <Typography color="text.secondary" variant="body2">
          No reasoning events recorded for this session.
        </Typography>
      ) : null}

      {reasoningEvents.map((event, index) => {
        const data = event.event_data;
        const prompt = stringField(data, ["prompt", "llm_prompt", "input"]);
        const response = stringField(data, ["response", "completion", "output"]);
        const model = stringField(data, ["model", "model_name"]);
        const temperature = numberField(data, ["temperature"]);
        const inputTokens = numberField(data, ["input_tokens", "prompt_tokens"]);
        const outputTokens = numberField(data, ["output_tokens", "completion_tokens"]);
        const markers = toStringArray(data.influence_markers ?? data.decision_influencing_phrases);
        const structuredKind = detectStructuredOutput(response);
        const formattedResponse = formatStructuredOutput(response);
        const parameters = data.generation_parameters ?? data.parameters ?? {};

        return (
          <Accordion
            expanded={expanded === event.event_id}
            key={event.event_id}
            onChange={(_, nextExpanded) => setExpanded(nextExpanded ? event.event_id : false)}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box className="accordion-summary">
                <Typography variant="subtitle1">Call {index + 1}</Typography>
                <Box className="chip-row">
                  {model ? <Chip label={model} size="small" /> : null}
                  {temperature != null ? <Chip label={`temp ${temperature}`} size="small" variant="outlined" /> : null}
                  {inputTokens != null ? <Chip label={`${inputTokens} in`} size="small" variant="outlined" /> : null}
                  {outputTokens != null ? <Chip label={`${outputTokens} out`} size="small" variant="outlined" /> : null}
                </Box>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              <Box className="reasoning-grid">
                <Box>
                  <Typography variant="subtitle2">Prompt</Typography>
                  <pre className="trace-code">{prompt}</pre>
                </Box>
                <Box>
                  <Typography variant="subtitle2">Response</Typography>
                  <pre className={`trace-code syntax-${structuredKind}`}>{highlightInfluence(formattedResponse, markers)}</pre>
                </Box>
              </Box>
              <Divider />
              <Typography variant="subtitle2">Generation parameters</Typography>
              <pre className="trace-code compact">{JSON.stringify(parameters, null, 2)}</pre>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Box>
  );
}
