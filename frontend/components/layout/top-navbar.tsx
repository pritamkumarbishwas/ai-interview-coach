"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { Bell, Search } from "lucide-react";

import { UserMenu } from "@/components/layout/user-menu";
import { titleCase } from "@/lib/utils";

const TITLES: Array<{ match: string; title: string }> = [
  { match: "/dashboard", title: "Dashboard" },
  { match: "/practice", title: "Practice" },
  { match: "/results", title: "Results" },
  { match: "/profile", title: "Profile" },
  { match: "/resumes", title: "Resumes" },
  { match: "/job-descriptions", title: "Job Descriptions" },
  { match: "/interviews/", title: "Interview Session" },
  { match: "/interviews", title: "My Interviews" },
];

const NOTIFICATIONS = [
  {
    id: "n1",
    title: "New report ready",
    detail: "Frontend Developer · scored 76%",
    time: "1h ago",
  },
  {
    id: "n2",
    title: "Practice streak",
    detail: "You've practiced 3 days in a row",
    time: "Yesterday",
  },
];

function pageTitle(pathname: string): string {
  const found = TITLES.find((item) => pathname.startsWith(item.match));
  if (found) return found.title;
  const segment = pathname.split("/").filter(Boolean).pop() ?? "";
  return titleCase(segment) || "Dashboard";
}

interface TopNavbarProps {
  onMenuClick: () => void;
}

export function TopNavbar({ onMenuClick }: TopNavbarProps) {
  const pathname = usePathname();
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setBellOpen(false);
  }, [pathname]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(event.target as Node)) {
        setBellOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-card/90 backdrop-blur">
      <div className="flex h-16 items-center gap-4 px-5 lg:px-8">
        <button
          type="button"
          onClick={onMenuClick}
          className="rounded-btn p-2 text-ink-2 transition-colors hover:bg-mist lg:hidden"
          aria-label="Open menu"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <h1 className="shrink-0 text-base font-semibold text-ink">
          {pageTitle(pathname)}
        </h1>

        <div className="mx-auto hidden w-full max-w-xs md:block">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
              aria-hidden
            />
            <input
              type="search"
              placeholder="Search…"
              aria-label="Search"
              className="h-9 w-full rounded-btn border border-line bg-surface pl-9 pr-3 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand-100"
            />
          </div>
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          <div className="relative" ref={bellRef}>
            <button
              type="button"
              onClick={() => setBellOpen((open) => !open)}
              className="relative rounded-btn p-2 text-ink-2 transition-colors hover:bg-mist hover:text-ink"
              aria-label="Notifications"
              aria-expanded={bellOpen}
            >
              <Bell className="h-[18px] w-[18px]" aria-hidden />
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-brand ring-2 ring-card" />
            </button>
            {bellOpen ? (
              <div className="absolute right-0 mt-2 w-72 overflow-hidden rounded-card border border-line bg-card shadow-lg animate-rise">
                <p className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
                  Notifications
                </p>
                <ul>
                  {NOTIFICATIONS.map((item) => (
                    <li
                      key={item.id}
                      className="border-b border-line px-4 py-3 last:border-0"
                    >
                      <p className="text-[13px] font-medium text-ink">
                        {item.title}
                      </p>
                      <p className="mt-0.5 text-[13px] text-ink-2">
                        {item.detail}
                      </p>
                      <p className="mt-1 text-xs text-ink-3">{item.time}</p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          <button
            type="button"
            className="rounded-btn p-2 text-ink-2 transition-colors hover:bg-mist hover:text-ink"
            aria-label="Help"
            title="Help & documentation"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <path d="M12 17h.01" />
            </svg>
          </button>

          <UserMenu />
        </div>
      </div>
    </header>
  );
}
