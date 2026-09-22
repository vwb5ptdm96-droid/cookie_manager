import { apiRequest } from "@/api/http";

export interface AutoRepairTicketItem {
  id: number;
  ticket_code: string;
  channel: string;
  shop_name: string | null;
  cdp_port: number;
  script_code: string | null;
  health_task_code: string | null;
  script_run_id: number | null;
  issue_type: string;
  kind?: string;
  cookie_sync_task_code?: string | null;
  status: string;
  error_message: string | null;
  diagnosis: string | null;
  dispatch_count: number;
  last_dispatched_at: string | null;
  closed_at: string | null;
  created_at: string | null;
  events?: AgentEvent[];
  diff?: string;
  usage?: TokenUsage | null;
  chat?: ChatMessage[];
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  total_tokens: number;
  total_cost_usd?: number | null;
  duration_ms?: number | null;
  num_turns?: number | null;
  model?: string | null;
}

export interface AgentEvent {
  type: "think" | "tool_call" | "screenshot" | "script_diff" | "recheck" | "status" | "usage" | string;
  text: string;
  path?: string;
  usage?: TokenUsage;
}

export interface ChatMessage {
  role: "user" | "assistant" | string;
  text: string;
  ts?: string;
}

export interface AgentStatus {
  counts: Record<string, number>;
  headline: string;
  phase: "idle" | "running" | "pending" | string;
}

interface TicketListResponse {
  items: AutoRepairTicketItem[];
  counts?: Record<string, number>;
}

export function fetchAutoRepairTickets(status?: string): Promise<TicketListResponse> {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<TicketListResponse>(`/auto-repair-tickets${suffix}`);
}

export function fetchAutoRepairTicket(id: number): Promise<AutoRepairTicketItem> {
  return apiRequest<AutoRepairTicketItem>(`/auto-repair-tickets/${id}`);
}

export interface OpsAttentionItem {
  title: string;
  reason: string;
  path: string;
  query?: Record<string, string>;
}

export interface OpsSummary {
  as_of: string;
  window_start: string;
  health: { enabled: number; fail: number };
  cookie_sync: { enabled: number; fail: number; syncing: number; jobs_pending: number };
  script_runs: { running: number; risk: number };
  profiles: { locked: number };
  agent: {
    running: number;
    pending: number;
    solved_today: number;
    need_human: number;
    failed: number;
  };
  attention: OpsAttentionItem[];
}

export function fetchOpsSummary(): Promise<OpsSummary> {
  return apiRequest<OpsSummary>("/agent/ops-summary");
}

export function fetchAgentStatus(): Promise<AgentStatus> {
  return apiRequest<AgentStatus>("/agent/status");
}

export function fetchAgentChat(ticketId?: number): Promise<{ items: ChatMessage[] }> {
  const suffix = ticketId != null ? `?ticket_id=${ticketId}` : "";
  return apiRequest<{ items: ChatMessage[] }>(`/agent/chat${suffix}`);
}

export function sendAgentChat(message: string, ticketId?: number): Promise<{
  reply: string;
  ticket_id: number | null;
  ticket_code: string | null;
  items: ChatMessage[];
}> {
  return apiRequest("/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, ticket_id: ticketId ?? null }),
  });
}

export function fetchSreExplain(): Promise<Record<string, unknown>> {
  return apiRequest("/agent/sre/explain");
}

export function runSreEnvCheck(): Promise<Record<string, unknown>> {
  return apiRequest("/agent/sre/env-check", { method: "POST" });
}

function sreConfirm(path: string): Promise<Record<string, unknown>> {
  return apiRequest(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
}

export function recycleStaleRuns(): Promise<{ reclaimed: number }> {
  return sreConfirm("/agent/sre/recycle-stale-runs") as Promise<{ reclaimed: number }>;
}

export function restartBackend(): Promise<{ scheduled?: boolean; dry_run?: boolean; message?: string }> {
  return sreConfirm("/agent/sre/restart-backend");
}

export function probeBackendHealth(): Promise<{ ok: boolean; status_code?: number }> {
  return apiRequest("/agent/sre/health-probe");
}
