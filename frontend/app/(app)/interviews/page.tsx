"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Loader2,
  Mic,
  Plus,
  Search,
  Trash,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SkeletonList } from "@/components/ui/loading";
import { Modal } from "@/components/ui/modal";
import { StatusBadge } from "@/components/ui/status-badge";
import { useAsync } from "@/hooks/use-async";
import { toApiError } from "@/lib/api";
import {
  DIFFICULTY_LABELS,
  STATUS_LABELS,
  TYPE_LABELS,
  TYPE_TONES,
} from "@/lib/interview";
import { cx, formatDate, scoreLabel, scoreTone } from "@/lib/utils";
import { deleteInterview, listInterviews } from "@/services/interviews";
import type {
  Difficulty,
  InterviewStatus,
  InterviewSummary,
  InterviewType,
} from "@/types";

const DIFFICULTY_TONES: Record<Difficulty, BadgeTone> = {
  beginner: "success",
  intermediate: "warning",
  advanced: "danger",
};

const PAGE_SIZE = 24;
const SEARCH_DEBOUNCE_MS = 400;

const TYPE_FILTERS = [
  "all",
  "technical",
  "behavioral",
  "hr",
  "system_design",
  "mixed",
] as const;

type StatusFilter = "all" | InterviewStatus;

const STATUS_FILTERS: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: "created", label: STATUS_LABELS.created },
  { value: "in_progress", label: STATUS_LABELS.in_progress },
  { value: "completed", label: STATUS_LABELS.completed },
];

export default function InterviewsPage() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | InterviewType>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [offset, setOffset] = useState(0);
  const [pendingDelete, setPendingDelete] = useState<InterviewSummary | null>(
    null,
  );
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Debounce typing so every keystroke does not hit the API.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(query.trim());
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const {
    data,
    loading,
    error,
    reload,
  } = useAsync(
    () =>
      listInterviews({
        limit: PAGE_SIZE,
        offset,
        status: statusFilter === "all" ? undefined : statusFilter,
        type: typeFilter === "all" ? undefined : typeFilter,
        q: search || undefined,
      }),
    [offset, statusFilter, typeFilter, search],
    { keepPreviousData: true },
  );

  const interviews = data?.items ?? [];
  const total = data?.total ?? 0;
  const hasMore = data?.has_more ?? false;
  const activeFilters =
    search !== "" || typeFilter !== "all" || statusFilter !== "all";
  const rangeStart = total === 0 ? 0 : (data?.offset ?? 0) + 1;
  const rangeEnd = (data?.offset ?? 0) + interviews.length;

  const closeDeleteDialog = () => {
    if (deleting) return;
    setPendingDelete(null);
    setDeleteError(null);
  };

  const discard = async () => {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteInterview(pendingDelete.id);
      setPendingDelete(null);
      // Deleting the only row on a later page would leave it empty.
      if (interviews.length === 1 && offset > 0) {
        setOffset(Math.max(0, offset - PAGE_SIZE));
      } else {
        reload();
      }
    } catch (caught) {
      setDeleteError(toApiError(caught).message);
    } finally {
      setDeleting(false);
    }
  };

  if (error && !data) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone="error">
          {error.message || "Could not load your interviews."}
        </Alert>
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={reload}>
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

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
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
          {loading && data ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-ink-3">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              Updating
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label="Filter by type"
          >
            {TYPE_FILTERS.map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => {
                  setTypeFilter(type);
                  setOffset(0);
                }}
                aria-pressed={typeFilter === type}
                className={cx(
                  "rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors",
                  typeFilter === type
                    ? "border-brand bg-brand-100 text-brand-hover"
                    : "border-line bg-card text-ink-2 hover:bg-mist",
                )}
              >
                {type === "all" ? "All types" : TYPE_LABELS[type]}
              </button>
            ))}
          </div>

          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label="Filter by status"
          >
            {STATUS_FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => {
                  setStatusFilter(item.value);
                  setOffset(0);
                }}
                aria-pressed={statusFilter === item.value}
                className={cx(
                  "rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors",
                  statusFilter === item.value
                    ? "border-brand bg-brand-100 text-brand-hover"
                    : "border-line bg-card text-ink-2 hover:bg-mist",
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error ? (
        <div className="space-y-3">
          <Alert tone="error">
            {error.message || "Could not update your interviews."}
          </Alert>
          <Button variant="outline" onClick={reload}>
            Try again
          </Button>
        </div>
      ) : null}

      {loading && !data ? (
        <SkeletonList rows={4} />
      ) : interviews.length === 0 ? (
        <EmptyState
          icon={<ClipboardList className="h-6 w-6" />}
          title={activeFilters ? "No interviews match" : "No interviews yet"}
          description={
            activeFilters
              ? "Try a different search or filter, or start a new mock interview."
              : "Start your first mock interview to see it here."
          }
          action={
            <ButtonLink href="/practice" icon={<Mic className="h-4 w-4" />}>
              Start Interview
            </ButtonLink>
          }
        />
      ) : (
        <>
          <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {interviews.map((item) => (
              <InterviewCard
                key={item.id}
                interview={item}
                onDiscard={() => {
                  setDeleteError(null);
                  setPendingDelete(item);
                }}
              />
            ))}
          </ul>

          <nav
            className="flex flex-wrap items-center justify-between gap-3"
            aria-label="Interview pages"
          >
            <p className="text-[13px] text-ink-2">
              Showing {rangeStart}–{rangeEnd} of {total}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0 || loading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                icon={<ChevronLeft className="h-3.5 w-3.5" />}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!hasMore || loading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </nav>
        </>
      )}

      <Modal
        open={pendingDelete !== null}
        onClose={closeDeleteDialog}
        title="Discard this interview?"
        description={
          pendingDelete
            ? `${pendingDelete.role} · ${TYPE_LABELS[pendingDelete.type]}`
            : undefined
        }
      >
        <div className="space-y-4">
          {deleteError ? <Alert tone="error">{deleteError}</Alert> : null}
          <p className="text-sm leading-relaxed text-ink-2">
            Its answers and any saved recording will be deleted. This cannot be
            undone. Completed interviews are kept as reports.
          </p>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={closeDeleteDialog}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={deleting}
              onClick={() => void discard()}
            >
              Discard interview
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function InterviewCard({
  interview,
  onDiscard,
}: {
  interview: InterviewSummary;
  onDiscard: () => void;
}) {
  const completed = interview.status === "completed";
  const href =
    interview.status === "completed"
      ? `/interviews/${interview.id}/result`
      : `/interviews/${interview.id}`;

  return (
    <li className="group flex flex-col rounded-card border border-line bg-card p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-border hover:shadow-card-hover">
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

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Badge tone={TYPE_TONES[interview.type]}>
          {TYPE_LABELS[interview.type]}
        </Badge>
        <Badge tone={DIFFICULTY_TONES[interview.difficulty]}>
          {DIFFICULTY_LABELS[interview.difficulty]}
        </Badge>
        {interview.score !== null ? (
          <Badge tone={scoreTone(interview.score)}>
            {Math.round(interview.score)}% · {scoreLabel(interview.score)}
          </Badge>
        ) : completed ? (
          <Badge tone="muted">Report pending</Badge>
        ) : null}
      </div>

      <div className="mt-4 flex items-center justify-between gap-2 border-t border-line pt-4">
        <div>
          <p className="text-[13px] font-medium text-ink-2">
            {STATUS_LABELS[interview.status]}
          </p>
          <p className="text-xs text-ink-3">
            {formatDate(interview.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!completed ? (
            <Button
              variant="ghost"
              size="sm"
              icon={<Trash className="h-3.5 w-3.5" aria-hidden />}
              onClick={onDiscard}
            >
              Discard
            </Button>
          ) : null}
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
      </div>
    </li>
  );
}
