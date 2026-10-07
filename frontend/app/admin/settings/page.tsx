"use client";

import { useCallback, useEffect, useState } from "react";
import { api, SettingEntry } from "@/lib/api";
import { DEFAULT_SYSTEM_PROMPT } from "@/lib/llm";

const PROVIDERS = [
  { id: "openai", label: "OpenAI", models: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"] },
  { id: "gemini", label: "Google Gemini", models: ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"] },
  { id: "anthropic", label: "Anthropic", models: ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"] },
  { id: "groq", label: "Groq", models: ["llama-3.1-70b-versatile", "llama-3.1-8b-instant"] },
  { id: "custom", label: "Custom (OpenAI-compatible)", models: [] },
];

type Settings = Record<string, SettingEntry>;

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<Settings>("/admin/settings");
      setSettings(data);
      const d: Record<string, string> = {};
      for (const [k, v] of Object.entries(data)) d[k] = v.value ?? "";
      setDraft(d);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (key: string, isSecret: boolean) => {
    setSaving(key);
    try {
      await api("/admin/settings", {
        method: "PUT",
        json: { key, value: draft[key] ?? "", is_secret: isSecret },
      });
      setMsg(`Saved ${key} - effective immediately (no redeploy).`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(null);
      setTimeout(() => setMsg(null), 4000);
    }
  };

  const saveAll = async () => {
    if (!settings) return;
    setSaving("*");
    try {
      for (const [key, entry] of Object.entries(settings)) {
        await api("/admin/settings", {
          method: "PUT",
          json: { key, value: draft[key] ?? "", is_secret: entry.is_secret },
        });
      }
      setMsg("All settings saved - effective immediately.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(null);
      setTimeout(() => setMsg(null), 4000);
    }
  };

  if (!settings) return <p className="text-sm text-slate-500">{error ?? "Loading settings…"}</p>;

  const provider = draft["llm.provider"] || "";
  const models = PROVIDERS.find((p) => p.id === provider)?.models ?? [];

  const Field = ({ label, hint, secret }: { label: string; hint?: string; secret?: boolean }) => (
    <div>
      <label className="label">{label}</label>
      <div className="flex gap-2">
        <input
          className="input font-mono"
          type={secret ? "password" : "text"}
          value={draft[label] ?? ""}
          onChange={(e) => setDraft((d) => ({ ...d, [label]: e.target.value }))}
          placeholder={secret && !settings[label]?.has_value ? "not set" : undefined}
        />
        <button
          className="btn-primary whitespace-nowrap"
          onClick={() => void save(label, !!secret)}
          disabled={saving === label}
        >
          {saving === label ? "…" : "Save"}
        </button>
      </div>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );

  return (
    <div className="space-y-6">
      {msg && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {msg}
        </div>
      )}
      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="card">
        <h2 className="font-semibold">AI Notice Analysis</h2>
        <p className="mt-1 text-sm text-slate-500">
          No hard-coded default - pick the active provider/model. Secrets are encrypted
          (Fernet/AES envelope) at rest in Postgres.
        </p>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label className="label" htmlFor="llm-provider">Active LLM provider</label>
            <div className="flex gap-2">
              <select
                id="llm-provider"
                className="input"
                value={provider}
                onChange={(e) => setDraft((d) => ({ ...d, "llm.provider": e.target.value }))}
              >
                <option value="">— select —</option>
                {PROVIDERS.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
              <button
                className="btn-primary"
                onClick={() => void save("llm.provider", false)}
                disabled={saving === "llm.provider"}
              >
                {saving === "llm.provider" ? "…" : "Save"}
              </button>
            </div>
          </div>

          <div>
            <label className="label" htmlFor="llm-model">Model</label>
            <div className="flex gap-2">
              <input
                id="llm-model"
                className="input"
                list="model-options"
                value={draft["llm.model"] ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, "llm.model": e.target.value }))}
                placeholder="gpt-4o-mini"
              />
              <datalist id="model-options">
                {models.map((m) => <option key={m} value={m} />)}
              </datalist>
              <button
                className="btn-primary"
                onClick={() => void save("llm.model", false)}
                disabled={saving === "llm.model"}
              >
                {saving === "llm.model" ? "…" : "Save"}
              </button>
            </div>
          </div>
        </div>

        <div className="mt-4">
          <Field
            label={`llm.api_key.${provider || "openai"}`}
            secret
            hint="Encrypted at rest. Switch provider above to edit that provider's key. Custom endpoint key is optional (leave empty for local Ollama/vLLM)."
          />
        </div>

        {provider === "custom" && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
            <h3 className="font-semibold">Custom OpenAI-compatible endpoint</h3>
            <p className="mt-1 text-sm text-slate-600">
              Works with Ollama, vLLM, Together, OpenRouter, Mistral La Plateforme, Azure
              OpenAI, LocalAI — anything serving <code>/chat/completions</code>. Must be
              reachable from the Render backend (public URL; localhost only works for local dev).
            </p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <Field
                label="llm.custom.base_url"
                hint="e.g. https://openrouter.ai/api/v1 or http://localhost:11434/v1 (no trailing /chat/completions)"
              />
              <Field label="llm.custom.model" hint="Exact model id served by that endpoint" />
              <Field label="llm.custom.api_key" secret hint="Alias of llm.api_key.custom. Empty = no Authorization header." />
              <Field
                label="llm.custom.extra_headers"
                hint='Optional JSON, e.g. {"HTTP-Referer":"https://saas.ramyaai.tech","X-Title":"CA-SaaS"}'
              />
            </div>
          </div>
        )}

        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <h3 className="font-semibold">Generation tuning</h3>
          <p className="mt-1 text-sm text-slate-600">
            Applied to every provider including custom. Extraction defaults to temperature 0
            for deterministic JSON.
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label="llm.temperature" hint="0 = deterministic extraction. Raise (0.3-0.7) only for friendlier summaries." />
            <Field label="llm.max_tokens" hint="Max output tokens per call (default 1024)" />
            <Field label="llm.timeout_s" hint="HTTP timeout per LLM call in seconds (default 60)" />
            <Field label="llm.max_body_chars" hint="Email body chars sent to the model (default 12000)" />
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between">
            <label className="label">System prompt</label>
            <button
              type="button"
              className="text-xs font-medium text-brand-600 hover:underline"
              onClick={() => setDraft((d) => ({ ...d, "llm.system_prompt": DEFAULT_SYSTEM_PROMPT }))}
            >
              Restore built-in default
            </button>
          </div>
          <textarea
            className="input min-h-[120px] font-mono text-xs"
            value={draft["llm.system_prompt"] ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, "llm.system_prompt": e.target.value }))}
            placeholder={DEFAULT_SYSTEM_PROMPT}
          />
          <p className="mt-1 text-xs text-slate-500">
            Empty = use the built-in GST notice prompt (shown as placeholder above). Your saved
            text overrides it.
          </p>
          <button
            className="btn-primary mt-2"
            onClick={() => void save("llm.system_prompt", false)}
            disabled={saving === "llm.system_prompt"}
          >
            {saving === "llm.system_prompt" ? "…" : "Save prompt"}
          </button>
        </div>
      </div>

      <div className="card">
        <h2 className="font-semibold">WhatsApp (fallback chain: Meta → Twilio → Gupshup)</h2>
        <p className="mt-1 text-sm text-slate-500">
          Each provider gets one retry before falling through to the next.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="whatsapp.meta.token" secret />
          <Field label="whatsapp.meta.phone_number_id" />
          <Field label="whatsapp.template.consultant" />
          <Field label="whatsapp.template.client" />
          <Field label="whatsapp.twilio.account_sid" secret />
          <Field label="whatsapp.twilio.auth_token" secret />
          <Field label="whatsapp.twilio.from" />
          <Field label="whatsapp.gupshup.api_key" secret />
          <Field label="whatsapp.gupshup.sender" />
          <Field label="whatsapp.provider_order" hint="Comma separated, e.g. meta,twilio,gupshup" />
        </div>
      </div>

      <div className="flex justify-end">
        <button className="btn-primary" onClick={saveAll} disabled={saving === "*"}>
          {saving === "*" ? "Saving all…" : "Save all settings"}
        </button>
      </div>
    </div>
  );
}
