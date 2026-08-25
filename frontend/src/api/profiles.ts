import { apiRequest } from "@/api/http";

export interface ProfileItem {
  id: number;
  profile_key: string;
  task_id: number | null;
  relative_path: string;
  absolute_path: string;
  status: string;
  is_locked: boolean;
  lock_owner: string | null;
  note: string | null;
  last_verified_at: string | null;
  updated_at: string | null;
}

interface ProfileListResponse {
  items: ProfileItem[];
}

export interface ProfileUpsertPayload {
  profile_key: string;
  task_id: number | null;
  relative_path: string;
  note: string;
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
