import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import SearchIconModule from "@mui/icons-material/Search";
import RefreshIconModule from "@mui/icons-material/Refresh";
import type { AgentObserverApiClient } from "../api/client";
import { apiClient } from "../api/client";
import type { Session, SessionSearchFilters, SessionStatus } from "../types/observability";
import { formatCurrency, formatDateTime, formatDuration, highlightParts, toNumber } from "../utils/format";
import { unwrapMuiIcon } from "../utils/muiIcon";

const SearchIcon = unwrapMuiIcon(SearchIconModule);
const RefreshIcon = unwrapMuiIcon(RefreshIconModule);

type SessionClient = Pick<AgentObserverApiClient, "listSessions" | "searchSessions">;

interface SessionListViewProps {
  client?: SessionClient;
  onSelectSession?: (session: Session) => void;
}

const statuses: SessionStatus[] = ["running", "completed", "failed", "timeout", "cancelled"];

function statusColor(status: SessionStatus): "default" | "primary" | "success" | "error" | "warning" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed" || status === "timeout") {
    return "error";
  }
  if (status === "running") {
    return "primary";
  }
  if (status === "cancelled") {
    return "warning";
  }
  return "default";
}

export function SessionListView({ client = apiClient, onSelectSession }: SessionListViewProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<SessionStatus | "">("");
  const [tagInput, setTagInput] = useState("");
  const [agentType, setAgentType] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [minCost, setMinCost] = useState("");
  const [maxCost, setMaxCost] = useState("");
  const [minDuration, setMinDuration] = useState("");
  const [maxDuration, setMaxDuration] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [sortField, setSortField] = useState("created_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  const tags = useMemo(
    () => tagInput.split(",").map((tag) => tag.trim()).filter(Boolean),
    [tagInput]
  );

  const hasAdvancedSearch = Boolean(
    query.trim() ||
      status ||
      tags.length ||
      agentType.trim() ||
      startDate ||
      endDate ||
      minCost ||
      maxCost ||
      minDuration ||
      maxDuration
  );

  const clientSideDurationFiltered = useMemo(() => {
    const durationMin = toNumber(minDuration);
    const durationMax = toNumber(maxDuration);
    if (durationMin == null && durationMax == null) {
      return sessions;
    }
    return sessions.filter((session) => {
      const duration = session.duration_ms ?? 0;
      return (durationMin == null || duration >= durationMin) && (durationMax == null || duration <= durationMax);
    });
  }, [sessions, minDuration, maxDuration]);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const offset = page * rowsPerPage;
      const sort = `${sortField}:${sortDirection}`;
      let result;

      if (hasAdvancedSearch) {
        const filters: SessionSearchFilters = {};
        if (status) {
          filters.status = [status];
        }
        if (tags.length) {
          filters.tags = tags;
        }
        if (agentType.trim()) {
          filters.agent_type = agentType.trim();
        }
        if (startDate || endDate) {
          filters.date_range = {};
          if (startDate) {
            filters.date_range.start = new Date(startDate).toISOString();
          }
          if (endDate) {
            filters.date_range.end = new Date(endDate).toISOString();
          }
        }
        if (minCost || maxCost) {
          filters.cost_range = {};
          const min = toNumber(minCost);
          const max = toNumber(maxCost);
          if (min != null) {
            filters.cost_range.min = min;
          }
          if (max != null) {
            filters.cost_range.max = max;
          }
        }
        if (minDuration || maxDuration) {
          filters.duration_range = {};
          const min = toNumber(minDuration);
          const max = toNumber(maxDuration);
          if (min != null) {
            filters.duration_range.min = min;
          }
          if (max != null) {
            filters.duration_range.max = max;
          }
        }
        result = await client.searchSessions({
          query: query.trim() || undefined,
          filters,
          sort,
          limit: rowsPerPage,
          offset
        });
      } else {
        result = await client.listSessions({
          limit: rowsPerPage,
          offset,
          sort
        });
      }

      setSessions(result.sessions);
      setTotal(result.total);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load sessions");
    } finally {
      setLoading(false);
    }
  }, [
    agentType,
    client,
    endDate,
    hasAdvancedSearch,
    maxCost,
    maxDuration,
    minCost,
    minDuration,
    page,
    query,
    rowsPerPage,
    sortDirection,
    sortField,
    startDate,
    status,
    tags
  ]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  const handleSort = (field: string) => {
    if (field === sortField) {
      setSortDirection((direction) => (direction === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection("desc");
  };

  return (
    <Box className="workspace-panel">
      <Box className="panel-heading">
        <Box>
          <Typography component="h1" variant="h5">
            Sessions
          </Typography>
          <Typography color="text.secondary" variant="body2">
            {total.toLocaleString()} tracked runs
          </Typography>
        </Box>
        <Tooltip title="Refresh sessions">
          <IconButton aria-label="Refresh sessions" onClick={() => void loadSessions()}>
            <RefreshIcon />
          </IconButton>
        </Tooltip>
      </Box>

      <Grid alignItems="center" container spacing={1.5}>
        <Grid item lg={3} md={4} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Search"
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
            size="small"
            value={query}
          />
        </Grid>
        <Grid item lg={2} md={4} sm={6} xs={12}>
          <FormControl fullWidth size="small">
            <InputLabel id="session-status-label">Status</InputLabel>
            <Select
              label="Status"
              labelId="session-status-label"
              onChange={(event) => {
                setStatus(event.target.value as SessionStatus | "");
                setPage(0);
              }}
              value={status}
            >
              <MenuItem value="">Any</MenuItem>
              {statuses.map((item) => (
                <MenuItem key={item} value={item}>
                  {item}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item lg={2} md={4} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Agent"
            onChange={(event) => {
              setAgentType(event.target.value);
              setPage(0);
            }}
            size="small"
            value={agentType}
          />
        </Grid>
        <Grid item lg={3} md={4} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Tags"
            onChange={(event) => {
              setTagInput(event.target.value);
              setPage(0);
            }}
            size="small"
            value={tagInput}
          />
        </Grid>
        <Grid item lg={2} md={4} sm={6} xs={12}>
          <Button fullWidth onClick={() => void loadSessions()} startIcon={<SearchIcon />} variant="contained">
            Search
          </Button>
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            InputLabelProps={{ shrink: true }}
            label="Start"
            onChange={(event) => {
              setStartDate(event.target.value);
              setPage(0);
            }}
            size="small"
            type="date"
            value={startDate}
          />
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            InputLabelProps={{ shrink: true }}
            label="End"
            onChange={(event) => {
              setEndDate(event.target.value);
              setPage(0);
            }}
            size="small"
            type="date"
            value={endDate}
          />
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Min cost"
            onChange={(event) => {
              setMinCost(event.target.value);
              setPage(0);
            }}
            size="small"
            type="number"
            value={minCost}
          />
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Max cost"
            onChange={(event) => {
              setMaxCost(event.target.value);
              setPage(0);
            }}
            size="small"
            type="number"
            value={maxCost}
          />
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Min duration"
            onChange={(event) => {
              setMinDuration(event.target.value);
              setPage(0);
            }}
            size="small"
            type="number"
            value={minDuration}
          />
        </Grid>
        <Grid item md={3} sm={6} xs={12}>
          <TextField
            fullWidth
            label="Max duration"
            onChange={(event) => {
              setMaxDuration(event.target.value);
              setPage(0);
            }}
            size="small"
            type="number"
            value={maxDuration}
          />
        </Grid>
      </Grid>

      {error ? <Alert severity="error">{error}</Alert> : null}

      <TableContainer className="table-shell">
        <Table aria-label="Session list" size="small">
          <TableHead>
            <TableRow>
              <TableCell>
                <TableSortLabel
                  active={sortField === "created_at"}
                  direction={sortDirection}
                  onClick={() => handleSort("created_at")}
                >
                  Created
                </TableSortLabel>
              </TableCell>
              <TableCell>Goal</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortField === "duration_ms"}
                  direction={sortDirection}
                  onClick={() => handleSort("duration_ms")}
                >
                  Duration
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortField === "total_cost"}
                  direction={sortDirection}
                  onClick={() => handleSort("total_cost")}
                >
                  Cost
                </TableSortLabel>
              </TableCell>
              <TableCell>Activity</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Box className="center-row">
                    <CircularProgress size={22} />
                  </Box>
                </TableCell>
              </TableRow>
            ) : null}
            {!loading && clientSideDurationFiltered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography color="text.secondary" variant="body2">
                    No sessions match the current filters.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
            {clientSideDurationFiltered.map((session) => (
              <TableRow
                hover
                key={session.session_id}
                onClick={() => onSelectSession?.(session)}
                sx={{ cursor: onSelectSession ? "pointer" : "default" }}
              >
                <TableCell>{formatDateTime(session.created_at)}</TableCell>
                <TableCell>
                  <Typography className="goal-cell" variant="body2">
                    {highlightParts(session.goal, query).map((part, index) =>
                      part.match ? <mark key={`${part.text}-${index}`}>{part.text}</mark> : part.text
                    )}
                  </Typography>
                  <Box className="tag-row">
                    <Chip label={session.agent_type} size="small" />
                    {session.tags.slice(0, 3).map((tag) => (
                      <Chip key={tag} label={tag} size="small" variant="outlined" />
                    ))}
                  </Box>
                </TableCell>
                <TableCell>
                  <Chip color={statusColor(session.status)} label={session.status} size="small" />
                </TableCell>
                <TableCell>{formatDuration(session.duration_ms)}</TableCell>
                <TableCell>{formatCurrency(session.total_cost)}</TableCell>
                <TableCell>
                  <Typography variant="body2">{session.total_reasoning_steps} reasoning</Typography>
                  <Typography color="text.secondary" variant="caption">
                    {session.total_tool_calls} tools / {session.total_memory_accesses} memory
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <TablePagination
        component="div"
        count={total}
        onPageChange={(_, nextPage) => setPage(nextPage)}
        onRowsPerPageChange={(event) => {
          setRowsPerPage(Number(event.target.value));
          setPage(0);
        }}
        page={page}
        rowsPerPage={rowsPerPage}
        rowsPerPageOptions={[10, 25, 50]}
      />
    </Box>
  );
}
