"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminMetrics, AdminUser, api } from "@/lib/api";

export default function AdminHomePage() {
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, u] = await Promise.all([
        api<AdminMetrics>("/admin/metrics"),
        api<AdminUser[]>("/admin/users"),
      ]);
      setMetrics(m);
      setUsers(u);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleActive = async (u: AdminUser) => {
    try {
      await api(`/admin/users/${u.id}`, {
        method: "PATCH",
        json: { is_active: !u.is_active },
      });
      setMsg(`${u.email} ${u.is_active ? "suspended" : "activated"}`);
      await load();
    } catch (e) {
      setMsg(`Failed: ${(e as Error).message}`);
    }
    setTimeout(() => setMsg(null), 4000);
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <MetricCard label="Consultants" value={metrics?.consultants} />
        <MetricCard label="Active" value={metrics?.active_consultants} tone="text-emerald-600" />
        <MetricCard label="Suspended" value={metrics?.suspended} tone="text-red-600" />
        <MetricCard label="Clients" value={metrics?.clients} />
        <MetricCard label="Notices 24h" value={metrics?.notices_24h} />
        <MetricCard label="Notices total" value={metrics?.notices_total} />
        <MetricCard label="Unmatched" value={metrics?.unmatched} tone="text-amber-600" />
        <MetricCard label="WhatsApp sent" value={metrics?.whatsapp_sent} tone="text-emerald-600" />
        <MetricCard label="WhatsApp failed" value={metrics?.whatsapp_failed} tone="text-red-600" />
        <MetricCard
          label="Avg latency"
          value={metrics?.avg_latency_ms != null ? `${Math.round(metrics.avg_latency_ms)} ms` : null}
        />
      </div>

      {msg && (
        <div className="rounded-md border border-brand-100 bg-brand-50 px-3 py-2 text-sm text-brand-700">
          {msg}
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full min-w-[1000px] border-collapse">
          <thead>
            <tr>
              <th className="th">Consultant</th>
              <th className="th">Channel</th>
              <th className="th">Connection</th>
              <th className="th">Clients</th>
              <th className="th">Notices</th>
              <th className="th">WA Sent</th>
              <th className="th">WA Failed</th>
              <th className="th">Avg latency</th>
              <th className="th">Status</th>
              <th className="th">Action</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-slate-50/60">
                <td className="td">
                  <p className="font-medium">{u.full_name || u.email}</p>
                  <p className="text-xs text-slate-400">{u.email}</p>
                </td>
                <td className="td">
                  <span className="badge border border-slate-200 bg-slate-50 text-slate-600">
                    {u.auth_method}
                  </span>
                  {u.role === "SUPER_ADMIN" && (
                    <span className="badge ml-1 border border-purple-200 bg-purple-50 text-purple-700">ADMIN</span>
                  )}
                </td>
                <td className="td text-sm text-slate-500">{u.connection_status ?? "-"}</td>
                <td className="td">{u.client_count}</td>
                <td className="td">{u.notice_count}</td>
                <td className="td text-emerald-600">{u.whatsapp_sent}</td>
                <td className="td text-red-600">{u.whatsapp_failed}</td>
                <td className="td text-slate-500">
                  {u.avg_latency_ms != null ? `${Math.round(u.avg_latency_ms)} ms` : "-"}
                </td>
                <td className="td">
                  <span
                    className={`badge border ${
                      u.is_active
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : "border-red-200 bg-red-50 text-red-700"
                    }`}
                  >
                    {u.is_active ? "ACTIVE" : "SUSPENDED"}
                  </span>
                </td>
                <td className="td">
                  <button
                    className={u.is_active ? "btn-danger !px-3 !py-1 text-xs" : "btn-primary !px-3 !py-1 text-xs"}
                    onClick={() => void toggleActive(u)}
                  >
                    {u.is_active ? "Suspend" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
            {!users.length && (
              <tr>
                <td colSpan={10} className="td py-8 text-center text-slate-400">
                  No users yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MetricCard({ label, value, tone }: { label: string; value?: number | string | null; tone?: string }) {
  return (
    <div className="card py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone ?? "text-slate-900"}`}>
        {value ?? "–"}
      </p>
    </div>
  );
}
