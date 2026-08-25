import { apiRequest } from "@/api/http";

export interface ScriptItem {
  id: number;
  script_code: string;
  script_name: string;
  script_type: string;
  platform: string;
  version: string | null;
  profile_key: string | null;
  script_dir: string;
  absolute_dir: string;
  main_file: string;
  enabled: boolean;
  default_run_mode: string | null;
  default_cdp_port: number | null;
  supports_pause: boolean;
  supports_cancel: boolean;
  default_timeout_seconds: number;
  description: string | null;
  updated_at: string | null;
}

export interface ScriptUploadPayload {
  scriptName: string;
  scriptType: string;
  platform: string;
  description: string;
  profileKey?: string | null;
  file: File;
}

export interface ScriptRunConfigPayload {
  default_run_mode?: string | null;
  default_cdp_port?: number | null;
  supports_pause?: boolean;
  supports_cancel?: boolean;
  default_timeout_seconds?: number;
}

interface ScriptListResponse {
  items: ScriptItem[];
}

export function fetchScripts(): Promise<ScriptListResponse> {
  return apiRequest<ScriptListResponse>("/scripts");
}

export function uploadScript(payload: ScriptUploadPayload): Promise<ScriptItem> {
  const formData = new FormData();
  formData.append("script_name", payload.scriptName);
  formData.append("script_code", "");
  formData.append("script_type", payload.scriptType);
  formData.append("platform", payload.platform);
  formData.append("version", "");
  formData.append("description", payload.description.trim());
  if (payload.profileKey) formData.append("profile_key", payload.profileKey);
  formData.append("script_file", payload.file);

  return apiRequest<ScriptItem>("/scripts/upload", {
    method: "POST",
    body: formData,
  });
}

export function updateScriptProfile(scriptCode: string, profileKey: string | null): Promise<ScriptItem> {
  return apiRequest<ScriptItem>(`/scripts/${scriptCode}/profile`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_key: profileKey }),
  });
}

export function toggleScript(scriptCode: string, enabled: boolean): Promise<ScriptItem> {
  return apiRequest<ScriptItem>(`/scripts/${scriptCode}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

export function updateScriptRunConfig(scriptCode: string, payload: ScriptRunConfigPayload): Promise<ScriptItem> {
  return apiRequest<ScriptItem>(`/scripts/${scriptCode}/run-config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchScriptFiles(scriptCode: string): Promise<string[]> {
  return apiRequest<string[]>(`/scripts/${scriptCode}/files`);
}

export function updateScriptMainFile(scriptCode: string, mainFile: string): Promise<ScriptItem> {
  return apiRequest<ScriptItem>(`/scripts/${scriptCode}/main-file`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ main_file: mainFile }),
  });
}

export function deleteScript(scriptCode: string): Promise<void> {
  return apiRequest<void>(`/scripts/${scriptCode}`, { method: "DELETE" });
}

export interface CdpPortStatus {
  port: number;
  script_name: string;
  script_code: string;
  in_use: boolean;
}

export function fetchCdpPortStatus(): Promise<CdpPortStatus[]> {
  return apiRequest<CdpPortStatus[]>("/scripts/cdp-port-status");
}

export function cloneScript(scriptCode: string): Promise<ScriptItem> {
  return apiRequest<ScriptItem>(`/scripts/${scriptCode}/clone`, {
    method: "POST",
  });
}

export function updateScript(
  scriptCode: string,
  payload: { script_name?: string; script_type?: string; platform?: string; description?: string | null },
): Promise<ScriptItem> {
  return apiRequest<ScriptItem>(`/scripts/${scriptCode}/update`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
