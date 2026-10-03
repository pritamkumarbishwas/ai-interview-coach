"use client";

import { useState, type ReactNode } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { TopNavbar } from "@/components/layout/top-navbar";
import { useAuth } from "@/hooks/use-auth";

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user } = useAuth();
  const userName = user?.name ?? "";

  return (
    <div className="min-h-screen bg-canvas">
      <div className="fixed inset-y-0 left-0 z-40 hidden xl:flex">
        <Sidebar userName={userName} />
      </div>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 xl:hidden">
          <div
            className="absolute inset-0 bg-[#1f2933]/40"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="absolute inset-y-0 left-0 shadow-xl">
            <Sidebar
              userName={userName}
              onClose={() => setMobileOpen(false)}
            />
          </div>
        </div>
      ) : null}

      <div className="xl:pl-56">
        <TopNavbar onMenuClick={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-[1500px] px-5 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
