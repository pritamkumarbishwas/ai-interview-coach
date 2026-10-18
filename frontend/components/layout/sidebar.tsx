"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Briefcase,
  ChartColumn,
  ClipboardList,
  FileText,
  LayoutDashboard,
  Mic,
  ScrollText,
  User,
  Users,
} from "lucide-react";

import { Logo } from "@/components/layout/logo";
import { Avatar } from "@/components/ui/avatar";
import { cx } from "@/lib/utils";
import type { Role } from "@/types";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  /** Only shown to these roles; omitted = everyone with this nav set. */
  roles?: Role[];
}

const CANDIDATE_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/interviews", label: "My Interviews", icon: ClipboardList },
  { href: "/practice", label: "Practice", icon: Mic },
  { href: "/resumes", label: "Resumes", icon: FileText },
  { href: "/job-descriptions", label: "Job Descriptions", icon: Briefcase },
  { href: "/results", label: "Results", icon: ChartColumn },
  { href: "/profile", label: "Profile", icon: User },
];

const STAFF_NAV: NavItem[] = [
  { href: "/jobs", label: "Jobs", icon: Briefcase },
  { href: "/templates", label: "Templates", icon: ClipboardList },
  { href: "/team", label: "Team", icon: Users, roles: ["admin"] },
  { href: "/audit", label: "Audit log", icon: ScrollText, roles: ["admin"] },
  { href: "/profile", label: "Profile", icon: User },
];

const STAFF_ROLE_SET: Role[] = ["admin", "recruiter", "reviewer"];

function navForRole(role: Role | undefined): NavItem[] {
  if (role && STAFF_ROLE_SET.includes(role)) {
    return STAFF_NAV.filter((item) => !item.roles || item.roles.includes(role));
  }
  return CANDIDATE_NAV;
}

const ROLE_LABELS: Record<Role, string> = {
  candidate: "Candidate",
  admin: "Administrator",
  recruiter: "Recruiter",
  reviewer: "Reviewer",
};

interface SidebarProps {
  userName: string;
  role?: Role;
  className?: string;
  onClose?: () => void;
}

export function Sidebar({ userName, role, className, onClose }: SidebarProps) {
  const pathname = usePathname();
  const navItems = navForRole(role);
  const isStaff = role ? STAFF_ROLE_SET.includes(role) : false;

  return (
    <aside
      className={cx(
        "flex h-full w-56 flex-col border-r border-line bg-card",
        className,
      )}
    >
      <div className="flex h-16 items-center justify-between px-5">
        <Logo />
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="rounded-btn p-1.5 text-ink-3 transition-colors hover:bg-mist hover:text-ink-2 xl:hidden"
            aria-label="Close menu"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        ) : null}
      </div>

      <nav
        className="flex-1 space-y-1 overflow-y-auto px-3 py-4"
        aria-label="Main navigation"
      >
        {navItems.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={cx(
                "flex items-center gap-3 rounded-btn px-3 py-2.5 text-sm font-medium transition-colors duration-150",
                active
                  ? "bg-brand-100 text-brand"
                  : "text-ink-2 hover:bg-mist hover:text-ink",
              )}
              aria-current={active ? "page" : undefined}
            >
              <Icon
                className={cx(
                  "h-[18px] w-[18px] shrink-0",
                  active ? "text-brand" : "text-ink-3",
                )}
                aria-hidden
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-line p-3">
        <Link
          href="/profile"
          onClick={onClose}
          className="flex items-center gap-3 rounded-btn px-2 py-2 transition-colors hover:bg-mist"
        >
          <span className="relative">
            <Avatar name={userName} size="sm" />
            <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-card bg-success" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[13px] font-semibold text-ink">
              {userName}
            </span>
            <span className="flex items-center gap-1 text-[11px] text-ink-3">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand" />
              {isStaff ? ROLE_LABELS[role!] : "Active Interview"}
            </span>
          </span>
        </Link>
      </div>
    </aside>
  );
}
