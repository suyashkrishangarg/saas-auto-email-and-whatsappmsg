"use client";

export function getApiBase(): string {
  const v = (process.env.NEXT_PUBLIC_API_URL || "").trim();
  if (v) return v.replace(/\/+$/, "");
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    // Same-apex convention: saas.<apex> -> api.<apex>
    if (host.startsWith("saas.")) return `${window.location.protocol}//api.${host.slice(5)}/v1`;
  }
  return "http://localhost:8000/v1";
}

const API_URL = getApiBase();

export type ApiError = { detail?: string | { msg: string }[] };

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
}

export async function api<T = unknown>(
  path: string,
  opts: RequestInit & { json?: unknown } = {}
): Promise<T> {
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let body = opts.body;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  const res = await fetch(`${API_URL}${path}`, { ...opts, headers, body });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
    setToken(null);
    if (!location.pathname.startsWith("/login")) {
      location.href = "/login";
      throw new Error("Session expired");
    }
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const d = data as ApiError;
    const msg =
      typeof d?.detail === "string"
        ? d.detail
        : Array.isArray(d?.detail)
          ? d.detail.map((e) => (typeof e === "string" ? e : e.msg)).join("; ")
          : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data as T;
}

// ---- shared types ----
export type User = {
  id: string;
  email: string;
  full_name: string | null;
  role: "SUPER_ADMIN" | "CONSULTANT";
  phone: string | null;
  auth_method: "OAUTH" | "FORWARDING" | "BOTH";
  forwarding_alias: string | null;
  forwarding_verification_code: string | null;
  is_active: boolean;
  created_at: string;
};

export type ClientRow = {
  id: string;
  name: string;
  phone: string | null;
  gstin: string;
  created_at: string;
};

export type Notice = {
  id: string;
  client_id: string | null;
  raw_subject: string | null;
  sender: string | null;
  extracted_gstin: string | null;
  notice_form: string | null;
  financial_year: string | null;
  tax_period: string | null;
  demand_amount: string | number | null;
  due_date: string | null;
  summary: string | null;
  status: "PROCESSED" | "UNMATCHED" | "FAILED";
  error_message: string | null;
  processing_latency_ms: number | null;
  source: string | null;
  created_at: string;
};

export type BulkResult = {
  created: number;
  updated: number;
  errors: { row: number; gstin: string; error: string }[];
};

export type AdminMetrics = {
  consultants: number;
  active_consultants: number;
  suspended: number;
  clients: number;
  notices_total: number;
  notices_24h: number;
  unmatched: number;
  whatsapp_sent: number;
  whatsapp_failed: number;
  avg_latency_ms: number | null;
};

export type AdminUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  phone: string | null;
  auth_method: string;
  forwarding_alias: string | null;
  is_active: boolean;
  client_count: number;
  notice_count: number;
  whatsapp_sent: number;
  whatsapp_failed: number;
  avg_latency_ms: number | null;
  connection_status: string | null;
  created_at: string | null;
};

export type SettingEntry = {
  value: string | null;
  is_secret: boolean;
  updated_at: string | null;
  has_value: boolean;
};

export type LogEntry = {
  type: "EMAIL" | "WHATSAPP";
  id: string;
  at: string | null;
  subject?: string;
  sender?: string;
  source?: string;
  gstin?: string | null;
  status?: string;
  latency_ms?: number | null;
  error?: string | null;
  recipient_type?: string;
  phone?: string;
  provider?: string | null;
  message_id?: string | null;
  notice_id?: string;
};

// ---- simple client-side checks (NO regex anywhere, per product spec) ----
function allAlnum(v: string): boolean {
  for (const ch of v) {
    const isDigit = ch >= "0" && ch <= "9";
    const isUpper = ch >= "A" && ch <= "Z";
    if (!isDigit && !isUpper) return false;
  }
  return true;
}

function allDigits(v: string): boolean {
  for (const ch of v) {
    if (ch < "0" || ch > "9") return false;
  }
  return true;
}

export function checkGstin(v: string): string | null {
  const g = (v || "").trim().toUpperCase();
  if (g.length !== 15) return "GSTIN must be exactly 15 characters";
  if (!allAlnum(g)) return "GSTIN must be letters and digits only";
  return null;
}

export function checkPhone(v: string): string | null {
  if (!v || !v.trim()) return null;
  let p = "";
  for (const ch of v.trim()) {
    if (ch !== " " && ch !== "-" && ch !== ".") p += ch;
  }
  if (p.startsWith("+91")) p = p.slice(3);
  if (p.length === 12 && p.startsWith("91")) p = p.slice(2);
  if (p.length !== 10 || !allDigits(p)) return "Phone must be 10 digits (optional +91)";
  return null;
}
