import type { ReactNode } from "react";

import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";

import { cx } from "@/lib/utils";

export type AlertTone = "error" | "success" | "info" | "warning";

const TONES: Record<AlertTone, string> = {
  error: "border-danger-border bg-danger-soft text-danger-ink",
  success: "border-success-border bg-success-soft text-success-ink",
  info: "border-info-border bg-info-soft text-info-ink",
  warning: "border-warning-border bg-warning-soft text-warning-ink",
};

const ICONS: Record<AlertTone, ReactNode> = {
  error: <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />,
  success: <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />,
  info: <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />,
  warning: <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />,
};

interface AlertProps {
  tone?: AlertTone;
  children: ReactNode;
  className?: string;
}

export function Alert({ tone = "info", children, className }: AlertProps) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cx(
        "flex items-start gap-2.5 rounded-btn border px-3.5 py-3 text-sm",
        TONES[tone],
        className,
      )}
    >
      {ICONS[tone]}
      <div className="min-w-0 leading-relaxed">{children}</div>
    </div>
  );
}
