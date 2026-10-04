"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ArrowRight, ClipboardList, Mic, Plus, Search } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SkeletonList } from "@/components/ui/loading";
import { StatusBadge } from "@/components/ui/status-badge";
import { useAsync } from "@/hooks/use-async";
import {
  DIFFICULTY_LABELS,
  STATUS_LABELS,
  TYPE_LABELS,
  TYPE_TONES,
} from "@/lib/interview";
import { cx, formatDate } from "@/lib/utils";
import { listInterviews } from "@/services/interviews";
import type { Difficulty, InterviewSummary, InterviewType } from "@/types";

const DIFFICULTY_TONES: Record<Difficulty, BadgeTone> = {
  beginner: "success",
  intermediate: "warning",
  advanced: "danger",
};

const TYPE_FILTERS = [
  "all",
  "technical",
  "behavioral",
  "hr",
  "system_design",
  "mixed",
] as const;

export default function InterviewsPage() {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | InterviewType>("all");

  const {
    data: interviews,
    loading,
    error,
    reload,
  } = useAsync(listInterviews, []);

  const filtered = useMemo(() => {
    const items = interviews ?? [];
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      const matchesQuery = needle === "" || item.role.toLowerCase().includes(needle);
      const matchesType = typeFilter === "all" || item.type === typeFilter;
      return matchesQuery && matchesType;
    });
  }, [interviews, query, typeFilter]);

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-ink">
            My Interviews
          </h2>
          <p className="mt-1.5 text-sm text-ink-2">
            Every mock interview you have started or completed.
          </p>
        </div>
        <ButtonLink href="/practice" icon={<Plus className="h-4 w-4" />}>
          New Interview
        </ButtonLink>
      </section>

      {error ? (
        <div className="space-y-3">
          <Alert tone="error">
            {error.message || "Could not load your interviews."}
          </Alert>
          <Button variant="outline" onClick={reload}>
            Try again
          </Button>
        </div>
      ) : (
        <>
          <section className="flex flex-wrap items-center gap-3">
            <div className="relative w-full max-w-xs">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
                aria-hidden
              />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by role…"
                aria-label="Search interviews"
                className="pl-9"
              />
            </div>
            <div
              className="flex flex-wrap gap-2"
              role="group"
              aria-label="Filter by type"
            >
              {TYPE_FILTERS.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setTypeFilter(type)}
                  aria-pressed={typeFilter === type}
                  className={cx(
                    "rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors",
                    typeFilter === type
                      ? "border-brand bg-brand-100 text-brand-hover"
                      : "border-line bg-card text-ink-2 hover:bg-mist",
                  )}
                >
                  {type === "all" ? "All" : TYPE_LABELS[type]}
                </button>
              ))}
            </div>
          </section>

          {loading && !interviews ? (
            <SkeletonList rows={4} />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<ClipboardList className="h-6 w-6" />}
              title="No interviews found"
              description="Try a different search, or start a new mock interview."
              action={
                <ButtonLink href="/practice" icon={<Mic className="h-4 w-4" />}>
                  Start Interview
                </ButtonLink>
              }
            />
          ) : (
            <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {filtered.map((item) => (
                <InterviewCard key={item.id} interview={item} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function InterviewCard({ interview }: { interview: InterviewSummary }) {
  const completed = interview.status === "completed";
  const href =
    interview.status === "completed"
      ? `/interviews/${interview.id}/result`
      : `/interviews/${interview.id}`;

  return (
    <li className="group flex flex-col rounded-card border border-line bg-card p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-all duration-200 hover:-translate-y-0.5 hover:border-[#f3d3a8] hover:shadow-[0_6px_16px_rgba(16,24,40,0.07)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold text-ink">
            {interview.role}
          </h3>
          <p className="mt-1 text-[13px] text-ink-2">
            {TYPE_LABELS[interview.type]} · {interview.answered_count}/
            {interview.target_questions} answered
          </p>
        </div>
        <StatusBadge status={interview.status} />
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Badge tone={TYPE_TONES[interview.type]}>
          {TYPE_LABELS[interview.type]}
        </Badge>
        <Badge tone={DIFFICULTY_TONES[interview.difficulty]}>
          {DIFFICULTY_LABELS[interview.difficulty]}
        </Badge>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
        <div>
          <p className="text-[13px] font-medium text-ink-2">
            {STATUS_LABELS[interview.status]}
          </p>
          <p className="text-xs text-ink-3">
            {formatDate(interview.created_at)}
          </p>
        </div>
        <Link
          href={href}
          className="inline-flex items-center gap-1.5 rounded-btn border border-line bg-card px-3.5 py-2 text-[13px] font-medium text-ink-2 transition-colors group-hover:border-brand group-hover:bg-brand-50 group-hover:text-brand"
        >
          {interview.status === "created"
            ? "Start"
            : completed
              ? "View report"
              : "Resume"}
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      </div>
    </li>
  );
}
