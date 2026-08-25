import { apiRequest } from "@/api/http";

export interface ScriptRunItem {
  id: number;
  run_id: string;
  health_task_id: number | null;
  health_task_code: string | null;
  health_task_name: string | null;
  script_id: number;
  script_code: string;
  script_name: string | null;
  directory_id: number | null;
  directory_key: string | null;
  run_mode: string;
  script_config: string | null;
  timeout_seconds: number;
  status: string;
  pid: number | null;
  start_time: string | null;
  end_time: string | null;
  duration_ms: number | null;
  artifact_dir: string | null;
  log_file: string | null;
  result_json: string | null;
  error_message: string | null;
  exit_code: number | null;
  control_file: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface ScriptRunListResponse {
  items: ScriptRunItem[];
}

export function fetchScriptRuns(params?: {
  status?: string;
  health_task_code?: string;
  script_code?: string;
  limit?: number;
}): Promise<ScriptRunListResponse> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.health_task_code) query.set("health_task_code", params.health_task_code);
  if (params?.script_code) query.set("script_code", params.script_code);
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiRequest<ScriptRunListResponse>(`/script-runs${qs ? "?" + qs : ""}`);
}

export function fetchRunningScriptRuns(): Promise<ScriptRunListResponse> {
  return apiRequest<ScriptRunListResponse>("/script-runs/running");
}

export function getScriptRun(runId: string): Promise<ScriptRunItem> {
  return apiRequest<ScriptRunItem>(`/script-runs/${runId}`);
}

export function pauseScriptRun(runId: string): Promise<ScriptRunItem> {
  return apiRequest<ScriptRunItem>(`/script-runs/${runId}/pause`, { method: "POST" });
}

export function resumeScriptRun(runId: string): Promise<ScriptRunItem> {
  return apiRequest<ScriptRunItem>(`/script-runs/${runId}/resume`, { method: "POST" });
}

export function cancelScriptRun(runId: string): Promise<ScriptRunItem> {
  return apiRequest<ScriptRunItem>(`/script-runs/${runId}/cancel`, { method: "POST" });
}

export interface LogContent {
  content: string;
  offset: number;
  total_bytes: number;
}

export function readScriptRunLog(runId: string, offset = 0, maxBytes = 65536): Promise<LogContent> {
  return apiRequest<LogContent>(
    `/script-runs/${runId}/log?offset=${offset}&max_bytes=${maxBytes}`,
  );
}

export function readScriptRunResult(runId: string): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/script-runs/${runId}/result`);
}
