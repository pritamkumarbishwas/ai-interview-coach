"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ArrowLeft,
  Award,
  CircleCheck,
  Lightbulb,
  Loader2,
  Mic,
  Sparkles,
  Target,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/loading";
import { StatCard } from "@/components/ui/stat-card";
import { AnswerReview } from "@/components/interview/answer-review";
import { RecordingPlayer } from "@/components/interview/recording-player";
import { useAsync } from "@/hooks/use-async";
import { ApiError, toApiError } from "@/lib/api";
import { TYPE_LABELS } from "@/lib/interview";
import { formatDateTime, scoreLabel } from "@/lib/utils";
import {
  getInterview,
  getReport,
  recordingKinds,
} from "@/services/interviews";
import type { Report } from "@/types";

const POLL_INTERVAL_MS = 3_000;
const POLL_MAX_ATTEMPTS = 60; // ~3 minutes

function durationLabel(startedAt: string | null, completedAt: string | null) {
  if (!startedAt || !completedAt) return null;
  const minutes = Math.round(
    (new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 60000,
  );
  return `${Math.max(1, minutes)} min`;
}

/**
 * Loads the report, polling every 3s while it is still being generated
 * (409 = interview not finished, 404 = report not cached yet). Gives up after
 * ~3 minutes and shows a manual retry.
 */
function useReportPolling(interviewId: string) {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [pollAttempt, setPollAttempt] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let count = 0;

    const load = async () => {
      setLoading(true);
      try {
        const data = await getReport(interviewId);
        if (cancelled) return;
        setReport(data);
        setError(null);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        const apiErr = toApiError(err);
        // 409 (not finished) and 404 (not cached yet) are transient while the
        // background evaluation pipeline is still running — keep polling.
        if (
          (apiErr.status === 409 || apiErr.status === 404) &&
          count < POLL_MAX_ATTEMPTS
        ) {
          count += 1;
          setPollAttempt(count);
          timer = setTimeout(load, POLL_INTERVAL_MS);
        } else {
          setError(apiErr);
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [interviewId, reloadKey]);

  const retry = useCallback(() => {
    setReport(null);
    setError(null);
    setLoading(true);
    setPollAttempt(0);
    setReloadKey((k) => k + 1);
  }, []);

  return {
    report,
    loading,
    error,
    retry,
    polling: pollAttempt > 0 && !report,
  };
}

export default function ResultPage() {
  const params = useParams<{ id: string }>();

  const interviewState = useAsync(() => getInterview(params.id), [params.id]);
  const {
    report,
    loading: reportLoading,
    error: reportError,
    retry: retryReport,
    polling,
  } = useReportPolling(params.id);

  const interview = interviewState.data;

  const notFound =
    reportError?.status === 404 || interviewState.error?.status === 404;

  if (interviewState.loading && !interview && !interviewState.error) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <SkeletonCard />
      </div>
    );
  }

  if (notFound || (!interview && interviewState.error)) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone="error">
          {interviewState.error?.message || "Interview not found."}
        </Alert>
        <div className="mt-4 flex justify-center">
          <ButtonLink href="/interviews" variant="outline">
            Back to interviews
          </ButtonLink>
        </div>
      </div>
    );
  }

  // Show a "generating" state while the report is still being computed.
  if (reportLoading && !report) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <Link
          href="/interviews"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to interviews
        </Link>
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <Loader2 className="h-8 w-8 animate-spin text-brand" aria-hidden />
            <div>
              <p className="text-[15px] font-semibold text-ink">
                Generating your report…
              </p>
              <p className="mt-1 text-sm text-ink-2">
                Your answers are being evaluated. This usually takes a few
                minutes.
              </p>
            </div>
          </CardContent>
        </Card>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    );
  }

  if (reportError && !report) {
    // Interview finished but report failed to load after polling cap.
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone="error">
          {reportError.message || "Could not load the report."}
        </Alert>
        <div className="mt-4 flex justify-center gap-3">
          <Button variant="outline" onClick={retryReport}>
            Try again
          </Button>
          <ButtonLink href="/interviews" variant="outline">
            Back to interviews
          </ButtonLink>
        </div>
      </div>
    );
  }

  if (!report || !interview) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  const duration = durationLabel(interview.started_at, interview.completed_at);
  const meta = [
    interview.role,
    TYPE_LABELS[interview.type],
    formatDateTime(interview.completed_at ?? interview.created_at),
    duration,
  ]
    .filter(Boolean)
    .join(" · ");

  const kinds = recordingKinds(interview);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link
        href="/interviews"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 transition-colors hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Back to interviews
      </Link>

      <section className="overflow-hidden rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
        <div className="flex flex-col items-center gap-5 bg-gradient-to-b from-brand-50 to-card px-6 py-8 text-center sm:px-8">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-white shadow-md">
            <Award className="h-7 w-7" aria-hidden />
          </span>
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-ink">
              Interview Complete
            </h2>
            <p className="mt-1 text-sm text-ink-2">{meta}</p>
          </div>
          <div className="flex items-end gap-2">
            <span className="text-6xl font-bold leading-none tracking-tight text-ink tabular-nums">
              {report.overall_score}
            </span>
            <span className="pb-1.5 text-xl font-semibold text-ink-3">/100</span>
          </div>
          <Badge tone="brand">{scoreLabel(report.overall_score)}</Badge>
        </div>
      </section>

      <RecordingPlayer interviewId={interview.id} kinds={kinds} />

      <section
        className="grid grid-cols-1 gap-4 sm:grid-cols-3"
        aria-label="Performance breakdown"
      >
        <StatCard
          label="Overall"
          value={`${report.overall_score}%`}
          icon={<Award className="h-4 w-4" />}
        />
        <StatCard
          label="Technical"
          value={`${report.technical_score}%`}
          icon={<Target className="h-4 w-4" />}
        />
        <StatCard
          label="Communication"
          value={`${report.communication_score}%`}
          icon={<Sparkles className="h-4 w-4" />}
        />
      </section>

      {report.narrative ? (
        <Card>
          <CardHeader
            title="Coach's assessment"
            description="What the AI interviewer noticed across the session."
          />
          <CardContent>
            <p className="text-sm leading-relaxed text-ink-2">
              {report.narrative}
            </p>
          </CardContent>
        </Card>
      ) : null}

      <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card>
          <CardHeader
            title="Strong Areas"
            description="Dimensions you scored well on."
          />
          <CardContent className="flex flex-wrap gap-2">
            {report.strong_topics.length === 0 ? (
              <p className="text-sm text-ink-2">
                No strong topics flagged this time.
              </p>
            ) : (
              report.strong_topics.map((area) => (
                <span
                  key={area}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[#bfe8d5] bg-[#e7f6ef] px-3 py-1.5 text-[13px] font-medium text-[#18794e]"
                >
                  <CircleCheck className="h-3.5 w-3.5" aria-hidden />
                  {area}
                </span>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Needs Improvement"
            description="Focus areas for your next session."
          />
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {report.weak_topics.length === 0 ? (
                <p className="text-sm text-ink-2">
                  Nothing flagged — nice work.
                </p>
              ) : (
                report.weak_topics.map((area) => (
                  <span
                    key={area}
                    className="inline-flex items-center gap-1.5 rounded-full border border-[#f3d3a8] bg-brand-50 px-3 py-1.5 text-[13px] font-medium text-brand-hover"
                  >
                    <Target className="h-3.5 w-3.5" aria-hidden />
                    {area}
                  </span>
                ))
              )}
            </div>
            {report.topics_to_study.length > 0 ? (
              <p className="text-[13px] text-ink-2">
                <span className="font-medium text-ink">Study next:</span>{" "}
                {report.topics_to_study.join(", ")}
              </p>
            ) : null}
          </CardContent>
        </Card>
      </section>

      {report.preparation_plan.length > 0 ? (
        <Card>
          <CardHeader
            title="Preparation Plan"
            description="Concrete steps to raise your score."
          />
          <CardContent className="space-y-3">
            {report.preparation_plan.map((step, index) => (
              <div
                key={`${step.focus}-${index}`}
                className="flex items-start gap-3 rounded-xl border border-line bg-surface p-4"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand">
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">{step.focus}</p>
                  <ul className="mt-1 space-y-1">
                    {step.actions.map((action) => (
                      <li
                        key={action}
                        className="flex gap-2 text-[13px] text-ink-2"
                      >
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand" />
                        {action}
                      </li>
                    ))}
                  </ul>
                </div>
                <Lightbulb
                  className="ml-auto mt-1 h-4 w-4 shrink-0 text-brand"
                  aria-hidden
                />
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <AnswerReview
        questions={interview.questions}
        answers={interview.answers}
      />

      <section className="flex flex-wrap items-center justify-center gap-3 pb-4">
        <ButtonLink
          href="/practice"
          size="lg"
          icon={<Mic className="h-4 w-4" />}
        >
          Start Another Interview
        </ButtonLink>
        <ButtonLink href="/interviews" variant="outline" size="lg">
          My Interviews
        </ButtonLink>
      </section>

      {polling ? (
        <p className="pb-2 text-center text-xs text-ink-3">
          Some answers are still being evaluated — refresh shortly for updated
          scores.
        </p>
      ) : null}
    </div>
  );
}
