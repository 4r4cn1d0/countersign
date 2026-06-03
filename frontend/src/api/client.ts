import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig
} from "axios";
import type {
  AggregateMetrics,
  ExecutionGraphResponse,
  Session,
  SessionListResponse,
  SessionSearchRequest,
  SessionMetrics,
  TimeSeriesMetrics,
  TraceResponse,
  MemoryHealthReport
} from "../types/observability";
import { getStoredAuthToken } from "./authToken";

export interface ApiClientOptions {
  baseURL?: string;
  tokenProvider?: () => string | null;
  maxRetries?: number;
  retryDelayMs?: number;
}

type RetryableConfig = InternalAxiosRequestConfig & {
  __retryCount?: number;
};

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

function isRetryable(error: AxiosError): boolean {
  if (!error.config) {
    return false;
  }
  if (!error.response) {
    return true;
  }
  return error.response.status >= 500 || error.response.status === 429;
}

function sleep(delayMs: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, delayMs));
}

export class AgentObserverApiClient {
  readonly axios: AxiosInstance;

  private readonly tokenProvider: () => string | null;

  private readonly maxRetries: number;

  private readonly retryDelayMs: number;

  constructor(options: ApiClientOptions = {}) {
    this.tokenProvider = options.tokenProvider ?? getStoredAuthToken;
    this.maxRetries = options.maxRetries ?? 2;
    this.retryDelayMs = options.retryDelayMs ?? 250;

    this.axios = axios.create({
      baseURL: options.baseURL ?? defaultBaseUrl,
      timeout: 15000
    });

    this.axios.interceptors.request.use((config) => {
      const token = this.tokenProvider();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    this.axios.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const config = error.config as RetryableConfig | undefined;
        if (!config || !isRetryable(error)) {
          throw error;
        }

        config.__retryCount = config.__retryCount ?? 0;
        if (config.__retryCount >= this.maxRetries) {
          throw error;
        }

        config.__retryCount += 1;
        await sleep(this.retryDelayMs * 2 ** (config.__retryCount - 1));
        return this.axios.request(config);
      }
    );
  }

  listSessions(params: {
    status?: string;
    agent_type?: string;
    limit?: number;
    offset?: number;
    sort?: string;
  } = {}): Promise<SessionListResponse> {
    return this.request<SessionListResponse>({ method: "GET", url: "/sessions", params });
  }

  searchSessions(request: SessionSearchRequest): Promise<SessionListResponse> {
    return this.request<SessionListResponse>({ method: "POST", url: "/sessions/search", data: request });
  }

  getSession(sessionId: string): Promise<Session> {
    return this.request<Session>({ method: "GET", url: `/sessions/${sessionId}` });
  }

  getTrace(sessionId: string, params: { page?: number; page_size?: number } = {}): Promise<TraceResponse> {
    return this.request<TraceResponse>({ method: "GET", url: `/sessions/${sessionId}/trace`, params });
  }

  getGraph(sessionId: string): Promise<ExecutionGraphResponse> {
    return this.request<ExecutionGraphResponse>({ method: "GET", url: `/sessions/${sessionId}/graph` });
  }

  getSessionMetrics(sessionId: string): Promise<SessionMetrics> {
    return this.request<SessionMetrics>({ method: "GET", url: `/sessions/${sessionId}/metrics` });
  }

  getAggregateMetrics(days = 7): Promise<AggregateMetrics> {
    return this.request<AggregateMetrics>({ method: "GET", url: "/metrics/aggregate", params: { days } });
  }

  getTimeSeriesMetrics(params: {
    metric?: "cost" | "duration" | "tokens" | "success_rate";
    days?: number;
    bucket_hours?: number;
  } = {}): Promise<TimeSeriesMetrics> {
    return this.request<TimeSeriesMetrics>({ method: "GET", url: "/metrics/timeseries", params });
  }

  createMemoryHealthReport(request: {
    run: Record<string, unknown>;
    task?: Record<string, unknown>;
  }): Promise<MemoryHealthReport> {
    return this.request<MemoryHealthReport>({ method: "POST", url: "/research/memory-health", data: request });
  }

  private async request<T>(config: AxiosRequestConfig): Promise<T> {
    const response = await this.axios.request<T>(config);
    return response.data;
  }
}

export const apiClient = new AgentObserverApiClient();
