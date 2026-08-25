import { apiRequest } from "@/api/http";

export type LogRunType = "CHECK" | "SCRIPT" | "PROFILE" | "REPAIR" | "ENV" | "TASK" | "SYSTEM";
export type LogStatus = "RUNNING" | "SUCCESS" | "FAIL" | "RISK" | "WARN";

export interface LogItem {
  run_id: string;
  run_type: LogRunType;
  task_id: number | null;
  check_id: number | null;
  ticket_id: number | null;
  status: LogStatus;
  title: string;
  message: string;
  log_file_path: string | null;
  created_at: string;
}

interface LogListResponse {
  items: LogItem[];
}

export interface LogFilters {
  runType: string;
  status: string;
  taskId: string;
  checkId: string;
  ticketId: string;
  healthTaskCode: string;
  runId: string;
  keyword: string;
  startAt: string;
  endAt: string;
}

export function fetchLogs(filters: LogFilters): Promise<LogListResponse> {
  const params = new URLSearchParams();
  if (filters.runType) params.set("run_type", filters.runType);
  if (filters.status) params.set("status", filters.status);
  if (filters.taskId) params.set("task_id", filters.taskId);
  if (filters.checkId) params.set("check_id", filters.checkId);
  if (filters.ticketId) params.set("ticket_id", filters.ticketId);
  if (filters.healthTaskCode) params.set("health_task_code", filters.healthTaskCode);
  if (filters.runId) params.set("run_id", filters.runId);
  if (filters.keyword) params.set("keyword", filters.keyword);
  if (filters.startAt) params.set("start_at", filters.startAt);
  if (filters.endAt) params.set("end_at", filters.endAt);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<LogListResponse>(`/logs${suffix}`);
}
