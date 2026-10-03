import type { ReactNode } from "react";

import { TrendingDown, TrendingUp } from "lucide-react";

import { cx } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
  trend?: { value: string; direction: "up" | "down" };
}

export function StatCard({ label, value, hint, icon, trend }: StatCardProps) {
  return (
    <div className="group rounded-card border border-line bg-card p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-shadow duration-200 hover:shadow-[0_4px_12px_rgba(16,24,40,0.06)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-ink-2">{label}</p>
          <p className="mt-2 text-[26px] font-bold leading-none tracking-tight text-ink">
            {value}
          </p>
          {trend ? (
            <p
              className={cx(
                "mt-2 inline-flex items-center gap-1 text-xs font-medium",
                trend.direction === "up" ? "text-success" : "text-danger",
              )}
            >
              {trend.direction === "up" ? (
                <TrendingUp className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <TrendingDown className="h-3.5 w-3.5" aria-hidden />
              )}
              {trend.value}
            </p>
          ) : null}
          {hint ? <p className="mt-2 text-xs text-ink-3">{hint}</p> : null}
        </div>
        {icon ? (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand transition-colors duration-200 group-hover:bg-brand-100">
            {icon}
          </span>
        ) : null}
      </div>
    </div>
  );
}
