import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AppBar,
  Box,
  CircularProgress,
  Container,
  Tab,
  Tabs,
  Toolbar,
  Typography,
  Alert
} from "@mui/material";
import { BrowserRouter, Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import TimelineIconModule from "@mui/icons-material/Timeline";
import { ResearchDashboard } from "./components/ResearchDashboard";
import type { ExecutionGraphNode, ExecutionGraphResponse, Session, TraceEvent, TraceResponse } from "./types/observability";
import { apiClient } from "./api/client";
import { ObservabilityWebSocketClient } from "./api/websocket";
import { SessionListView } from "./components/SessionListView";
import { ExecutionGraph } from "./components/ExecutionGraph";
import { EventDetailPanel } from "./components/EventDetailPanel";
import { ReasoningTraceView } from "./components/ReasoningTraceView";
import { ToolCallMonitor } from "./components/ToolCallMonitor";
import { unwrapMuiIcon } from "./utils/muiIcon";

const TimelineIcon = unwrapMuiIcon(TimelineIconModule);

function DashboardPage() {
  const navigate = useNavigate();
  const handleSelectSession = useCallback((session: Session) => {
    navigate(`/sessions/${session.session_id}`);
  }, [navigate]);

  return (
    <Container className="page-frame" maxWidth={false}>
      <SessionListView onSelectSession={handleSelectSession} />
    </Container>
  );
}

function ResearchDashboardPage() {
  return (
    <Container className="page-frame" maxWidth={false}>
      <ResearchDashboard />
    </Container>
  );
}

function SessionDetailPage() {
  const { sessionId = "" } = useParams();
  const [graph, setGraph] = useState<ExecutionGraphResponse | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [liveEvents, setLiveEvents] = useState<TraceEvent[]>([]);
  const [selectedNode, setSelectedNode] = useState<ExecutionGraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [graphResponse, traceResponse] = await Promise.all([
          apiClient.getGraph(sessionId),
          apiClient.getTrace(sessionId, { page_size: 500 })
        ]);
        if (!active) {
          return;
        }
        setGraph(graphResponse);
        setTrace(traceResponse);
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Unable to load session trace");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [sessionId]);

  useEffect(() => {
    const lastSequenceNumber = trace?.events.at(-1)?.sequence_number;
    const wsClient = new ObservabilityWebSocketClient();
    const unsubscribe = wsClient.onMessage((message) => {
      if (message.type === "snapshot" && message.session_id === sessionId) {
        setLiveEvents((events) => [...events, ...message.events]);
      }
      if (message.type === "event" && message.session_id === sessionId) {
        setLiveEvents((events) => [...events, message.event]);
      }
      if (message.type === "events" && message.session_id === sessionId) {
        setLiveEvents((events) => [...events, ...message.events]);
      }
    });
    wsClient.connect();
    wsClient.subscribe(sessionId, lastSequenceNumber);

    return () => {
      unsubscribe();
      wsClient.close();
    };
  }, [sessionId, trace?.events]);

  const allEvents = useMemo(() => {
    const eventMap = new Map<string, TraceEvent>();
    trace?.events.forEach((event) => eventMap.set(event.event_id, event));
    liveEvents.forEach((event) => eventMap.set(event.event_id, event));
    return Array.from(eventMap.values()).sort((a, b) => a.sequence_number - b.sequence_number);
  }, [liveEvents, trace?.events]);

  const selectedEvent = useMemo(() => {
    if (!selectedNode) {
      return null;
    }
    return allEvents.find((event) => event.event_id === selectedNode.event_id) ?? null;
  }, [allEvents, selectedNode]);

  if (loading) {
    return (
      <Box className="full-page-center">
        <CircularProgress />
      </Box>
    );
  }

  if (error || !graph) {
    return (
      <Container className="page-frame" maxWidth={false}>
        <Alert severity="error">{error ?? "Session graph is unavailable"}</Alert>
      </Container>
    );
  }

  return (
    <Container className="page-frame" maxWidth={false}>
      <Box className="session-detail-layout">
        <ExecutionGraph
          graph={graph}
          liveEvents={liveEvents}
          onSelectNode={setSelectedNode}
          selectedNodeId={selectedNode?.event_id ?? null}
        />
        <EventDetailPanel event={selectedEvent} />
      </Box>
      <ToolCallMonitor events={allEvents} />
      <ReasoningTraceView events={allEvents} />
    </Container>
  );
}

function AppShell() {
  return (
    <BrowserRouter>
      <AppBar className="top-bar" color="inherit" elevation={0} position="sticky">
        <Toolbar>
          <TimelineIcon color="primary" />
          <Typography className="brand-title" component={Link} to="/" variant="h6">
            Agent Observer
          </Typography>
          <Tabs value={false}>
            <Tab component={Link} label="Sessions" to="/" />
            <Tab component={Link} label="Research" to="/research" />
          </Tabs>
        </Toolbar>
      </AppBar>
      <Routes>
        <Route element={<DashboardPage />} path="/" />
        <Route element={<ResearchDashboardPage />} path="/research" />
        <Route element={<SessionDetailPage />} path="/sessions/:sessionId" />
      </Routes>
    </BrowserRouter>
  );
}

export default AppShell;
