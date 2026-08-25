import { apiRequest } from "@/api/http";

export interface HealthTaskItem {
  id: number;
  health_task_code: string;
  health_task_name: string;
  enabled: boolean;
  cookie_table: string;
  channel: string;
  shop_name: string | null;
  mobile_phone: string | null;
  dns: string | null;
  check_url: string;
  http_method: string;
  http_headers: string | null;
  http_body: string | null;
  success_rule: string | null;
  failure_rule: string | null;
  cron_expression: string | null;
  check_timeout_seconds: number;
  retry_count: number;
  last_checked_at: string | null;
  next_run_at: string | null;
  auto_repair_enabled: boolean;
  repair_cron_expression: string | null;
  repair_script_id: number | null;
  repair_directory_id: number | null;
  repair_run_mode: string | null;
  repair_script_config: string | null;
  repair_timeout_seconds: number;
  status: string;
  last_run_status: string | null;
  last_result_message: string | null;
  last_repaired_at: string | null;
  last_repair_run_id: string | null;
  updated_at: string | null;
}

export interface HealthTaskCreatePayload {
  health_task_name: string;
  cookie_table?: string;
  channel: string;
  shop_name?: string | null;
  mobile_phone?: string | null;
  dns?: string | null;
  check_url: string;
  http_method?: string;
  http_headers?: string | null;
  http_body?: string | null;
  success_rule?: string | null;
  failure_rule?: string | null;
  cron_expression?: string | null;
  check_timeout_seconds?: number;
  retry_count?: number;
  auto_repair_enabled?: boolean;
  repair_cron_expression?: string | null;
  repair_script_id?: number | null;
  repair_directory_id?: number | null;
  repair_run_mode?: string | null;
  repair_script_config?: string | null;
  repair_timeout_seconds?: number;
}

export type HealthTaskUpdatePayload = Partial<HealthTaskCreatePayload>;

interface HealthTaskListResponse {
  items: HealthTaskItem[];
}

export function fetchHealthTasks(): Promise<HealthTaskListResponse> {
  return apiRequest<HealthTaskListResponse>("/health-tasks");
}

export function getHealthTask(code: string): Promise<HealthTaskItem> {
  return apiRequest<HealthTaskItem>(`/health-tasks/${code}`);
}

export function createHealthTask(payload: HealthTaskCreatePayload): Promise<HealthTaskItem> {
  return apiRequest<HealthTaskItem>("/health-tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateHealthTask(code: string, payload: HealthTaskUpdatePayload): Promise<HealthTaskItem> {
  return apiRequest<HealthTaskItem>(`/health-tasks/${code}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function toggleHealthTask(code: string, enabled: boolean): Promise<HealthTaskItem> {
  return apiRequest<HealthTaskItem>(`/health-tasks/${code}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

export function executeHealthTaskCheck(code: string): Promise<HealthTaskItem> {
  return apiRequest<HealthTaskItem>(`/health-tasks/${code}/check`, {
    method: "POST",
  });
}

export function executeHealthTaskRepair(code: string): Promise<HealthTaskItem> {
  return apiRequest<HealthTaskItem>(`/health-tasks/${code}/repair`, {
    method: "POST",
  });
}

export interface TimelineEntry {
  time: string;
  action: string;
  action_type: "check" | "repair";
  result: string;
  detail: string;
}

export function fetchHealthTaskTimeline(code: string): Promise<TimelineEntry[]> {
  return apiRequest<TimelineEntry[]>(`/health-tasks/${code}/timeline`);
}

export function deleteHealthTask(code: string): Promise<void> {
  return apiRequest<void>(`/health-tasks/${code}`, {
    method: "DELETE",
  });
}

export function cloneHealthTask(code: string): Promise<HealthTaskItem> {
  return apiRequest<HealthTaskItem>(`/health-tasks/${code}/clone`, {
    method: "POST",
  });
}
