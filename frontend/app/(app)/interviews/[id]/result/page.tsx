"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  ArrowLeft,
  Award,
  CircleCheck,
  ClipboardList,
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
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonCard } from "@/components/ui/loading";
import { StatCard } from "@/components/ui/stat-card";
import { AnswerReview } from "@/components/interview/answer-review";
import { RecordingPlayer } from "@/components/interview/recording-player";
import { useAsync } from "@/hooks/use-async";
import { TYPE_LABELS } from "@/lib/interview";
import { formatDateTime, scoreLabel, scoreTone } from "@/lib/utils";
import {
  getInterview,
  getReport,
  hasSessionRecording,
} from "@/services/interviews";

function durationLabel(startedAt: string | null, completedAt: string | null) {
  if (!startedAt || !completedAt) return null;
  const minutes = Math.round(
    (new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 60000,
  );
  return minutes < 1 ? "<1 min" : `${minutes} min`;
}

export default function ResultPage() {
  const params = useParams<{ id: string }>();

  const interviewState = useAsync(() => getInterview(params.id), [params.id]);
  const reportState = useAsync(() => getReport(params.id), [params.id]);

  const interview =
    interviewState.data?.id === params.id ? interviewState.data : null;
  const report =
    reportState.data?.interview_id === params.id ? reportState.data : null;
  const reportError = reportState.error;
  const retryReport = reportState.reload;
  const reloadInterview = interviewState.reload;
  const syncedReportRef = useRef<string | null>(null);
  // The report is fetched in parallel with the interview, so the interview
  // snapshot can predate the persisted evaluations. Refresh it once the report
  // arrives (keyed by interview + generated_at to avoid a render loop).
  useEffect(() => {
    if (!report || report.interview_id !== params.id) return;
    const key = `${report.interview_id}:${report.generated_at}`;
    if (syncedReportRef.current === key) return;
    syncedReportRef.current = key;
    reloadInterview();
  }, [report, reloadInterview, params.id]);
  // The report endpoint blocks (per-interview lock) until evaluation and
  // generation finish, so a single request covers the whole wait — this
  // loading flag stays true for as long as that request is in flight.
  const reportLoading = reportState.loading && !report;

  const notFound =
    reportError?.status === 404 || interviewState.error?.status === 404;
  const reportPending = reportError?.status === 409;

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

  if (interview && interview.status !== "completed") {
    const started = interview.status === "in_progress";
    return (
      <div className="mx-auto max-w-2xl py-10">
        <EmptyState
          icon={<ClipboardList className="h-6 w-6" />}
          title={started ? "Interview still in progress" : "Interview not started"}
          description={
            started
              ? "This session hasn't been completed yet. Return to the interview to finish it, or use End Interview to score the answers given so far."
              : "This interview hasn't been started yet. Start it to answer the questions and generate a report."
          }
          action={
            <div className="flex justify-center gap-3">
              <ButtonLink
                href={`/interviews/${params.id}`}
                variant="primary"
                icon={<Mic className="h-4 w-4" />}
              >
                {started ? "Resume interview" : "Start interview"}
              </ButtonLink>
              <ButtonLink href="/interviews" variant="outline">
                Back to interviews
              </ButtonLink>
            </div>
          }
        />
      </div>
    );
  }

  if (reportLoading) {
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
                Your answers are being evaluated. This usually takes a moment.
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

  if (interview && reportError && !report) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone={reportPending ? "info" : "error"}>
          {reportPending
            ? "The interview is complete, but its report is still being generated. Try again in a moment."
            : reportError.message || "Could not load the report."}
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
  const answered = interview.answers.length;
  const endedEarly = answered < interview.target_questions;
  const meta = [
    interview.role,
    TYPE_LABELS[interview.type],
    formatDateTime(interview.completed_at ?? interview.created_at),
    duration,
    endedEarly ? `Ended early · ${answered} of ${interview.target_questions} answered` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const hasRecording = hasSessionRecording(interview);
  const unevaluated = Math.max(
    0,
    report.total_answers - report.evaluated_answers,
  );
  const extraStudyTopics = report.topics_to_study.filter(
    (topic) => !report.weak_topics.includes(topic),
  );

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link
        href="/interviews"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 transition-colors hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Back to interviews
      </Link>

      <section className="overflow-hidden rounded-card border border-line bg-card shadow-card">
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
          <Badge tone={scoreTone(report.overall_score)}>
            {scoreLabel(report.overall_score)}
          </Badge>
        </div>
      </section>

      {report.partial ? (
        <Alert tone="warning">
          {unevaluated} of {report.total_answers} answer
          {report.total_answers === 1 ? "" : "s"} could not be evaluated. This
          score is based on the answers that were evaluated.
        </Alert>
      ) : null}

      <RecordingPlayer
        interviewId={interview.id}
        available={hasRecording}
        sizeBytes={interview.recordings.camera?.size_bytes}
      />

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
            title="Topics you did well on"
            description="Subjects where your answers scored strongly."
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
                  className="inline-flex items-center gap-1.5 rounded-full border border-success-border bg-success-soft px-3 py-1.5 text-[13px] font-medium text-success-ink"
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
            title="Topics to revisit"
            description="Subjects to focus on in your next session."
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
                    className="inline-flex items-center gap-1.5 rounded-full border border-brand-border bg-brand-soft px-3 py-1.5 text-[13px] font-medium text-brand-ink"
                  >
                    <Target className="h-3.5 w-3.5" aria-hidden />
                    {area}
                  </span>
                ))
              )}
            </div>
            {extraStudyTopics.length > 0 ? (
              <p className="text-[13px] text-ink-2">
                <span className="font-medium text-ink">Also study:</span>{" "}
                {extraStudyTopics.join(", ")}
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
        evaluationsFinal={report.partial}
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
    </div>
  );
}
