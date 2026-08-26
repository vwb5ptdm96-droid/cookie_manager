import { apiRequest } from "@/api/http";

export interface CookieSyncTaskItem {
  id: number;
  cookie_sync_task_code: string;
  cookie_sync_task_name: string;
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
  sync_wait_timeout_seconds: number;
  status: string;
  last_run_status: string | null;
  last_result_message: string | null;
  last_checked_at: string | null;
  last_sync_at: string | null;
  sync_deadline_at: string | null;
  updated_at: string | null;
}

export interface CookieSyncTaskCreatePayload {
  cookie_sync_task_name: string;
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
  sync_wait_timeout_seconds?: number;
}

export type CookieSyncTaskUpdatePayload = Partial<CookieSyncTaskCreatePayload>;

interface CookieSyncTaskListResponse {
  items: CookieSyncTaskItem[];
}

export function fetchCookieSyncTasks(): Promise<CookieSyncTaskListResponse> {
  return apiRequest<CookieSyncTaskListResponse>("/cookie-sync-tasks");
}

export function getCookieSyncTask(code: string): Promise<CookieSyncTaskItem> {
  return apiRequest<CookieSyncTaskItem>(`/cookie-sync-tasks/${code}`);
}

export function createCookieSyncTask(payload: CookieSyncTaskCreatePayload): Promise<CookieSyncTaskItem> {
  return apiRequest<CookieSyncTaskItem>("/cookie-sync-tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateCookieSyncTask(
  code: string,
  payload: CookieSyncTaskUpdatePayload,
): Promise<CookieSyncTaskItem> {
  return apiRequest<CookieSyncTaskItem>(`/cookie-sync-tasks/${code}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function toggleCookieSyncTask(code: string, enabled: boolean): Promise<CookieSyncTaskItem> {
  return apiRequest<CookieSyncTaskItem>(`/cookie-sync-tasks/${code}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

export function executeCookieSyncTaskCheck(code: string): Promise<CookieSyncTaskItem> {
  return apiRequest<CookieSyncTaskItem>(`/cookie-sync-tasks/${code}/check`, {
    method: "POST",
  });
}

export function deleteCookieSyncTask(code: string): Promise<void> {
  return apiRequest<void>(`/cookie-sync-tasks/${code}`, {
    method: "DELETE",
  });
}

export function cloneCookieSyncTask(code: string): Promise<CookieSyncTaskItem> {
  return apiRequest<CookieSyncTaskItem>(`/cookie-sync-tasks/${code}/clone`, {
    method: "POST",
  });
}
