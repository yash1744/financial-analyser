"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { UserGate } from "@/components/UserGate";

import { Sidebar } from "./Sidebar";

// Reached from emailed links, often without a session — never gated.
const PUBLIC_PATHS = new Set([
  "/verify-email",
  "/forgot-password",
  "/reset-password",
]);

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (PUBLIC_PATHS.has(pathname)) {
    return <>{children}</>;
  }
  return (
    <UserGate>
      <div className="min-h-screen bg-page">
        <Sidebar />
        <div className="md:pl-56">
          <main className="mx-auto w-full max-w-6xl px-4 py-6 lg:px-8 lg:py-8">
            {children}
          </main>
        </div>
      </div>
    </UserGate>
  );
}
