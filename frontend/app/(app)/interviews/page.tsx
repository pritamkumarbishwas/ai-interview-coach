"use client";

import Link from "next/link";

import { ArrowRight, ClipboardList, Mic, Plus, Search } from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  MOCK_INTERVIEWS,
  type InterviewTypeLabel,
  type MockInterview,
} from "@/data/mock";
import { cx } from "@/lib/utils";
import { useMemo, useState } from "react";

const TYPE_TONES: Record<InterviewTypeLabel, BadgeTone> = {
  Technical: "ai",
  Behavioral: "success",
  HR: "neutral",
  Mixed: "warning",
  "System Design": "brand",
};

const DIFFICULTY_TONES = {
  Beginner: "success",
  Intermediate: "warning",
  Advanced: "danger",
} as const;

export default function InterviewsPage() {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<"All" | InterviewTypeLabel>("All");

  const interviews = useMemo(() => {
    return MOCK_INTERVIEWS.filter((item) => {
      const matchesQuery =
        query.trim() === "" ||
        item.role.toLowerCase().includes(query.trim().toLowerCase());
      const matchesType = typeFilter === "All" || item.type === typeFilter;
      return matchesQuery && matchesType;
    });
  }, [query, typeFilter]);

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
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by type">
          {(
            [
              "All",
              "Technical",
              "Behavioral",
              "HR",
              "System Design",
              "Mixed",
            ] as const
          ).map((type) => (
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
                {type}
              </button>
            ),
          )}
        </div>
      </section>

      {interviews.length === 0 ? (
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
          {interviews.map((item) => (
            <InterviewCard key={item.id} interview={item} />
          ))}
        </ul>
      )}
    </div>
  );
}

function InterviewCard({ interview }: { interview: MockInterview }) {
  const completed = interview.status === "completed";

  return (
    <li className="group flex flex-col rounded-card border border-line bg-card p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-all duration-200 hover:-translate-y-0.5 hover:border-[#f3d3a8] hover:shadow-[0_6px_16px_rgba(16,24,40,0.07)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold text-ink">
            {interview.role}
          </h3>
          <p className="mt-1 text-[13px] text-ink-2">
            {interview.type} · {interview.questions} questions
          </p>
        </div>
        <Badge tone={completed ? "success" : "brand"}>
          {completed ? "Completed" : "In progress"}
        </Badge>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Badge tone={TYPE_TONES[interview.type]}>{interview.type}</Badge>
        <Badge tone={DIFFICULTY_TONES[interview.difficulty]}>
          {interview.difficulty}
        </Badge>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
        <div>
          {interview.score !== null ? (
            <p className="text-lg font-bold text-ink tabular-nums">
              {interview.score}
              <span className="text-sm font-medium text-ink-3">%</span>
            </p>
          ) : (
            <p className="text-[13px] text-ink-3">No score yet</p>
          )}
          <p className="text-xs text-ink-3">{interview.date}</p>
        </div>
        <Link
          href={`/interviews/${interview.id}`}
          className="inline-flex items-center gap-1.5 rounded-btn border border-line bg-card px-3.5 py-2 text-[13px] font-medium text-ink-2 transition-colors group-hover:border-brand group-hover:bg-brand-50 group-hover:text-brand"
        >
          {completed ? "View report" : "Resume"}
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      </div>
    </li>
  );
}
