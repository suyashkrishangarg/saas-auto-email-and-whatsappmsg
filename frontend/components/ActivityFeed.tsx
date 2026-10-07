"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Notice } from "@/lib/api";

function fmtAmount(v: string | number | null): string {
  if (v === null || v === undefined) return "-";
  const n = typeof v === "string" ? Number(v) : v;
  if (Number.isNaN(n)) return String(v);
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function StatusBadge({ status }: { status: Notice["status"] }) {
  const map: Record<string, string> = {
    PROCESSED: "bg-emerald-50 text-emerald-700 border-emerald-200",
    UNMATCHED: "bg-amber-50 text-amber-700 border-amber-200",
    FAILED: "bg-red-50 text-red-700 border-red-200",
  };
  return <span className={`badge border ${map[status] ?? "bg-slate-50 text-slate-600"}`}>{status}</span>;
}

export default function ActivityFeed({ refreshKey = 0 }: { refreshKey?: number }) {
  const [notices, setNotices] = useState<Notice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [logs, setLogs] = useState<
    {
      id: string;
      recipient_type: string;
      phone: string;
      status: string;
      provider: string | null;
      error: string | null;
    }[]
  >([]);

  const load = useCallback(async () => {
    try {
      const data = await api<Notice[]>("/notices?limit=100");
      setNotices(data.filter((n) => n.status !== "UNMATCHED"));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const toggleLogs = async (id: string) => {
    if (openId === id) {
      setOpenId(null);
      return;
    }
    try {
      const data = await api<
        {
          id: string;
          recipient_type: string;
          phone: string;
          status: string;
          provider: string | null;
          error: string | null;
        }[]
      >(`/notices/${id}/logs`);
      setLogs(data);
      setOpenId(id);
    } catch {
      setOpenId(null);
    }
  };

  if (loading) return <p className="text-sm text-slate-500">Loading notices…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!notices.length)
    return (
      <div className="card text-center text-sm text-slate-500">
        No notices yet. Connect your mailbox in <b>Setup</b> - detected notices will appear
        here with WhatsApp dispatch status.
      </div>
    );

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full min-w-[900px] border-collapse">
        <thead>
          <tr>
            <th className="th">Received</th>
            <th className="th">Subject / Sender</th>
            <th className="th">GSTIN</th>
            <th className="th">Form</th>
            <th className="th">Demand</th>
            <th className="th">Due</th>
            <th className="th">Status</th>
            <th className="th">Latency</th>
            <th className="th">WhatsApp</th>
          </tr>
        </thead>
        <tbody>
          {notices.map((n) => (
            <tr key={n.id} className="hover:bg-slate-50/60">
              <td className="td whitespace-nowrap text-slate-500">
                {new Date(n.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
              </td>
              <td className="td max-w-[260px]">
                <p className="truncate font-medium">{n.raw_subject || "(no subject)"}</p>
                <p className="truncate text-xs text-slate-400">{n.sender}</p>
              </td>
              <td className="td font-mono text-xs">{n.extracted_gstin ?? "-"}</td>
              <td className="td">{n.notice_form ?? "-"}</td>
              <td className="td">{fmtAmount(n.demand_amount)}</td>
              <td className="td whitespace-nowrap">{n.due_date ?? "-"}</td>
              <td className="td"><StatusBadge status={n.status} /></td>
              <td className="td text-slate-500">{n.processing_latency_ms ?? "-"} ms</td>
              <td className="td">
                <button className="text-xs font-medium text-brand-600 hover:underline"
                  onClick={() => void toggleLogs(n.id)}>
                  {openId === n.id ? "Hide" : "View"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {openId && (
        <div className="border-t border-slate-100 bg-slate-50 p-4">
          <p className="mb-2 text-xs font-semibold uppercase text-slate-500">WhatsApp delivery receipts</p>
          {!logs.length && <p className="text-sm text-slate-500">No dispatch attempts.</p>}
          <ul className="space-y-1">
            {logs.map((l) => (
              <li key={l.id} className="flex flex-wrap items-center gap-3 text-sm">
                <span className={`badge border ${l.status === "SENT" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}`}>
                  {l.status}
                </span>
                <span>{l.recipient_type}</span>
                <span className="font-mono text-xs text-slate-500">{l.phone || "-"}</span>
                <span className="text-xs text-slate-400">via {l.provider ?? "-"}</span>
                {l.error && <span className="text-xs text-red-500">{l.error}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
