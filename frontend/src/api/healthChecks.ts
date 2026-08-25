import { apiRequest } from "@/api/http";

export interface HealthCheckItem {
  id: number;
  check_code: string;
  check_name: string;
  cookie_table: string;
  channel: string;
  shop_name: string;
  mobile_phone: string;
  dns: string;
  method: string;
  check_url: string;
  request_headers: Record<string, unknown>;
  request_body: Record<string, unknown>;
  success_rule: Record<string, unknown>;
  failure_rule: Record<string, unknown>;
  trigger_task_id: number;
  trigger_task_code: string | null;
  status: string;
  enabled: boolean;
  last_result_message: string | null;
  last_checked_at: string | null;
  updated_at: string | null;
  triggered_task_code?: string | null;
}

interface HealthCheckListResponse {
  items: HealthCheckItem[];
}

export interface HealthCheckCreatePayload {
  check_name: string;
  cookie_table: string;
  channel: string;
  shop_name: string;
  mobile_phone: string;
  dns: string;
  method: string;
  check_url: string;
  request_headers: Record<string, unknown>;
  request_body: Record<string, unknown>;
  success_rule: Record<string, unknown>;
  failure_rule: Record<string, unknown>;
  trigger_task_id: number;
}

export function fetchHealthChecks(): Promise<HealthCheckListResponse> {
  return apiRequest<HealthCheckListResponse>("/health-checks");
}

export function createHealthCheck(payload: HealthCheckCreatePayload): Promise<HealthCheckItem> {
  return apiRequest<HealthCheckItem>("/health-checks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateHealthCheck(checkCode: string, payload: HealthCheckCreatePayload): Promise<HealthCheckItem> {
  return apiRequest<HealthCheckItem>(`/health-checks/${checkCode}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function executeHealthCheck(checkCode: string): Promise<HealthCheckItem> {
  return apiRequest<HealthCheckItem>(`/health-checks/${checkCode}/execute`, {
    method: "POST",
  });
}

export function executeAllHealthChecks(): Promise<HealthCheckListResponse> {
  return apiRequest<HealthCheckListResponse>("/health-checks/execute-all", {
    method: "POST",
  });
}

export function toggleHealthCheck(checkCode: string, enabled: boolean): Promise<HealthCheckItem> {
  return apiRequest<HealthCheckItem>(`/health-checks/${checkCode}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}
