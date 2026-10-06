export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    let code: string | undefined;
    try {
      const body = await response.json();
      message = body.error?.message ?? body.detail?.message ?? body.detail ?? message;
      code = body.error?.code ?? body.detail?.code;
    } catch { /* Keep the readable fallback for non-JSON responses. */ }
    throw new ApiError(typeof message === "string" ? message : "Please check the information and try again.", response.status, code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function jsonBody(value: unknown): Pick<RequestInit, "method" | "body"> {
  return { method: "POST", body: JSON.stringify(value) };
}

export function resolveMediaUrl(playbackUrl: string | null | undefined): string | null {
  if (!playbackUrl) return null;
  if (/^[a-z][a-z0-9+.-]*:/i.test(playbackUrl)) return playbackUrl;
  return `${API_URL}${playbackUrl.startsWith("/") ? "" : "/"}${playbackUrl}`;
}
