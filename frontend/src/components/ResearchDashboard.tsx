import { useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
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
  Tooltip,
  Typography
} from "@mui/material";
import UploadFileIconModule from "@mui/icons-material/UploadFile";
import type {
  ComparisonReport,
  MemoryClaim,
  MemoryHealthReport,
  ResearchReportBundle,
  VerificationDecision,
  VerificationReport
} from "../types/observability";
import { demoResearchReportBundle } from "../fixtures/researchReports";
import { unwrapMuiIcon } from "../utils/muiIcon";

const UploadFileIcon = unwrapMuiIcon(UploadFileIconModule);

interface ResearchDashboardProps {
  initialBundle?: ResearchReportBundle;
}

type ClaimFilter = "all" | "stale" | "unsupported" | "blocked" | "needs_verification";

interface ClaimRow {
  claim: MemoryClaim | null;
  decision: VerificationDecision | null;
}

interface RiskTimelinePoint {
  label: string;
  stale: number;
  unsupported: number;
  blocked: number;
  needsVerification: number;
  totalRisk: number;
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function signedPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${percent(value)}`;
}

function chipColor(value: number, inverse = false): "success" | "warning" | "error" | "default" {
  const score = inverse ? 1 - value : value;
  if (score >= 0.8) {
    return "success";
  }
  if (score >= 0.5) {
    return "warning";
  }
  if (score > 0) {
    return "error";
  }
  return "default";
}

function decisionColor(decision: string): "success" | "warning" | "error" | "default" {
  if (decision === "allow") {
    return "success";
  }
  if (decision === "block") {
    return "error";
  }
  if (decision === "needs_verification") {
    return "warning";
  }
  return "default";
}

function uniqueClaims(report: MemoryHealthReport): MemoryClaim[] {
  const claims = new Map<string, MemoryClaim>();
  [...report.unsupported_claims, ...report.stale_claims, ...report.contradicted_claims]
    .forEach((claim) => claims.set(claim.claim_id, claim));
  return Array.from(claims.values());
}

function buildClaimRows(bundle: ResearchReportBundle): ClaimRow[] {
  const claimsById = new Map(uniqueClaims(bundle.health).map((claim) => [claim.claim_id, claim]));
  const decisionsById = new Map(bundle.verification.decisions.map((decision) => [decision.claim_id, decision]));
  const ids = new Set([...claimsById.keys(), ...decisionsById.keys()]);
  return Array.from(ids).map((id) => ({
    claim: claimsById.get(id) ?? null,
    decision: decisionsById.get(id) ?? null
  }));
}

function buildRiskTimeline(bundle: ResearchReportBundle): RiskTimelinePoint[] {
  const bucketCount = 4;
  const traceEventCount = Math.max(bundle.health.trace_event_count, 1);
  const buckets = Array.from({ length: bucketCount }, (_, index): RiskTimelinePoint => {
    const start = Math.floor((index * traceEventCount) / bucketCount) + 1;
    const end = Math.max(start, Math.floor(((index + 1) * traceEventCount) / bucketCount));
    return {
      label: `Events ${start}-${end}`,
      stale: 0,
      unsupported: 0,
      blocked: 0,
      needsVerification: 0,
      totalRisk: 0
    };
  });

  for (const { claim, decision } of buildClaimRows(bundle)) {
    const sequenceNumbers = claim?.source_event_sequence_numbers ?? [];
    const sequenceNumber = sequenceNumbers.length ? Math.max(...sequenceNumbers) : traceEventCount;
    const bucketIndex = Math.min(
      bucketCount - 1,
      Math.max(0, Math.ceil((sequenceNumber / traceEventCount) * bucketCount) - 1)
    );
    const bucket = buckets[bucketIndex];
    if (claim?.stale) {
      bucket.stale += 1;
    }
    if (claim?.support_status === "unsupported" || claim?.lost_provenance) {
      bucket.unsupported += 1;
    }
    if (decision?.decision === "block") {
      bucket.blocked += 1;
    }
    if (decision?.decision === "needs_verification") {
      bucket.needsVerification += 1;
    }
    bucket.totalRisk = bucket.stale + bucket.unsupported + bucket.blocked + bucket.needsVerification;
  }

  return buckets;
}

function readArtifactFile(file: File): Promise<string> {
  if (typeof file.text === "function") {
    return file.text();
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result ?? "")));
    reader.addEventListener("error", () => reject(reader.error ?? new Error("Unable to read artifact")));
    reader.readAsText(file);
  });
}

async function parseArtifactFiles(files: FileList): Promise<Partial<ResearchReportBundle>> {
  const parsed = await Promise.all(Array.from(files).map(async (file) => JSON.parse(await readArtifactFile(file)) as {
    schema_version?: string;
  }));
  const next: Partial<ResearchReportBundle> = {};

  for (const artifact of parsed) {
    if (artifact.schema_version === "agent-memory-health/v0.1") {
      next.health = artifact as MemoryHealthReport;
    }
    if (artifact.schema_version === "agent-memory-verification/v0.1") {
      next.verification = artifact as VerificationReport;
    }
    if (artifact.schema_version === "agent-memory-comparison/v0.1") {
      next.comparison = artifact as ComparisonReport;
    }
  }

  return next;
}

export function ResearchDashboard({ initialBundle = demoResearchReportBundle }: ResearchDashboardProps) {
  const [bundle, setBundle] = useState(initialBundle);
  const [claimFilter, setClaimFilter] = useState<ClaimFilter>("all");
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const claimRows = useMemo(() => {
    const rows = buildClaimRows(bundle);
    return rows.filter(({ claim, decision }) => {
      if (claimFilter === "all") {
        return true;
      }
      if (claimFilter === "stale") {
        return Boolean(claim?.stale);
      }
      if (claimFilter === "unsupported") {
        return claim?.support_status === "unsupported";
      }
      if (claimFilter === "blocked") {
        return decision?.decision === "block";
      }
      if (claimFilter === "needs_verification") {
        return decision?.decision === "needs_verification";
      }
      return true;
    });
  }, [bundle, claimFilter]);
  const riskTimeline = useMemo(() => buildRiskTimeline(bundle), [bundle]);

  async function handleFileChange(files: FileList | null) {
    if (!files?.length) {
      return;
    }
    try {
      const artifacts = await parseArtifactFiles(files);
      setBundle((current) => ({
        ...current,
        ...artifacts,
        source: "uploaded"
      }));
      setArtifactError(null);
    } catch (caught) {
      setArtifactError(caught instanceof Error ? caught.message : "Unable to load research artifacts");
    }
  }

  return (
    <Box className="research-panel">
      <Box className="panel-heading">
        <Box>
          <Typography component="h1" variant="h5">
            Memory safety reports
          </Typography>
          <Box className="chip-row">
            <Chip label={bundle.health.task_id ?? "unknown task"} size="small" />
            <Chip label={bundle.runtime} size="small" />
            <Chip label={bundle.variant} size="small" />
            <Chip label={bundle.source} size="small" />
          </Box>
        </Box>
        <Box>
          <input
            hidden
            multiple
            onChange={(event) => void handleFileChange(event.target.files)}
            ref={fileInputRef}
            type="file"
          />
          <Tooltip title="Load JSON artifacts">
            <Button
              onClick={() => fileInputRef.current?.click()}
              startIcon={<UploadFileIcon />}
              variant="outlined"
            >
              Artifacts
            </Button>
          </Tooltip>
        </Box>
      </Box>

      {artifactError ? <Alert severity="error">{artifactError}</Alert> : null}

      <Grid container spacing={1.5}>
        <Grid item md={2} sm={4} xs={6}>
          <Box className="stat-tile">
            <span>Health</span>
            <strong>{percent(bundle.health.metrics.memory_health_score)}</strong>
          </Box>
        </Grid>
        <Grid item md={2} sm={4} xs={6}>
          <Box className="stat-tile">
            <span>Drift</span>
            <strong>{percent(bundle.health.metrics.semantic_drift_score)}</strong>
          </Box>
        </Grid>
        <Grid item md={2} sm={4} xs={6}>
          <Box className="stat-tile">
            <span>Task state</span>
            <strong>{percent(bundle.health.metrics.task_state_accuracy)}</strong>
          </Box>
        </Grid>
        <Grid item md={2} sm={4} xs={6}>
          <Box className="stat-tile">
            <span>Attribution</span>
            <strong>{percent(bundle.health.metrics.attribution_accuracy)}</strong>
          </Box>
        </Grid>
        <Grid item md={2} sm={4} xs={6}>
          <Box className="stat-tile">
            <span>Temporal</span>
            <strong>{percent(bundle.health.metrics.temporal_accuracy)}</strong>
          </Box>
        </Grid>
        <Grid item md={2} sm={4} xs={6}>
          <Box className="stat-tile">
            <span>False completion</span>
            <strong>{percent(bundle.health.metrics.false_completion_rate)}</strong>
          </Box>
        </Grid>
      </Grid>

      <Box className="chip-row">
        <Chip color={bundle.health.claim_counts.stale ? "warning" : "default"} label={`${bundle.health.claim_counts.stale} stale`} />
        <Chip color={bundle.health.claim_counts.unsupported ? "error" : "default"} label={`${bundle.health.claim_counts.unsupported} unsupported`} />
        <Chip color={bundle.health.claim_counts.false_completion ? "error" : "default"} label={`${bundle.health.claim_counts.false_completion} false completion`} />
        <Chip color={bundle.verification.decision_counts.block ? "error" : "default"} label={`${bundle.verification.decision_counts.block} blocked`} />
        <Chip color={bundle.verification.decision_counts.needs_verification ? "warning" : "default"} label={`${bundle.verification.decision_counts.needs_verification} needs verification`} />
      </Box>

      <Box className="research-section">
        <Typography component="h2" variant="h6">
          Trace risk timeline
        </Typography>
        <Box className="timeline-grid">
          {riskTimeline.map((point) => (
            <Box className="timeline-point" key={point.label}>
              <Box className="metric-row">
                <Typography variant="body2">{point.label}</Typography>
                <strong>{point.totalRisk}</strong>
              </Box>
              <Box aria-label={`${point.label} risk intensity`} className="timeline-bar">
                <span style={{ width: `${Math.min(100, point.totalRisk * 25)}%` }} />
              </Box>
              <Box className="chip-row">
                <Chip color={point.stale ? "warning" : "default"} label={`${point.stale} stale`} size="small" />
                <Chip color={point.unsupported ? "error" : "default"} label={`${point.unsupported} unsupported`} size="small" />
                <Chip color={point.blocked ? "error" : "default"} label={`${point.blocked} blocked`} size="small" />
                <Chip color={point.needsVerification ? "warning" : "default"} label={`${point.needsVerification} verify`} size="small" />
              </Box>
            </Box>
          ))}
        </Box>
      </Box>

      <Box className="research-section">
        <Box className="panel-heading compact">
          <Box>
            <Typography component="h2" variant="h6">
              Claims
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {claimRows.length} visible claims
            </Typography>
          </Box>
          <FormControl size="small" sx={{ minWidth: 190 }}>
            <InputLabel id="claim-filter-label">Filter</InputLabel>
            <Select
              label="Filter"
              labelId="claim-filter-label"
              onChange={(event) => setClaimFilter(event.target.value as ClaimFilter)}
              value={claimFilter}
            >
              <MenuItem value="all">All</MenuItem>
              <MenuItem value="stale">Stale</MenuItem>
              <MenuItem value="unsupported">Unsupported</MenuItem>
              <MenuItem value="blocked">Blocked</MenuItem>
              <MenuItem value="needs_verification">Needs verification</MenuItem>
            </Select>
          </FormControl>
        </Box>
        <TableContainer className="table-shell">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Claim</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Decision</TableCell>
                <TableCell>Risk</TableCell>
                <TableCell>Sources</TableCell>
                <TableCell>Source seq</TableCell>
                <TableCell>Inspected</TableCell>
                <TableCell>Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {claimRows.map(({ claim, decision }) => {
                const id = claim?.claim_id ?? decision?.claim_id ?? "unknown";
                return (
                  <TableRow key={id}>
                    <TableCell>
                      <Typography variant="body2">{claim?.text ?? decision?.claim_type}</Typography>
                      <Typography color="text.secondary" variant="caption">{id}</Typography>
                    </TableCell>
                    <TableCell>
                      <Box className="chip-row">
                        {claim?.stale ? <Chip color="warning" label="stale" size="small" /> : null}
                        {claim?.support_status ? <Chip label={claim.support_status} size="small" /> : null}
                        {claim?.lost_provenance ? <Chip color="error" label="lost provenance" size="small" /> : null}
                      </Box>
                    </TableCell>
                    <TableCell>
                      {decision ? (
                        <Chip color={decisionColor(decision.decision)} label={decision.decision.replace("_", " ")} size="small" />
                      ) : "-"}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{decision?.risk_level ?? "-"}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography className="mono-cell" variant="caption">
                        {(claim?.source_event_ids ?? decision?.source_event_ids ?? []).join(", ") || "-"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography className="mono-cell" variant="caption">
                        {(claim?.source_event_sequence_numbers ?? []).join(", ") || "-"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography className="mono-cell" variant="caption">
                        {(decision?.inspected_event_ids ?? []).join(", ") || "-"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{decision?.recommended_action ?? bundle.health.recovery_opportunities.find((item) => item.claim_id === id)?.recommended_action ?? "-"}</Typography>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>

      <Box className="research-section">
        <Typography component="h2" variant="h6">
          Baseline vs verified
        </Typography>
        <Grid container spacing={1.5}>
          {Object.entries(bundle.comparison.metric_deltas).map(([metric, delta]) => (
            <Grid item key={metric} md={3} sm={6} xs={12}>
              <Box className="stat-tile">
                <span>{metric.replaceAll("_", " ")}</span>
                <strong>{signedPercent(delta)}</strong>
                <Chip
                  color={chipColor(Math.abs(delta), metric.includes("false") || metric.includes("drift"))}
                  label={`baseline ${percent(bundle.comparison.baseline_metrics[metric as keyof typeof bundle.comparison.baseline_metrics])}`}
                  size="small"
                />
              </Box>
            </Grid>
          ))}
        </Grid>
        <Box className="chip-row">
          <Chip label={`${bundle.comparison.verification_overhead.extra_trace_events} verification events`} />
          <Chip color={bundle.comparison.verification_overhead.blocked_actions ? "error" : "default"} label={`${bundle.comparison.verification_overhead.blocked_actions} blocked actions`} />
        </Box>
      </Box>
    </Box>
  );
}
