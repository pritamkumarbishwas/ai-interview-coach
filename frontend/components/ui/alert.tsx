import type { ReactNode } from "react";

import { CircleAlert, CircleCheck, Info } from "lucide-react";

import { cx } from "@/lib/utils";

export type AlertTone = "error" | "success" | "info";

const TONES: Record<AlertTone, string> = {
  error: "border-[#f5c6c7] bg-[#fdf0f0] text-[#a02c30]",
  success: "border-[#c4ebdc] bg-[#e7f6ef] text-[#157a52]",
  info: "border-[#f8dcb8] bg-ai text-[#8a5310]",
};

const ICONS: Record<AlertTone, ReactNode> = {
  error: <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />,
  success: <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />,
  info: <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />,
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
