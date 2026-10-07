"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";

function CallbackInner() {
  const params = useSearchParams();
  const { loginWithGoogle } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = params.get("code");
    if (!code) {
      setError("Missing authorization code");
      return;
    }
    loginWithGoogle(code)
      .then((u) => {
        location.href = u.role === "SUPER_ADMIN" ? "/admin" : "/dashboard";
      })
      .catch((e) => setError((e as Error).message));
  }, [params, loginWithGoogle]);

  if (error) {
    return (
      <div className="mx-auto mt-24 max-w-md card">
        <p className="text-sm text-red-600">Google sign-in failed: {error}</p>
        <a href="/login" className="btn-secondary mt-4">Back to login</a>
      </div>
    );
  }
  return <p className="mt-24 text-center text-sm text-slate-500">Signing you in…</p>;
}

export default function GoogleCallbackPage() {
  return (
    <AuthProvider>
      <Suspense fallback={<p className="mt-24 text-center text-sm text-slate-500">Loading…</p>}>
        <CallbackInner />
      </Suspense>
    </AuthProvider>
  );
}
