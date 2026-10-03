import Link from "next/link";

import { MessagesSquare, Sparkles } from "lucide-react";

import { cx } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/dashboard"
      className={cx("flex items-center gap-2.5", className)}
      aria-label="AI Interview Coach home"
    >
      <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-white shadow-sm">
        <MessagesSquare className="h-[18px] w-[18px]" aria-hidden />
        <Sparkles
          className="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full bg-white p-[1px] text-brand"
          aria-hidden
        />
      </span>
      <span className="text-[15px] font-bold tracking-tight text-ink">
        AI Interview <span className="text-brand">Coach</span>
      </span>
    </Link>
  );
}
