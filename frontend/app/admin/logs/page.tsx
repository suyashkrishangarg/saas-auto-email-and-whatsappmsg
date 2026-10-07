"use client";

import { useCallback, useEffect, useState } from "react";
import { api, LogEntry } from "@/lib/api";

export default function AdminLogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [kind, setKind] = useState("all");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<LogEntry[]>(`/admin/logs?kind=${kind}&limit=200`);
      setLogs(data);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [kind]);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 15000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="flex overflow-hidden rounded-md border border-slate-200">
          {(["all", "notices", "whatsapp"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`px-3 py-1.5 text-sm capitalize ${
                kind === k ? "bg-brand-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {k}
            </button>
          ))}
        </div>
        <button className="btn-secondary" onClick={() => void load()}>Refresh</button>
        <span className="ml-auto text-xs text-slate-400">auto-refresh 15s · {logs.length} entries</span>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full min-w-[900px] border-collapse">
          <thead>
            <tr>
              <th className="th">Time</th>
              <th className="th">Type</th>
              <th className="th">Detail</th>
              <th className="th">Status</th>
              <th className="th">Latency</th>
              <th className="th">Error</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={`${l.type}-${l.id}`} className="hover:bg-slate-50/60">
                <td className="td whitespace-nowrap text-slate-500">
                  {l.at ? new Date(l.at).toLocaleString("en-IN") : "-"}
                </td>
                <td className="td">
                  <span
                    className={`badge border ${
                      l.type === "EMAIL"
                        ? "border-sky-200 bg-sky-50 text-sky-700"
                        : "border-emerald-200 bg-emerald-50 text-emerald-700"
                    }`}
                  >
                    {l.type}
                  </span>
                </td>
                <td className="td max-w-[420px]">
                  {l.type === "EMAIL" ? (
                    <>
                      <p className="truncate font-medium">{l.subject || "(no subject)"}</p>
                      <p className="truncate text-xs text-slate-400">
                        {l.sender} · {l.source} · {l.gstin ?? "no GSTIN"}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-sm">
                        {l.recipient_type} → {l.phone}
                      </p>
                      <p className="truncate text-xs text-slate-400">
                        via {l.provider ?? "-"} · id {l.message_id ?? "-"}
                      </p>
                    </>
                  )}
                </td>
                <td className="td">
                  <span
                    className={`badge border ${
                      l.status === "SENT" || l.status === "PROCESSED"
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : l.status === "FAILED"
                          ? "border-red-200 bg-red-50 text-red-700"
                          : "border-amber-200 bg-amber-50 text-amber-700"
                    }`}
                  >
                    {l.status ?? "-"}
                  </span>
                </td>
                <td className="td text-slate-500">{l.latency_ms != null ? `${l.latency_ms} ms` : "-"}</td>
                <td className="td max-w-[240px] truncate text-xs text-red-500">{l.error ?? ""}</td>
              </tr>
            ))}
            {!logs.length && (
              <tr>
                <td colSpan={6} className="td py-8 text-center text-slate-400">
                  No log entries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
