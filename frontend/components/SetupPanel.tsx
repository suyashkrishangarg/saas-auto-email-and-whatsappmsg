"use client";

import { useCallback, useEffect, useState } from "react";
import { api, User } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type GmailStatus = {
  connected: boolean;
  status: string | null;
  mailbox: string | null;
  watch_expiry: string | null;
  last_sync_at: string | null;
};

export default function SetupPanel() {
  const { user, refresh } = useAuth();
  const [method, setMethod] = useState<string>(
    (user?.auth_method as string) || "FORWARDING"
  );
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [copied, setCopied] = useState(false);

  const code = user?.forwarding_verification_code ?? null;

  const loadGmail = useCallback(async () => {
    try {
      setGmail(await api<GmailStatus>("/gmail/status"));
    } catch {
      setGmail(null);
    }
  }, []);

  useEffect(() => {
    void loadGmail();
  }, [loadGmail]);

  // Poll for the intercepted 9-digit Gmail forwarding code (webhook sets it)
  useEffect(() => {
    if (!code) return;
    const t = setInterval(() => {
      void refresh();
    }, 8000);
    return () => clearInterval(t);
  }, [code, refresh]);

  const saveMethod = async () => {
    setErr(null);
    try {
      await api("/auth/onboarding", { method: "POST", json: { auth_method: method } });
      await refresh();
      setMsg("Ingestion channel saved.");
    } catch (e) {
      setErr((e as Error).message);
    }
    setTimeout(() => setMsg(null), 4000);
  };

  const connectGmail = async () => {
    setErr(null);
    try {
      const { url } = await api<{ url: string }>("/gmail/connect");
      location.href = url;
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const copyAlias = async () => {
    if (!user?.forwarding_alias) return;
    try {
      await navigator.clipboard.writeText(user.forwarding_alias);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setErr("Copy failed - select the address manually.");
    }
  };

  const confirmCode = async () => {
    if (!code) return;
    setConfirming(true);
    setErr(null);
    try {
      await api("/auth/verification-code?code=" + encodeURIComponent(code), { method: "POST" });
      await refresh();
      setMsg("Forwarding confirmed ✅ Gmail will now forward department mails here.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setConfirming(false);
      setTimeout(() => setMsg(null), 5000);
    }
  };

  if (!user) return null;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Method picker */}
      <div className="card">
        <h3 className="font-semibold">1 · Choose your ingestion channel</h3>
        <p className="mt-1 text-sm text-slate-500">
          Pick how department notices reach the platform. You can switch anytime.
        </p>
        <div className="mt-4 space-y-2">
          {(
            [
              ["FORWARDING", "Email forwarding alias", "Forward department mails to your unique virtual address - zero setup."],
              ["OAUTH", "Gmail OAuth (watch)", "We watch your Gmail inbox via Google Pub/Sub push - fully automatic."],
              ["BOTH", "Both channels", "Alias + Gmail watch together."],
            ] as const
          ).map(([value, title, desc]) => (
            <label
              key={value}
              className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${
                method === value ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:bg-slate-50"
              }`}
            >
              <input
                type="radio"
                name="method"
                className="mt-1"
                checked={method === value}
                onChange={() => setMethod(value)}
              />
              <span>
                <span className="block text-sm font-medium">{title}</span>
                <span className="block text-xs text-slate-500">{desc}</span>
              </span>
            </label>
          ))}
        </div>
        <button className="btn-primary mt-4" onClick={saveMethod}>Save channel</button>
        {msg && <p className="mt-2 text-sm text-emerald-600">{msg}</p>}
        {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      </div>

      {/* Forwarding setup */}
      <div className="card">
        <h3 className="font-semibold">2 · Your forwarding alias</h3>
        <p className="mt-1 text-sm text-slate-500">
          Add this address to your Gmail forwarding rules (Settings → Forwarding). Google will
          email a 9-digit confirmation code - we intercept it automatically.
        </p>
        <div className="mt-3 flex items-center gap-2">
          <code className="flex-1 truncate rounded-md bg-slate-100 px-3 py-2 text-sm">
            {user.forwarding_alias || "not assigned"}
          </code>
          <button className="btn-secondary" onClick={copyAlias}>
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>

        {code && (
          <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
            <p className="text-sm font-medium text-amber-800">
              Google verification code intercepted:
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <span className="rounded-md border border-amber-300 bg-white px-4 py-2 font-mono text-2xl font-bold tracking-widest text-amber-900">
                {code}
              </span>
              <button
                className="btn-secondary"
                onClick={() => void navigator.clipboard.writeText(code)}
              >
                Copy code
              </button>
              <button className="btn-primary" onClick={confirmCode} disabled={confirming}>
                {confirming ? "Confirming…" : "Confirm forwarding"}
              </button>
            </div>
            <p className="mt-2 text-xs text-amber-700">
              Google sends this to your alias; our inbound webhook extracts it for you.
            </p>
          </div>
        )}
      </div>

      {/* Gmail OAuth */}
      <div className="card">
        <h3 className="font-semibold">3 · Gmail connection</h3>
        <p className="mt-1 text-sm text-slate-500">
          Connect the mailbox with one click. We subscribe to inbox changes via Google
          Cloud Pub/Sub push notifications.
        </p>
        <div className="mt-3 space-y-1 text-sm">
          <p>
            Status:{" "}
            {gmail?.connected ? (
              <span className="badge border border-emerald-200 bg-emerald-50 text-emerald-700">
                {gmail.status ?? "CONNECTED"}
              </span>
            ) : (
              <span className="badge border border-slate-200 bg-slate-50 text-slate-600">
                NOT CONNECTED
              </span>
            )}
          </p>
          {gmail?.mailbox && <p className="text-slate-500">Mailbox: {gmail.mailbox}</p>}
          {gmail?.last_sync_at && (
            <p className="text-slate-500">
              Last sync: {new Date(gmail.last_sync_at).toLocaleString("en-IN")}
            </p>
          )}
        </div>
        <div className="mt-3 flex gap-2">
          <button className="btn-primary" onClick={connectGmail}>Connect Gmail (OAuth)</button>
          {gmail?.connected && (
            <button
              className="btn-secondary"
              onClick={() => void api("/gmail/renew", { method: "POST" })}
            >
              Renew watch
            </button>
          )}
        </div>
      </div>

      {/* Webhook endpoints */}
      <div className="card">
        <h3 className="font-semibold">4 · Webhook endpoints</h3>
        <p className="mt-1 text-sm text-slate-500">
          Point your inbound provider / Pub/Sub subscription at:
        </p>
        <ul className="mt-2 space-y-1 text-xs font-mono text-slate-600">
          <li>POST https://api.ramyaai.tech/v1/ingest/inbound</li>
          <li>POST https://api.ramyaai.tech/v1/ingest/pubsub</li>
        </ul>
      </div>
    </div>
  );
}
