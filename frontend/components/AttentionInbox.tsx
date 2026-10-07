"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ClientRow, Notice } from "@/lib/api";

export default function AttentionInbox({ refreshKey = 0 }: { refreshKey?: number }) {
  const [notices, setNotices] = useState<Notice[]>([]);
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [mapping, setMapping] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [n, c] = await Promise.all([
        api<Notice[]>("/notices/unmatched"),
        api<ClientRow[]>("/clients"),
      ]);
      setNotices(n);
      setClients(c);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const mapTo = async (noticeId: string, clientId: string) => {
    if (!clientId) return;
    setMapping(noticeId);
    try {
      await api(`/notices/${noticeId}/map`, { method: "POST", json: { client_id: clientId } });
      setMsg("Client mapped - WhatsApp alert queued for the client.");
      setNotices((prev) => prev.filter((n) => n.id !== noticeId));
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setMapping(null);
      setTimeout(() => setMsg(null), 5000);
    }
  };

  if (loading) return <p className="text-sm text-slate-500">Loading attention inbox…</p>;

  return (
    <div className="space-y-4">
      {msg && (
        <div className="rounded-md border border-brand-100 bg-brand-50 px-3 py-2 text-sm text-brand-700">
          {msg}
        </div>
      )}

      {!notices.length ? (
        <div className="card text-center text-sm text-slate-500">
          🎉 Attention inbox empty - every detected notice is mapped to a client.
        </div>
      ) : (
        notices.map((n) => (
          <div key={n.id} className="card border-l-4 border-l-amber-400">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium">{n.raw_subject || "(no subject)"}</p>
                <p className="mt-1 text-sm text-slate-500">
                  GSTIN on notice:{" "}
                  <span className="font-mono font-semibold text-slate-700">
                    {n.extracted_gstin ?? "not found"}
                  </span>{" "}
                  - no client matched yet.
                </p>
                {n.summary && <p className="mt-2 text-sm text-slate-600">{n.summary}</p>}
                <p className="mt-1 text-xs text-slate-400">
                  {n.notice_form ?? "Form?"} · from {n.sender ?? "unknown"} ·{" "}
                  {new Date(n.created_at).toLocaleString("en-IN")}
                </p>
              </div>
              <div className="flex w-full max-w-xs items-end gap-2 sm:w-auto">
                <div className="flex-1 sm:w-56">
                  <label className="label" htmlFor={`map-${n.id}`}>Map to client</label>
                  <select id={`map-${n.id}`} className="input" defaultValue="">
                    <option value="" disabled>Select client…</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.gstin})
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  className="btn-primary"
                  disabled={mapping === n.id}
                  onClick={(e) => {
                    const sel = (e.currentTarget.parentElement?.querySelector("select") as HTMLSelectElement | null);
                    void mapTo(n.id, sel?.value ?? "");
                  }}
                >
                  {mapping === n.id ? "Mapping…" : "Map & Alert"}
                </button>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
