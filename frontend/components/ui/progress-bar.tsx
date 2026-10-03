"use client";

import { useEffect, useState } from "react";

import { cx } from "@/lib/utils";

interface ProgressBarProps {
  value: number;
  className?: string;
  tone?: "brand" | "success" | "danger";
  label?: string;
}

const TONES = {
  brand: "bg-brand",
  success: "bg-success",
  danger: "bg-danger",
};

export function ProgressBar({
  value,
  className,
  tone = "brand",
  label,
}: ProgressBarProps) {
  const safe = Math.max(0, Math.min(value, 100));
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div
      className={cx("h-1.5 w-full overflow-hidden rounded-full bg-mist", className)}
      role="progressbar"
      aria-valuenow={Math.round(safe)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div
        className={cx(
          "h-full rounded-full transition-[width] duration-700 ease-out",
          TONES[tone],
        )}
        style={{ width: mounted ? `${safe}%` : "0%" }}
      />
    </div>
  );
}
