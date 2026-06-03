import type { TraceEvent } from "../types/observability";

export function formatDuration(durationMs?: number | null): string {
  if (durationMs == null) {
    return "-";
  }
  if (durationMs < 1000) {
    return `${durationMs} ms`;
  }
  return `${(durationMs / 1000).toFixed(1)} s`;
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4
  }).format(value);
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export function eventLabel(event: TraceEvent): string {
  const data = event.event_data;
  if (event.event_type === "reasoning_step") {
    return `Reasoning: ${String(data.model ?? "unknown model")}`;
  }
  if (event.event_type === "tool_call") {
    return `Tool: ${String(data.tool_name ?? "unknown tool")}`;
  }
  if (event.event_type === "memory_access") {
    return `Memory: ${String(data.memory_type ?? "memory")}`;
  }
  if (event.event_type === "decision_point") {
    return `Decision: ${String(data.decision_type ?? "decision")}`;
  }
  if (event.event_type === "planning_phase") {
    return `Plan: ${String(data.planning_strategy ?? "planning")}`;
  }
  return event.event_type.replaceAll("_", " ");
}

export type StructuredKind = "json" | "xml" | "text";

export function detectStructuredOutput(value: string): StructuredKind {
  const trimmed = value.trim();
  if (!trimmed) {
    return "text";
  }

  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try {
      JSON.parse(trimmed);
      return "json";
    } catch {
      return "text";
    }
  }

  if (/^<([A-Za-z][\w:.-]*)(\s|>|\/>)/.test(trimmed) && /<\/[A-Za-z][\w:.-]*>$|\/>$/.test(trimmed)) {
    return "xml";
  }

  return "text";
}

export function formatStructuredOutput(value: string): string {
  const kind = detectStructuredOutput(value);
  if (kind === "json") {
    return JSON.stringify(JSON.parse(value), null, 2);
  }
  if (kind === "xml") {
    return value
      .replace(/>\s*</g, ">\n<")
      .split("\n")
      .reduce<string[]>((lines, line) => {
        const trimmed = line.trim();
        const previous = lines.length > 0 ? lines[lines.length - 1] : "";
        const previousIndent = previous.match(/^\s*/)?.[0].length ?? 0;
        const closing = trimmed.startsWith("</");
        const selfClosing = trimmed.endsWith("/>");
        const opening = trimmed.startsWith("<") && !closing && !selfClosing && !trimmed.includes("</");
        const indent = closing ? Math.max(previousIndent - 2, 0) : previousIndent;
        lines.push(`${" ".repeat(indent)}${trimmed}`);
        if (opening) {
          lines.push(`${" ".repeat(indent + 2)}`);
        }
        return lines;
      }, [])
      .filter((line) => line.trim().length > 0)
      .join("\n");
  }
  return value;
}

export function highlightParts(text: string, query: string): Array<{ text: string; match: boolean }> {
  if (!query.trim()) {
    return [{ text, match: false }];
  }
  const escaped = query.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`(${escaped})`, "i");
  return text.split(pattern).filter(Boolean).map((part) => ({
    text: part,
    match: pattern.test(part)
  }));
}

export function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

export function toStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string");
  }
  if (typeof value === "string" && value.trim()) {
    return [value];
  }
  return [];
}
