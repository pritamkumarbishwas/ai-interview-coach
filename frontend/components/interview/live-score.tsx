"use client";

import { useEffect, useState } from "react";

import { ScoreMetric } from "@/components/interview/score-metric";
import type { MockScoreMetric } from "@/data/mock";

interface LiveScoreProps {
  overall: number;
  label: string;
  metrics: MockScoreMetric[];
}

export function LiveScore({ overall, label, metrics }: LiveScoreProps) {
  const [mounted, setMounted] = useState(false);
  const radius = 56;
  const circumference = 2 * Math.PI * radius;
  const safe = Math.max(0, Math.min(overall, 100));
  const offset = circumference - (safe / 100) * circumference;

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <section
      className="rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
      aria-label="Live scoring"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-[15px] font-semibold text-ink">Live Scoring</h2>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand">
          <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse-dot" />
          Live
        </span>
      </header>

      <div className="flex flex-col items-center px-4 pt-5">
        <div className="relative h-36 w-36">
          <svg viewBox="0 0 132 132" className="h-full w-full -rotate-90">
            <circle
              cx="66"
              cy="66"
              r={radius}
              className="fill-none stroke-mist"
              strokeWidth="11"
            />
            <circle
              cx="66"
              cy="66"
              r={radius}
              className="fill-none stroke-brand transition-[stroke-dashoffset] duration-1000 ease-out"
              strokeWidth="11"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={mounted ? offset : circumference}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-[28px] font-bold leading-none tracking-tight text-ink tabular-nums">
              {safe}
              <span className="text-base font-semibold text-ink-3">/100</span>
            </span>
            <span className="mt-1 rounded-full bg-brand-100 px-2 py-0.5 text-[11px] font-semibold text-brand-hover">
              {label}
            </span>
          </div>
        </div>
      </div>

      <div className="space-y-3.5 px-4 py-5">
        {metrics.map((metric) => (
          <ScoreMetric key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </div>
    </section>
  );
}
