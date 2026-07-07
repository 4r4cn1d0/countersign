import { Fragment, useMemo, useState } from "react";
import {
  Box,
  Chip,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography
} from "@mui/material";
import ErrorOutlineIconModule from "@mui/icons-material/ErrorOutline";
import TimerIconModule from "@mui/icons-material/Timer";
import type { TraceEvent } from "../types/observability";
import { formatDuration, toNumber } from "../utils/format";
import { unwrapMuiIcon } from "../utils/muiIcon";

const ErrorOutlineIcon = unwrapMuiIcon(ErrorOutlineIconModule);
const TimerIcon = unwrapMuiIcon(TimerIconModule);

interface ToolCallMonitorProps {
  events: TraceEvent[];
}

interface ToolCallRecord {
  eventId: string;
  sequenceNumber: number;
  timestamp: string;
  toolName: string;
  toolType: string;
  status: string;
  durationMs: number | null;
  inputs: unknown;
  outputs: unknown;
  retryCount: number;
  errorType?: string | null;
  errorMessage?: string | null;
  stackTrace?: string | null;
  errorContext?: unknown;
}

interface ToolStats {
  toolName: string;
  total: number;
  failures: number;
  totalDuration: number;
  measured: number;
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function readObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function renderValue(value: unknown): string {
  if (value == null || value === "") {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

function normalizeStatus(event: TraceEvent, data: Record<string, unknown>, errorMessage?: string | null): string {
  const status = stringValue(event.status ?? data.status);
  if (status) {
    return status;
  }
  return errorMessage ? "failed" : "completed";
}

function isFailed(status: string, errorMessage?: string | null): boolean {
  return Boolean(errorMessage) || ["failed", "error", "timeout"].includes(status.toLowerCase());
}

function normalizeToolCall(event: TraceEvent): ToolCallRecord {
  const data = event.event_data;
  const error = readObject(data.error);
  const retryCount = toNumber(data.retry_count) ?? toNumber(data.retryCount) ?? 0;
  const errorType = event.error_type ?? (stringValue(data.error_type) || stringValue(error?.type ?? error?.error_type));
  const errorMessage = event.error_message ?? (stringValue(data.error_message) || stringValue(error?.message ?? error?.error));
  const status = normalizeStatus(event, data, errorMessage || null);

  return {
    eventId: event.event_id,
    sequenceNumber: event.sequence_number,
    timestamp: event.timestamp,
    toolName: stringValue(data.tool_name ?? data.toolName ?? data.name, "unknown"),
    toolType: stringValue(data.tool_type ?? data.toolType, "function"),
    status,
    durationMs: event.duration_ms ?? toNumber(data.duration_ms) ?? null,
    inputs: data.inputs ?? data.input_parameters ?? data.arguments ?? data.input ?? null,
    outputs: data.outputs ?? data.output ?? data.result ?? null,
    retryCount,
    errorType: errorType || null,
    errorMessage: errorMessage || null,
    stackTrace: stringValue(data.stack_trace ?? error?.stack_trace, "") || null,
    errorContext: error?.context ?? data.execution_context ?? data.context ?? null
  };
}

function statusColor(record: ToolCallRecord): "default" | "success" | "error" | "warning" | "primary" {
  if (isFailed(record.status, record.errorMessage)) {
    return "error";
  }
  if (record.durationMs != null && record.durationMs > 5000) {
    return "warning";
  }
  if (["completed", "success", "succeeded"].includes(record.status.toLowerCase())) {
    return "success";
  }
  if (["running", "pending"].includes(record.status.toLowerCase())) {
    return "primary";
  }
  return "default";
}

function calculateStats(records: ToolCallRecord[]) {
  const measured = records.filter((record) => record.durationMs != null);
  const totalDuration = measured.reduce((sum, record) => sum + (record.durationMs ?? 0), 0);
  const failures = records.filter((record) => isFailed(record.status, record.errorMessage)).length;
  const slow = records.filter((record) => (record.durationMs ?? 0) > 5000).length;
  const byTool = new Map<string, ToolStats>();

  for (const record of records) {
    const stats = byTool.get(record.toolName) ?? {
      toolName: record.toolName,
      total: 0,
      failures: 0,
      totalDuration: 0,
      measured: 0
    };
    stats.total += 1;
    if (isFailed(record.status, record.errorMessage)) {
      stats.failures += 1;
    }
    if (record.durationMs != null) {
      stats.totalDuration += record.durationMs;
      stats.measured += 1;
    }
    byTool.set(record.toolName, stats);
  }

  return {
    total: records.length,
    averageDuration: measured.length ? totalDuration / measured.length : 0,
    failureRate: records.length ? failures / records.length : 0,
    failures,
    slow,
    byTool: Array.from(byTool.values()).sort((a, b) => b.total - a.total || a.toolName.localeCompare(b.toolName))
  };
}

export function ToolCallMonitor({ events }: ToolCallMonitorProps) {
  const [toolFilter, setToolFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [minDuration, setMinDuration] = useState("");
  const [maxDuration, setMaxDuration] = useState("");

  const toolCalls = useMemo(
    () => events
      .filter((event) => event.event_type === "tool_call")
      .map(normalizeToolCall)
      .sort((a, b) => a.sequenceNumber - b.sequenceNumber),
    [events]
  );

  const filteredToolCalls = useMemo(() => {
    const min = toNumber(minDuration);
    const max = toNumber(maxDuration);
    const nameQuery = toolFilter.trim().toLowerCase();

    return toolCalls.filter((record) => {
      const failed = isFailed(record.status, record.errorMessage);
      const duration = record.durationMs ?? 0;
      return (
        (!nameQuery || record.toolName.toLowerCase().includes(nameQuery)) &&
        (statusFilter === "all" ||
          (statusFilter === "failed" && failed) ||
          (statusFilter === "success" && !failed) ||
          record.status.toLowerCase() === statusFilter) &&
        (min == null || duration >= min) &&
        (max == null || duration <= max)
      );
    });
  }, [maxDuration, minDuration, statusFilter, toolCalls, toolFilter]);

  const stats = useMemo(() => calculateStats(filteredToolCalls), [filteredToolCalls]);

  return (
    <Box className="tool-panel">
      <Box className="panel-heading">
        <Box>
          <Typography component="h2" variant="h6">
            Tool calls
          </Typography>
          <Typography color="text.secondary" variant="body2">
            {stats.total} matching calls
          </Typography>
        </Box>
        <Box className="chip-row">
          <Chip label={`${stats.failures} failed`} color={stats.failures ? "error" : "default"} size="small" />
          <Chip label={`${stats.slow} slow`} color={stats.slow ? "warning" : "default"} size="small" />
        </Box>
      </Box>

      <Grid container spacing={1.5}>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Tool"
            onChange={(event) => setToolFilter(event.target.value)}
            size="small"
            value={toolFilter}
          />
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <FormControl fullWidth size="small">
            <InputLabel id="tool-status-label">Status</InputLabel>
            <Select
              label="Status"
              labelId="tool-status-label"
              onChange={(event) => setStatusFilter(event.target.value)}
              value={statusFilter}
            >
              <MenuItem value="all">All</MenuItem>
              <MenuItem value="success">Success</MenuItem>
              <MenuItem value="failed">Failed</MenuItem>
              <MenuItem value="running">Running</MenuItem>
              <MenuItem value="timeout">Timeout</MenuItem>
            </Select>
          </FormControl>
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Min duration"
            onChange={(event) => setMinDuration(event.target.value)}
            size="small"
            type="number"
            value={minDuration}
          />
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Max duration"
            onChange={(event) => setMaxDuration(event.target.value)}
            size="small"
            type="number"
            value={maxDuration}
          />
        </Grid>
      </Grid>

      <Box className="stat-grid">
        <Box className="stat-tile">
          <span>Total calls</span>
          <strong>{stats.total}</strong>
        </Box>
        <Box className="stat-tile">
          <span>Average duration</span>
          <strong>{formatDuration(Math.round(stats.averageDuration))}</strong>
        </Box>
        <Box className="stat-tile">
          <span>Failure rate</span>
          <strong>{Math.round(stats.failureRate * 100)}%</strong>
        </Box>
        <Box className="stat-tile">
          <span>Slow calls</span>
          <strong>{stats.slow}</strong>
        </Box>
      </Box>

      {stats.byTool.length ? (
        <Box className="tool-stats-row">
          {stats.byTool.map((tool) => (
            <Box className="tool-stat" key={tool.toolName}>
              <Typography variant="subtitle2">{tool.toolName}</Typography>
              <Typography color="text.secondary" variant="caption">
                {tool.total} calls / {tool.failures} failed / avg {formatDuration(tool.measured ? Math.round(tool.totalDuration / tool.measured) : 0)}
              </Typography>
            </Box>
          ))}
        </Box>
      ) : null}

      <TableContainer className="table-shell">
        <Table aria-label="Tool call list" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Seq</TableCell>
              <TableCell>Tool</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Duration</TableCell>
              <TableCell>Input</TableCell>
              <TableCell>Output</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredToolCalls.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography color="text.secondary" variant="body2">
                    No tool calls match the current filters.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
            {filteredToolCalls.map((record) => {
              const failed = isFailed(record.status, record.errorMessage);
              const slow = (record.durationMs ?? 0) > 5000;
              return (
                <Fragment key={record.eventId}>
                  <TableRow className={failed ? "tool-row failed" : "tool-row"}>
                    <TableCell>#{record.sequenceNumber}</TableCell>
                    <TableCell>
                      <Typography variant="body2">{record.toolName}</Typography>
                      <Typography color="text.secondary" variant="caption">
                        {record.toolType}
                        {record.retryCount ? ` / ${record.retryCount} retries` : ""}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box className="chip-row">
                        <Chip color={statusColor(record)} label={record.status} size="small" />
                        {slow ? <Chip color="warning" icon={<TimerIcon />} label="slow" size="small" /> : null}
                      </Box>
                    </TableCell>
                    <TableCell>{formatDuration(record.durationMs)}</TableCell>
                    <TableCell>
                      <pre className="tool-payload">{renderValue(record.inputs)}</pre>
                    </TableCell>
                    <TableCell>
                      <pre className="tool-payload">{renderValue(record.outputs)}</pre>
                    </TableCell>
                  </TableRow>
                  {failed ? (
                    <TableRow className="tool-error-row">
                      <TableCell colSpan={6}>
                        <Box className="tool-error">
                          <Box className="chip-row">
                            <ErrorOutlineIcon color="error" fontSize="small" />
                            <Typography color="error" variant="subtitle2">
                              {record.errorType ?? "Tool call error"}
                            </Typography>
                          </Box>
                          <Typography variant="body2">{record.errorMessage ?? "No error message recorded."}</Typography>
                          {record.stackTrace ? (
                            <>
                              <Typography variant="subtitle2">Stack trace</Typography>
                              <pre className="tool-error-code">{record.stackTrace}</pre>
                            </>
                          ) : null}
                          {record.errorContext ? (
                            <>
                              <Typography variant="subtitle2">Execution context</Typography>
                              <pre className="tool-error-code">{renderValue(record.errorContext)}</pre>
                            </>
                          ) : null}
                        </Box>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <Divider />
    </Box>
  );
}
