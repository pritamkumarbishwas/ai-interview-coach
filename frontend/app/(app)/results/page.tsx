"use client";

import Link from "next/link";

import {
  ArrowRight,
  Award,
  Calendar,
  ChartColumn,
  Clock,
  Filter,
} from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { MOCK_RESULTS, type InterviewTypeLabel } from "@/data/mock";
import { cx } from "@/lib/utils";
import { useMemo, useState } from "react";

const TYPE_TONES: Record<InterviewTypeLabel, BadgeTone> = {
  Technical: "ai",
  Behavioral: "success",
  HR: "neutral",
  Mixed: "warning",
  "System Design": "brand",
};

const SORTS = [
  { id: "recent", label: "Most recent" },
  { id: "score", label: "Highest score" },
  { id: "low", label: "Lowest score" },
] as const;

export default function ResultsPage() {
  const [sort, setSort] = useState<(typeof SORTS)[number]["id"]>("recent");

  const results = useMemo(() => {
    const items = [...MOCK_RESULTS];
    if (sort === "score") {
      items.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    } else if (sort === "low") {
      items.sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
    }
    return items;
  }, [sort]);

  const average =
    results.length > 0
      ? Math.round(
          results.reduce((sum, item) => sum + (item.score ?? 0), 0) /
            results.length,
        )
      : 0;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-ink">Results</h2>
          <p className="mt-1.5 text-sm text-ink-2">
            Scores and reports from your completed interviews.
          </p>
        </div>
        <ButtonLink href="/practice" icon={<ArrowRight className="h-4 w-4" />}>
          Practice now
        </ButtonLink>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-card border border-line bg-card p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <p className="text-[13px] font-medium text-ink-2">Completed</p>
          <p className="mt-2 text-[26px] font-bold leading-none text-ink">
            {results.length}
          </p>
        </div>
        <div className="rounded-card border border-line bg-card p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <p className="text-[13px] font-medium text-ink-2">Average score</p>
          <p className="mt-2 text-[26px] font-bold leading-none text-ink">
            {average}
            <span className="text-base font-medium text-ink-3">%</span>
          </p>
        </div>
        <div className="rounded-card border border-line bg-card p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <p className="text-[13px] font-medium text-ink-2">Best score</p>
          <p className="mt-2 flex items-center gap-2 text-[26px] font-bold leading-none text-ink">
            {Math.max(...results.map((item) => item.score ?? 0))}
            <span className="text-base font-medium text-ink-3">%</span>
            <Award className="h-5 w-5 text-brand" aria-hidden />
          </p>
        </div>
      </section>

      <section className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-[13px] font-medium text-ink-2">
          <Filter className="h-4 w-4 text-ink-3" aria-hidden />
          Sort
        </span>
        {SORTS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setSort(item.id)}
            aria-pressed={sort === item.id}
            className={cx(
              "rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors",
              sort === item.id
                ? "border-brand bg-brand-100 text-brand-hover"
                : "border-line bg-card text-ink-2 hover:bg-mist",
            )}
          >
            {item.label}
          </button>
        ))}
      </section>

      {results.length === 0 ? (
        <EmptyState
          icon={<ChartColumn className="h-6 w-6" />}
          title="No results yet"
          description="Complete a mock interview to see your score report here."
          action={
            <ButtonLink href="/practice">Start Interview</ButtonLink>
          }
        />
      ) : (
        <ul className="space-y-3">
          {results.map((item) => (
            <li key={item.id}>
              <Link
                href={`/interviews/${item.id}/result`}
                className="group flex flex-wrap items-center gap-4 rounded-card border border-line bg-card px-5 py-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-all duration-200 hover:-translate-y-0.5 hover:border-[#f3d3a8] hover:shadow-[0_6px_16px_rgba(16,24,40,0.07)]"
              >
                <span
                  className={cx(
                    "flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-base font-bold tabular-nums",
                    item.score !== null && item.score >= 80
                      ? "bg-[#e7f6ef] text-success"
                      : item.score !== null && item.score >= 70
                        ? "bg-brand-100 text-brand"
                        : "bg-[#fef3e2] text-warning",
                  )}
                >
                  {item.score}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-semibold text-ink">
                    {item.role}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-2">
                    <span className="inline-flex items-center gap-1">
                      <Calendar className="h-3.5 w-3.5" aria-hidden />
                      {item.date}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" aria-hidden />
                      {item.questions} questions
                    </span>
                  </span>
                </span>

                <Badge tone={TYPE_TONES[item.type]}>{item.type}</Badge>

                <span
                  className={cx(
                    "rounded-full px-2.5 py-1 text-xs font-semibold",
                    item.score !== null && item.score >= 80
                      ? "bg-[#e7f6ef] text-success"
                      : "bg-brand-100 text-brand-hover",
                  )}
                >
                  {item.score !== null && item.score >= 80 ? "Strong" : "Good"}
                </span>

                <span className="inline-flex items-center gap-1 text-sm font-medium text-brand opacity-0 transition-opacity group-hover:opacity-100">
                  Report
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
