import { apiRequest } from "@/api/http";

export interface EnvironmentCheckItem {
  check_code: string;
  status: string;
  summary: string;
  created_at?: string | null;
}

interface EnvironmentCheckListResponse {
  items: EnvironmentCheckItem[];
}

export function executeEnvironmentChecks(): Promise<EnvironmentCheckListResponse> {
  return apiRequest<EnvironmentCheckListResponse>("/environment/checks/execute", {
    method: "POST",
  });
}

export function fetchLatestEnvironmentChecks(): Promise<EnvironmentCheckListResponse> {
  return apiRequest<EnvironmentCheckListResponse>("/environment/checks/latest");
}
