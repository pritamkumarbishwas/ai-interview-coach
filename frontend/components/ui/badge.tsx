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
  brand: "bg-brand-soft text-brand-ink ring-brand-border",
  ai: "bg-info-soft text-info-ink ring-info-border",
  success: "bg-success-soft text-success-ink ring-success-border",
  warning: "bg-warning-soft text-warning-ink ring-warning-border",
  danger: "bg-danger-soft text-danger-ink ring-danger-border",
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
