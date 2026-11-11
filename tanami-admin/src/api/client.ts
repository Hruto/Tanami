import type { Page, TokenPair } from "./types";

// Same origin by default: Vite proxies /api in development, and in production
// the dashboard is served next to the API or VITE_API_BASE_URL points at it.
const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const BASE = RAW_BASE.endsWith("/") ? RAW_BASE.slice(0, -1) : RAW_BASE;
const SESSION_KEY = "tanami.admin.session";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | null;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> | null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get field(): string | null {
    const field = this.details?.["field"];
    return typeof field === "string" ? field : null;
  }
}

// The refresh token lives in sessionStorage: it survives a reload but not a
// closed tab, which is the right lifetime for a shared staff computer.
function readSession(): TokenPair | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as TokenPair) : null;
  } catch {
    return null;
  }
}

let session: TokenPair | null = readSession();
let refreshing: Promise<boolean> | null = null;

export function setSession(tokens: TokenPair | null): void {
  session = tokens;
  try {
    if (tokens) sessionStorage.setItem(SESSION_KEY, JSON.stringify(tokens));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // Storage can be blocked; the in-memory session still works for this tab.
  }
}

export function hasSession(): boolean {
  return session !== null;
}

export function currentRefreshToken(): string | null {
  return session?.refresh_token ?? null;
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  auth?: boolean;
}

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const search = params.toString();
  return `${BASE}/api/v1${path}${search ? `?${search}` : ""}`;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.auth !== false && session) headers["Authorization"] = `Bearer ${session.access_token}`;
  return fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

async function refreshSession(): Promise<boolean> {
  if (!session) return false;
  refreshing ??= (async () => {
    try {
      const response = await send("/auth/refresh", {
        method: "POST",
        body: { refresh_token: session?.refresh_token },
        auth: false,
      });
      if (!response.ok) return false;
      const body = (await response.json()) as { data: TokenPair };
      setSession(body.data);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

async function toError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code: string; message: string; details?: Record<string, unknown> | null };
    };
    if (body.error) {
      return new ApiError(response.status, body.error.code, body.error.message, body.error.details ?? null);
    }
  } catch {
    // Not JSON: fall through to a generic message.
  }
  return new ApiError(response.status, "network", "Server tidak menjawab dengan benar. Coba lagi sebentar lagi.", null);
}

async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  let response: Response;
  try {
    response = await send(path, options);
  } catch {
    throw new ApiError(0, "offline", "Tidak dapat terhubung ke server Tanami. Periksa koneksi lalu coba lagi.", null);
  }
  if (response.status === 401 && options.auth !== false && (await refreshSession())) {
    response = await send(path, options);
  }
  if (response.status === 401 && options.auth !== false) {
    setSession(null);
    window.dispatchEvent(new Event("tanami:signed-out"));
  }
  if (!response.ok) throw await toError(response);
  return response;
}

export async function apiGet<T>(path: string, query?: Query): Promise<T> {
  const response = await request(path, { query });
  return ((await response.json()) as { data: T }).data;
}

export async function apiPage<T>(path: string, query?: Query): Promise<Page<T>> {
  const response = await request(path, { query });
  return (await response.json()) as Page<T>;
}

export async function apiSend<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
  auth = true,
): Promise<T> {
  const response = await request(path, { method, body, auth });
  if (response.status === 204) return undefined as T;
  return ((await response.json()) as { data: T }).data;
}
