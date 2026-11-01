export type Json = Record<string, unknown>;

let csrfToken = "";

export function setCsrfToken(token: string) {
  csrfToken = token;
}

export function getCsrfToken() {
  return csrfToken;
}

export async function api<T = Json>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken && options.method && options.method !== "GET") {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const res = await fetch(path, {
    ...options,
    headers,
    credentials: "include",
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    let detail = res.statusText;
    if (typeof data === "object" && data && "detail" in data) {
      const d = (data as { detail: unknown }).detail;
      if (typeof d === "string") detail = d;
      else if (d && typeof d === "object" && "message_vi" in d) {
        detail = String((d as { message_vi: string }).message_vi);
      } else detail = JSON.stringify(d);
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data as T;
}
