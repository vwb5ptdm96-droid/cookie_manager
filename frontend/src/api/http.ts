export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  message: string;
  error_code: string | null;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? ((await response.json()) as ApiEnvelope<T>)
    : ({
        success: false,
        data: null as T,
        message: await response.text(),
        error_code: null,
      } satisfies ApiEnvelope<T>);

  if (!response.ok || !payload.success) {
    throw new Error(payload.message || "请求失败");
  }

  return payload.data;
}
