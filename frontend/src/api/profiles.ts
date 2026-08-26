import { apiRequest } from "@/api/http";

export interface ProfileItem {
  id: number;
  profile_key: string;
  relative_path: string;
  absolute_path: string;
  status: string;
  is_locked: boolean;
  lock_owner: string | null;
  debug_port: number | null;
  note: string | null;
  last_verified_at: string | null;
  updated_at: string | null;
}

interface ProfileListResponse {
  items: ProfileItem[];
}

export interface ProfileUpsertPayload {
  profile_key: string;
  relative_path: string;
  debug_port: number | null;
  note: string;
}

export interface ProfileDebugOpenResult {
  profile_key: string;
  port: number;
  cdp_url: string;
  chrome_path: string;
  already_running: boolean;
}

export function fetchProfiles(): Promise<ProfileListResponse> {
  return apiRequest<ProfileListResponse>("/profiles");
}

export function createProfile(payload: ProfileUpsertPayload): Promise<ProfileItem> {
  return apiRequest<ProfileItem>("/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function lockProfile(profileKey: string, owner: string): Promise<ProfileItem> {
  return apiRequest<ProfileItem>(`/profiles/${profileKey}/lock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner }),
  });
}

export function unlockProfile(profileKey: string): Promise<ProfileItem> {
  return apiRequest<ProfileItem>(`/profiles/${profileKey}/unlock`, {
    method: "POST",
  });
}

export function verifyProfile(profileKey: string): Promise<ProfileItem> {
  return apiRequest<ProfileItem>(`/profiles/${profileKey}/verify`, {
    method: "POST",
  });
}

export function updateProfile(profileKey: string, payload: ProfileUpsertPayload): Promise<ProfileItem> {
  return apiRequest<ProfileItem>(`/profiles/${profileKey}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteProfile(profileKey: string): Promise<void> {
  return apiRequest<void>(`/profiles/${profileKey}`, {
    method: "DELETE",
  });
}

export function openProfileDebug(profileKey: string): Promise<ProfileDebugOpenResult> {
  return apiRequest<ProfileDebugOpenResult>(`/profiles/${profileKey}/debug/open`, {
    method: "POST",
  });
}

export function closeProfileDebug(profileKey: string): Promise<{ profile_key: string; port: number; closed: boolean }> {
  return apiRequest<{ profile_key: string; port: number; closed: boolean }>(`/profiles/${profileKey}/debug/close`, {
    method: "POST",
  });
}
