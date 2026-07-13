"use client";

import type { ReactNode } from "react";

import { UserGate } from "@/components/UserGate";

import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: ReactNode }) {
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
