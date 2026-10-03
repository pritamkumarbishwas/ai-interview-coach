import type { ReactNode } from "react";

import { cx } from "@/lib/utils";

export type BadgeTone =
  | "neutral"
  | "brand"
  | "ai"
  | "success"
  | "warning"
  | "danger"
  | "muted";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-mist text-ink-2 ring-line",
  brand: "bg-brand-100 text-brand-hover ring-[#f8dcb8]",
  ai: "bg-ai text-[#b3620a] ring-[#f8dcb8]",
  success: "bg-[#e7f6ef] text-success ring-[#c4ebdc]",
  warning: "bg-[#fdf3e2] text-[#b57a09] ring-[#f5dfb4]",
  danger: "bg-[#fdf0f0] text-danger ring-[#f5c6c7]",
  muted: "bg-mist text-ink-3 ring-line",
};

interface BadgeProps {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}

export function Badge({ tone = "neutral", className, children }: BadgeProps) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
