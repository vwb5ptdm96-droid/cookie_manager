import { apiRequest } from "@/api/http";

export interface DeployConfigPayload {
  deploy_root: string;
  runtime_root: string;
  startup_command: string;
  api_host: string;
  api_port: number;
  current_user: string;
  current_user_hint: string;
  directories: Record<string, string>;
}

export function fetchDeployConfig(): Promise<DeployConfigPayload> {
  return apiRequest<DeployConfigPayload>("/deploy/config");
}
