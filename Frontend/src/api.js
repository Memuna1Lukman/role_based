const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status, requestId) { super(message); this.status = status; this.requestId = requestId; }
}

export async function api(path, options = {}, retry = true) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  if (response.status === 401 && retry && path !== "/auth/refresh") {
    const refresh = await fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refresh.ok) return api(path, options, false);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.error?.message || "Something went wrong. Please try again.", response.status, body?.error?.request_id);
  }
  return response.status === 204 ? null : response.json();
}

export function websocketUrl() {
  const url = new URL(API_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws";
  return url.toString();
}
