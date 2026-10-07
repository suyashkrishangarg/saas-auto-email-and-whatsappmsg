"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { AuthProvider, useAuth } from "@/lib/auth";

function AdminNav({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) location.href = "/login";
    if (!loading && user && user.role !== "SUPER_ADMIN") location.href = "/dashboard";
  }, [loading, user]);

  if (loading || !user) return <div className="p-6 text-sm text-slate-500">Loading…</div>;

  const links = [
    ["/admin", "Metrics & Users"],
    ["/admin/settings", "Settings"],
    ["/admin/logs", "Audit Logs"],
  ] as const;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-slate-900 text-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <span className="text-lg font-bold">NoticeAlert · Super Admin</span>
            <nav className="hidden gap-1 md:flex">
              {links.map(([href, label]) => (
                <Link key={href} href={href}
                  className={`rounded-md px-3 py-1.5 text-sm ${
                    pathname === href ? "bg-white/15 text-white" : "text-slate-300 hover:bg-white/10"
                  }`}>
                  {label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-sm text-slate-300 hover:text-white">Consultant view</Link>
            <button onClick={logout} className="btn-secondary !bg-white/10 !text-white !border-white/20">
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AdminNav>{children}</AdminNav>
    </AuthProvider>
  );
}
