"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api/endpoints";
import { useUser } from "@/lib/user";

const links = [
  { href: "/", label: "Dashboard", icon: "◧" },
  { href: "/transactions", label: "Transactions", icon: "⇄" },
  { href: "/accounts", label: "Accounts", icon: "▤" },
  { href: "/analytics", label: "Analytics", icon: "◔" },
  { href: "/assistant", label: "AI Assistant", icon: "✦" },
  { href: "/connect", label: "Connect Bank", icon: "＋" },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-1">
      {links.map(({ href, label, icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              active
                ? "bg-accent/10 text-accent"
                : "text-ink-2 hover:bg-line hover:text-ink"
            }`}
          >
            <span aria-hidden className="w-4 text-center">
              {icon}
            </span>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function UserFooter() {
  const { user, clearUser } = useUser();
  if (!user) return null;
  const signOut = async () => {
    try {
      await api.logout(); // clears the httpOnly cookie server-side
    } catch {
      // cookie may already be gone; still drop the local profile
    }
    clearUser();
  };
  return (
    <div className="mt-auto border-t border-line pt-4">
      <p className="truncate text-xs text-ink-3" title={user.email}>
        {user.email}
      </p>
      <button
        onClick={signOut}
        className="mt-1 text-xs text-ink-3 underline-offset-2 hover:text-ink hover:underline"
      >
        Sign out
      </button>
    </div>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Mobile top bar */}
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-surface px-4 py-3 md:hidden">
        <span className="text-sm font-semibold">Finance</span>
        <button
          aria-label="Toggle navigation"
          onClick={() => setOpen((v) => !v)}
          className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2"
        >
          {open ? "Close" : "Menu"}
        </button>
      </header>
      {open && (
        <div className="border-b border-line bg-surface p-4 md:hidden">
          <NavLinks onNavigate={() => setOpen(false)} />
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-10 hidden w-56 flex-col border-r border-line bg-surface p-4 md:flex">
        <div className="mb-6 px-3">
          <span className="text-base font-semibold text-ink">Finance</span>
        </div>
        <NavLinks />
        <UserFooter />
      </aside>
    </>
  );
}
