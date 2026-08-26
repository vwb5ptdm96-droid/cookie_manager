import { apiRequest } from "@/api/http";

export interface CookieSyncMappingItem {
  id: number;
  worker_id: string;
  domain: string;
  channel: string;
  shop_name: string | null;
  mobile_phone: string | null;
  dns: string;
  remark: string | null;
  last_report_at: string | null;
  last_report_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface CookieSyncMappingCreatePayload {
  worker_id: string;
  domain: string;
  channel: string;
  shop_name?: string | null;
  mobile_phone?: string | null;
  dns: string;
  remark?: string | null;
}

export type CookieSyncMappingUpdatePayload = Partial<CookieSyncMappingCreatePayload>;

interface CookieSyncMappingListResponse {
  items: CookieSyncMappingItem[];
}

export function fetchCookieSyncMappings(): Promise<CookieSyncMappingListResponse> {
  return apiRequest<CookieSyncMappingListResponse>("/cookie-sync-mappings");
}

export function createCookieSyncMapping(payload: CookieSyncMappingCreatePayload): Promise<CookieSyncMappingItem> {
  return apiRequest<CookieSyncMappingItem>("/cookie-sync-mappings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateCookieSyncMapping(
  id: number,
  payload: CookieSyncMappingUpdatePayload,
): Promise<CookieSyncMappingItem> {
  return apiRequest<CookieSyncMappingItem>(`/cookie-sync-mappings/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteCookieSyncMapping(id: number): Promise<void> {
  return apiRequest<void>(`/cookie-sync-mappings/${id}`, {
    method: "DELETE",
  });
}
