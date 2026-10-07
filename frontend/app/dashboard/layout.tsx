"use client";

import Link from "next/link";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AuthProvider, useAuth } from "@/lib/auth";

function Nav({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
    if (!loading && user?.role === "SUPER_ADMIN" && !pathname.startsWith("/admin")) {
      router.replace("/admin");
    }
  }, [loading, user, router, pathname]);

  if (loading || !user) return <div className="p-6 text-sm text-slate-500">Loading…</div>;

  const links = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/dashboard?tab=clients", label: "Clients" },
    { href: "/dashboard?tab=notices", label: "Notices" },
    { href: "/dashboard?tab=inbox", label: "Attention Inbox" },
    { href: "/dashboard?tab=setup", label: "Setup" },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <span className="text-lg font-bold text-brand-700">NoticeAlert</span>
            <nav className="hidden gap-1 md:flex">
              {links.map((l) => (
                <Link key={l.href} href={l.href}
                  className={`rounded-md px-3 py-1.5 text-sm ${pathname + location.search === l.href
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-600 hover:bg-slate-50"}`}>
                  {l.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-500 sm:block">{user.email}</span>
            <button onClick={logout} className="btn-secondary">Sign out</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <Nav>{children}</Nav>
    </AuthProvider>
  );
}
