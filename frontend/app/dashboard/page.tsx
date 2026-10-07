"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import ActivityFeed from "@/components/ActivityFeed";
import AttentionInbox from "@/components/AttentionInbox";
import ClientGrid from "@/components/ClientGrid";
import SetupPanel from "@/components/SetupPanel";
import { api, ClientRow } from "@/lib/api";

type Stats = {
  notices_total: number;
  unmatched: number;
  notices_24h: number;
  clients: number;
};

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="card py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${accent ?? "text-slate-900"}`}>{value}</p>
    </div>
  );
}

function DashboardInner() {
  const params = useSearchParams();
  const tab = params.get("tab") || "overview";
  const [stats, setStats] = useState<Stats | null>(null);
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        api<Stats>("/notices/stats/summary"),
        api<ClientRow[]>("/clients"),
      ]);
      setStats(s);
      setClients(c);
    } catch {
      /* handled by children */
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 30000); // live feed refresh
    return () => clearInterval(t);
  }, [load, refreshKey]);

  const tabs = [
    ["overview", "Overview"],
    ["clients", "Client Grid"],
    ["notices", "Notice Feed"],
    ["inbox", `Attention Inbox${stats && stats.unmatched ? ` (${stats.unmatched})` : ""}`],
    ["setup", "Setup"],
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {tabs.map(([key, label]) => (
          <a
            key={key}
            href={key === "overview" ? "/dashboard" : `/dashboard?tab=${key}`}
            className={`rounded-md px-3 py-1.5 text-sm ${
              tab === key ? "bg-brand-600 text-white" : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            {label}
          </a>
        ))}
        <button className="btn-secondary ml-auto" onClick={() => setRefreshKey((k) => k + 1)}>
          Refresh
        </button>
      </div>

      {(tab === "overview" || tab === "notices") && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="Clients" value={stats?.clients ?? "–"} />
          <Stat label="Notices (total)" value={stats?.notices_total ?? "–"} />
          <Stat label="Last 24h" value={stats?.notices_24h ?? "–"} />
          <Stat
            label="Unmatched"
            value={stats?.unmatched ?? "–"}
            accent={stats && stats.unmatched > 0 ? "text-amber-600" : undefined}
          />
        </div>
      )}

      {tab === "overview" && <ActivityFeed refreshKey={refreshKey} />}
      {tab === "clients" && <ClientGrid initial={clients} />}
      {tab === "notices" && <ActivityFeed refreshKey={refreshKey} />}
      {tab === "inbox" && <AttentionInbox refreshKey={refreshKey} />}
      {tab === "setup" && <SetupPanel />}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
      <DashboardInner />
    </Suspense>
  );
}
