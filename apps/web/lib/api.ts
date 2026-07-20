import type { Role } from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export const WS_URL = API_URL.replace(/^http/, "ws") + "/ws";

const TOKEN_KEY = "cp_token";
const ROLE_KEY = "cp_role";

let memToken: string | null = null;
let memRole: Role | null = null;

export function getToken(): string | null {
  if (memToken) return memToken;
  if (typeof window !== "undefined") {
    memToken = sessionStorage.getItem(TOKEN_KEY);
  }
  return memToken;
}

export function getRole(): Role | null {
  if (memRole) return memRole;
  if (typeof window !== "undefined") {
    const r = sessionStorage.getItem(ROLE_KEY);
    if (r === "owner" || r === "viewer") memRole = r;
  }
  return memRole;
}

export function isOwner(): boolean {
  return getRole() === "owner";
}

export function setSession(token: string, role: string) {
  memToken = token;
  memRole = role === "owner" ? "owner" : "viewer";
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(ROLE_KEY, memRole);
}

export function clearSession() {
  memToken = null;
  memRole = null;
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(ROLE_KEY);
  }
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

interface ApiOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  auth?: boolean;
}

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = opts;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(
      "API unreachable. Is the CareerPilot API running on " + API_URL + "?",
      0
    );
  }

  if (res.status === 401 && auth) {
    clearSession();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new ApiError("Session expired. Sign in again.", 401);
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
      else if (data?.detail) detail = JSON.stringify(data.detail);
    } catch {
      /* keep default */
    }
    throw new ApiError(detail, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
