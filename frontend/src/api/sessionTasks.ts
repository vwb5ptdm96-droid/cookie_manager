import { apiRequest } from "@/api/http";

export interface SessionTaskItem {
  id: number;
  task_code: string;
  task_name: string;
  channel: string;
  mobile_phone: string;
  account_alias: string | null;
  related_dns: string[];
  script_code: string;
  script_name: string;
  script_type: string;
  platform: string;
  profile_key: string;
  profile_relative_path: string;
  profile_absolute_path: string;
  schedule_type: string;
  schedule_value: string | null;
  script_config: Record<string, unknown>;
  script_dir: string;
  script_main_file: string;
  health_check_codes: string[];
  status: string;
  enabled: boolean;
  last_run_status: string | null;
  last_run_id: string | null;
  last_error: string | null;
  last_artifact_dir: string | null;
  last_run_at: string | null;
  updated_at: string | null;
  artifact_dir?: string | null;
}

interface SessionTaskListResponse {
  items: SessionTaskItem[];
}

export interface SessionTaskCreatePayload {
  task_name: string;
  channel: string;
  mobile_phone: string;
  account_alias: string;
  related_dns: string[];
  script_code: string;
  profile_key: string;
  schedule_type: string;
  schedule_value: string;
  script_config: Record<string, unknown>;
  notes?: string;
}

export function fetchSessionTasks(): Promise<SessionTaskListResponse> {
  return apiRequest<SessionTaskListResponse>("/session-tasks");
}

export function createSessionTask(payload: SessionTaskCreatePayload): Promise<SessionTaskItem> {
  return apiRequest<SessionTaskItem>("/session-tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateSessionTask(taskCode: string, payload: SessionTaskCreatePayload): Promise<SessionTaskItem> {
  return apiRequest<SessionTaskItem>(`/session-tasks/${taskCode}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function executeSessionTask(taskCode: string): Promise<SessionTaskItem> {
  return apiRequest<SessionTaskItem>(`/session-tasks/${taskCode}/execute`, {
    method: "POST",
  });
}

export function toggleSessionTask(taskCode: string, enabled: boolean): Promise<SessionTaskItem> {
  return apiRequest<SessionTaskItem>(`/session-tasks/${taskCode}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}
