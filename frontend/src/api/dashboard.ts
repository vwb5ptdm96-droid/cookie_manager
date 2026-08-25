import { apiRequest } from "@/api/http";

export interface DashboardLogItem {
  run_id: string;
  run_type: string;
  status: string;
  title: string;
  message: string;
  created_at: string;
}

export interface DashboardCheckItem {
  check_code: string;
  check_name: string;
  status: string;
  last_result_message: string | null;
  last_checked_at: string | null;
  updated_at: string | null;
}

export interface DashboardPayload {
  stats: {
    tasks: number;
    profiles: number;
    checks: number;
    pending_repairs: number;
  };
  recent_logs: DashboardLogItem[];
  recent_checks: DashboardCheckItem[];
}

export function fetchDashboard(): Promise<DashboardPayload> {
  return apiRequest<DashboardPayload>("/dashboard");
}
