/** Thin fetch wrapper for the FastAPI backend (proxied via Next rewrites).
 * Auth rides an httpOnly cookie the browser attaches automatically
 * (same-origin); a 401 clears the stored profile so the login gate takes
 * over. */

import { clearSession } from "@/lib/user";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly plaidErrorCode?: string;

  constructor(status: number, detail: string, plaidErrorCode?: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.plaidErrorCode = plaidErrorCode;
  }
}

type QueryValue = string | number | boolean | undefined | null;

function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = `Request failed with status ${response.status}`;
  let plaidErrorCode: string | undefined;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body.detail)) {
      // FastAPI validation errors (422)
      detail = body.detail
        .map((e: { msg?: string }) => e.msg)
        .filter(Boolean)
        .join("; ");
    }
    if (typeof body.plaid_error_code === "string") {
      plaidErrorCode = body.plaid_error_code;
    }
  } catch {
    // non-JSON body; keep the generic message
  }
  return new ApiError(response.status, detail, plaidErrorCode);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is the backend running?");
  }
  if (!response.ok) {
    // expired/invalid cookie: drop the profile so the login gate renders
    // (auth endpoints themselves 401 on bad credentials — no session to drop)
    if (response.status === 401 && !path.startsWith("/auth/")) {
      clearSession();
    }
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function apiGet<T>(
  path: string,
  params: Record<string, QueryValue> = {},
): Promise<T> {
  return request<T>(`${path}${buildQuery(params)}`);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
