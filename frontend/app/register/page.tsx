"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { AuthProvider, useAuth } from "@/lib/auth";

function RegisterForm() {
  const { register } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(email, password, fullName, phone);
      location.href = "/dashboard";
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto mt-16 w-full max-w-md">
      <div className="card">
        <h1 className="text-xl font-semibold">Create your CA account</h1>
        <p className="mt-1 text-sm text-slate-500">
          You will pick your notice ingestion method in the onboarding wizard.
        </p>
        <form onSubmit={submit} className="mt-5 space-y-3">
          <div>
            <label className="label" htmlFor="name">Full name</label>
            <input id="name" className="input" required value={fullName}
              onChange={(e) => setFullName(e.target.value)} placeholder="CA Ramya Sharma" />
          </div>
          <div>
            <label className="label" htmlFor="email">Email</label>
            <input id="email" className="input" type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)} placeholder="you@firm.in" />
          </div>
          <div>
            <label className="label" htmlFor="phone">WhatsApp number (for alerts)</label>
            <input id="phone" className="input" value={phone}
              onChange={(e) => setPhone(e.target.value)} placeholder="9876543210 or +919876543210" />
          </div>
          <div>
            <label className="label" htmlFor="password">Password</label>
            <input id="password" className="input" type="password" required minLength={8}
              value={password} onChange={(e) => setPassword(e.target.value)} placeholder="min 8 characters" />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
        <p className="mt-4 text-sm text-slate-500">
          Already registered?{" "}
          <Link href="/login" className="font-medium text-brand-600 hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <AuthProvider>
      <RegisterForm />
    </AuthProvider>
  );
}
