"use client";

import { useState } from "react";
import Link from "next/link";

import {
  ArrowRight,
  ArrowUpDown,
  Award,
  Calendar,
  ChartColumn,
  Clock,
  Loader2,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonCard } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { TYPE_LABELS, TYPE_TONES } from "@/lib/interview";
import {
  cx,
  formatDate,
  scoreLabel,
  scoreTone,
} from "@/lib/utils";
import { getResults } from "@/services/interviews";
import type { ResultsSort } from "@/types";

const SORTS: Array<{ id: ResultsSort; label: string }> = [
  { id: "recent", label: "Most recent" },
  { id: "score_desc", label: "Highest score" },
  { id: "score_asc", label: "Lowest score" },
];

const SCORE_STYLES: Record<
  ReturnType<typeof scoreTone>,
  string
> = {
  success: "bg-success-soft text-success-ink",
  brand: "bg-brand-100 text-brand",
  warning: "bg-warning-soft text-warning-ink",
  danger: "bg-danger-soft text-danger-ink",
};

function statValue(value: number | null): string {
  return value === null ? "—" : `${value}`;
}

export default function ResultsPage() {
  const [sort, setSort] = useState<ResultsSort>("recent");
  const state = useAsync(() => getResults(sort), [sort]);
  const data = state.data;
  const items = data?.items ?? [];

  if (state.loading && !data) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-ink">Results</h2>
          <p className="mt-1.5 text-sm text-ink-2">
            Scores and reports from your completed interviews.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (state.error && !data) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone="error">
          {state.error.message || "Could not load your results."}
        </Alert>
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={state.reload}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

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
        <div className="rounded-card border border-line bg-card p-5 shadow-card">
          <p className="text-[13px] font-medium text-ink-2">Completed</p>
          <p className="mt-2 text-[26px] font-bold leading-none text-ink">
            {data?.total ?? 0}
          </p>
        </div>
        <div className="rounded-card border border-line bg-card p-5 shadow-card">
          <p className="text-[13px] font-medium text-ink-2">Average score</p>
          <p className="mt-2 text-[26px] font-bold leading-none text-ink">
            {statValue(data?.average_score ?? null)}
            {data?.average_score != null ? (
              <span className="text-base font-medium text-ink-3">%</span>
            ) : null}
          </p>
        </div>
        <div className="rounded-card border border-line bg-card p-5 shadow-card">
          <p className="text-[13px] font-medium text-ink-2">Best score</p>
          <p className="mt-2 flex items-center gap-2 text-[26px] font-bold leading-none text-ink">
            {statValue(data?.best_score ?? null)}
            {data?.best_score != null ? (
              <span className="text-base font-medium text-ink-3">%</span>
            ) : null}
            <Award className="h-5 w-5 text-brand" aria-hidden />
          </p>
        </div>
      </section>

      <section className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-[13px] font-medium text-ink-2">
          <ArrowUpDown className="h-4 w-4 text-ink-3" aria-hidden />
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
        {state.loading ? (
          <Loader2
            className="h-4 w-4 animate-spin text-ink-3"
            aria-label="Updating results"
          />
        ) : null}
      </section>

      {items.length === 0 ? (
        <EmptyState
          icon={<ChartColumn className="h-6 w-6" />}
          title="No results yet"
          description="Complete an interview to see your score report here."
          action={<ButtonLink href="/practice">Start Interview</ButtonLink>}
        />
      ) : (
        <ul className="space-y-3">
          {items.map((item) => {
            const tone = item.score === null ? null : scoreTone(item.score);
            return (
              <li key={item.id}>
                <Link
                  href={`/interviews/${item.id}/result`}
                  className="group flex flex-wrap items-center gap-4 rounded-card border border-line bg-card px-5 py-4 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-border hover:shadow-card-hover"
                >
                  <span
                    className={cx(
                      "flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-base font-bold tabular-nums",
                      tone
                        ? SCORE_STYLES[tone]
                        : "bg-mist text-ink-3",
                    )}
                  >
                    {item.score === null ? "—" : Math.round(item.score)}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold text-ink">
                      {item.role}
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-2">
                      <span className="inline-flex items-center gap-1">
                        <Calendar className="h-3.5 w-3.5" aria-hidden />
                        {formatDate(item.completed_at ?? item.created_at)}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" aria-hidden />
                        {item.answered_count}/{item.target_questions} answered
                      </span>
                    </span>
                  </span>

                  <Badge tone={TYPE_TONES[item.type]}>
                    {TYPE_LABELS[item.type]}
                  </Badge>

                  <span
                    className={cx(
                      "rounded-full px-2.5 py-1 text-xs font-semibold",
                      tone ? SCORE_STYLES[tone] : "bg-mist text-ink-3",
                    )}
                  >
                    {item.score === null
                      ? "Report pending"
                      : scoreLabel(item.score)}
                  </span>

                  <span className="inline-flex items-center gap-1 text-sm font-medium text-brand opacity-0 transition-opacity group-hover:opacity-100">
                    Report
                    <ArrowRight className="h-4 w-4" aria-hidden />
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
