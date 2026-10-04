"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Mic, Play, Square } from "lucide-react";

import {
  AIInterviewer,
  type AIStatus,
} from "@/components/interview/ai-interviewer";
import { AIFeedback } from "@/components/interview/ai-feedback";
import { AnswerInput } from "@/components/interview/answer-input";
import { CandidateVideo } from "@/components/interview/candidate-video";
import { EvaluationCard } from "@/components/interview/evaluation-card";
import { InterviewFeed } from "@/components/interview/interview-feed";
import { InterviewProgress } from "@/components/interview/interview-progress";
import { LiveScore } from "@/components/interview/live-score";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { FullScreenLoader } from "@/components/ui/loading";
import { Modal } from "@/components/ui/modal";
import { useAsync } from "@/hooks/use-async";
import { useAuth } from "@/hooks/use-auth";
import { toApiError } from "@/lib/api";
import { TYPE_LABELS } from "@/lib/interview";
import { scoreLabel } from "@/lib/utils";
import {
  findCurrentQuestion,
  getInterview,
  startInterview,
  submitAnswer as submitAnswerApi,
} from "@/services/interviews";
import type { Evaluation, InterviewDetail, Question } from "@/types";
import type {
  ChatMessage,
  FeedbackItem,
  MockScoreMetric,
} from "@/data/mock";

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function timeSince(startedAt: string | null, iso: string): string {
  if (!startedAt) return "";
  const started = new Date(startedAt).getTime();
  const at = new Date(iso).getTime();
  if (!Number.isFinite(started) || !Number.isFinite(at)) return "";
  return formatTime(Math.max(0, Math.floor((at - started) / 1000)));
}

/** Rebuild the conversation from stored questions + answers. */
function seedMessages(interview: InterviewDetail): ChatMessage[] {
  const out: ChatMessage[] = [];
  const answersByQuestion = new Map(
    interview.answers.map((answer) => [answer.question_id, answer]),
  );
  for (const question of interview.questions) {
    const answer = answersByQuestion.get(question.id);
    out.push({
      id: `ai-${question.id}`,
      author: "ai",
      text: question.text,
      time: answer
        ? timeSince(interview.started_at, answer.created_at)
        : formatTime(0),
    });
    if (!answer) break;
    out.push({
      id: `c-${answer.id}`,
      author: "candidate",
      text: answer.text,
      time: timeSince(interview.started_at, answer.created_at),
    });
  }
  return out;
}

function feedbackFrom(evaluation: Evaluation): FeedbackItem[] {
  const items: FeedbackItem[] = [];
  if (evaluation.strengths.length > 0) {
    items.push({
      id: "fb-strengths",
      tone: "good",
      title: "Strengths",
      detail: evaluation.strengths.join(" · "),
    });
  }
  if (evaluation.weaknesses.length > 0) {
    items.push({
      id: "fb-weaknesses",
      tone: "improve",
      title: "To improve",
      detail: evaluation.weaknesses.join(" · "),
    });
  }
  items.push({
    id: "fb-feedback",
    tone: "good",
    title: "Coach feedback",
    detail: evaluation.feedback,
  });
  return items;
}

function metricsFrom(evaluation: Evaluation): MockScoreMetric[] {
  return [
    { label: "Technical", value: evaluation.scores.technical },
    { label: "Relevance", value: evaluation.scores.relevance },
    { label: "Completeness", value: evaluation.scores.completeness },
    { label: "Structure", value: evaluation.scores.structure },
    { label: "Clarity", value: evaluation.scores.clarity },
  ];
}

export default function InterviewWorkspacePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const { user } = useAuth();

  const {
    data: interview,
    loading,
    error,
    reload,
  } = useAsync(() => getInterview(params.id), [params.id]);

  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [evalState, setEvalState] = useState<"idle" | "pending" | "done">(
    "idle",
  );
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [pendingNext, setPendingNext] = useState<Question | null>(null);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [aiStatus, setAiStatus] = useState<AIStatus>("listening");
  const [muted, setMuted] = useState(false);
  const [endOpen, setEndOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const seededRef = useRef("");
  const timers = useRef<number[]>([]);

  // Seed session state from the loaded interview (first load or after start).
  useEffect(() => {
    if (!interview) return;
    const signature = `${interview.id}:${interview.status}:${interview.questions.length}`;
    if (seededRef.current === signature) return;
    seededRef.current = signature;

    setMessages(seedMessages(interview));
    setEvaluations(interview.answers.map((answer) => answer.evaluation));
    setCurrentQuestion(findCurrentQuestion(interview));
    setCompleted(interview.status === "completed");
    if (interview.status === "completed") {
      router.replace(`/interviews/${interview.id}/result`);
    }
  }, [interview, router]);

  // Session clock driven by the server-side start time.
  useEffect(() => {
    if (!interview?.started_at || interview.status === "completed") return;
    const started = new Date(interview.started_at).getTime();
    if (!Number.isFinite(started)) return;
    const tick = () =>
      setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [interview?.started_at, interview?.status]);

  useEffect(() => {
    if (interview && interview.status !== "created") {
      setStarting(false);
    }
  }, [interview]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((id) => window.clearTimeout(id));
  }, []);

  const schedule = (fn: () => void, ms: number) => {
    const id = window.setTimeout(fn, ms);
    timers.current.push(id);
  };

  if (loading && !interview) {
    return <FullScreenLoader label="Loading interview" />;
  }

  if (error || !interview) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone="error">
          {error?.message || "Interview not found."}
        </Alert>
        <div className="mt-4 flex justify-center gap-3">
          <Button variant="outline" onClick={reload}>
            Try again
          </Button>
          <Button onClick={() => router.push("/interviews")}>
            Back to interviews
          </Button>
        </div>
      </div>
    );
  }

  const targetQuestions = interview.target_questions;
  const answeredCount = evaluations.length;
  const isLastQuestion = answeredCount >= targetQuestions;
  const questionNumber = currentQuestion
    ? currentQuestion.sequence
    : Math.max(answeredCount, 1);

  const runningOverall =
    evaluations.length > 0
      ? Math.round(
          evaluations.reduce((sum, item) => sum + item.overall, 0) /
            evaluations.length,
        )
      : 0;
  const lastEvaluation = evaluations[evaluations.length - 1] ?? null;

  const handleStart = async () => {
    if (starting) return;
    setStarting(true);
    setStartError(null);
    try {
      await startInterview(params.id);
      reload();
    } catch (err) {
      setStartError(toApiError(err).message);
      setStarting(false);
    }
  };

  const submitAnswer = async (text: string): Promise<void> => {
    if (!currentQuestion || completed) {
      throw new Error("No question available.");
    }
    const messageId = `c-${Date.now()}`;
    const time = formatTime(elapsed);
    setAnswerError(null);
    setMessages((prev) => [
      ...prev,
      { id: messageId, author: "candidate", text, time },
    ]);
    setEvalState("pending");
    setAiStatus("thinking");
    try {
      const result = await submitAnswerApi(currentQuestion.id, text);
      setEvaluation(result.evaluation);
      setEvaluations((prev) => [...prev, result.evaluation]);
      setPendingNext(result.next_question);
      setFeedback(feedbackFrom(result.evaluation));
      setEvalState("done");
      if (result.status === "completed") {
        setCompleted(true);
      }
      setAiStatus("speaking");
      schedule(() => setAiStatus("listening"), 1400);
    } catch (err) {
      const apiError = toApiError(err);
      // Roll back the optimistic message; the text stays in the input.
      setMessages((prev) => prev.filter((item) => item.id !== messageId));
      setEvalState("idle");
      setAiStatus("listening");
      setAnswerError(apiError.message);
      throw err;
    }
  };

  const goNextQuestion = () => {
    if (!pendingNext || completed) {
      router.push(`/interviews/${params.id}/result`);
      return;
    }
    const next = pendingNext;
    setCurrentQuestion(next);
    setPendingNext(null);
    setEvaluation(null);
    setEvalState("idle");
    setFeedback([]);
    setMessages((prev) => [
      ...prev,
      {
        id: `ai-${next.id}`,
        author: "ai",
        text: next.text,
        time: formatTime(elapsed),
      },
    ]);
    setAiStatus("speaking");
    schedule(() => setAiStatus("listening"), 1600);
  };

  const leaveInterview = () => {
    setEndOpen(false);
    router.push("/interviews");
  };

  const header = (
    <header className="flex flex-wrap items-center gap-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-danger/10 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-danger">
            <span className="h-1.5 w-1.5 rounded-full bg-danger animate-pulse-dot" />
            Live
          </span>
          <h2 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">
            Mock Interview Session
          </h2>
        </div>
        <p className="mt-1 text-sm text-ink-2">
          {interview.role} · {TYPE_LABELS[interview.type]}
        </p>
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-3">
        <InterviewProgress
          current={Math.min(questionNumber, targetQuestions)}
          total={targetQuestions}
        />
        <div className="flex items-center gap-2 rounded-btn border border-line bg-card px-3 py-2 shadow-sm">
          <Mic className="h-4 w-4 text-success" aria-hidden />
          <span className="text-sm font-semibold tabular-nums text-ink">
            {formatTime(elapsed)}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setEndOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-btn border border-[#f5c6c7] bg-[#fdf0f0] px-3.5 py-2 text-sm font-medium text-danger transition-colors hover:bg-[#fbe6e6]"
        >
          <Square className="h-3.5 w-3.5" aria-hidden />
          End Interview
        </button>
      </div>
    </header>
  );

  if (interview.status === "created") {
    return (
      <div className="space-y-5">
        {header}
        <Card className="mx-auto max-w-xl">
          <CardHeader
            title="Ready to begin?"
            description={`${targetQuestions} questions · ${TYPE_LABELS[interview.type]} interview. The AI interviewer will ask one question at a time.`}
          />
          <CardContent className="space-y-4">
            {startError ? <Alert tone="error">{startError}</Alert> : null}
            <Button
              variant="primary"
              onClick={handleStart}
              disabled={starting}
              loading={starting}
              icon={<Play className="h-4 w-4" />}
              className="w-full"
            >
              {starting ? "Generating first question…" : "Start Interview"}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {header}

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <CandidateVideo candidateName={user?.name ?? "Candidate"} />
        <AIInterviewer
          status={aiStatus}
          question={currentQuestion?.text ?? ""}
          questionNumber={Math.min(questionNumber, targetQuestions)}
          totalQuestions={targetQuestions}
          muted={muted}
          onToggleMute={() => setMuted((value) => !value)}
        />
        <LiveScore
          overall={runningOverall}
          label={lastEvaluation ? scoreLabel(runningOverall) : "Not started"}
          metrics={lastEvaluation ? metricsFrom(lastEvaluation) : []}
        />
      </section>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="flex flex-col overflow-hidden rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <header className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="text-[15px] font-semibold text-ink">
              Conversation
            </h2>
            <span className="text-xs text-ink-3">
              {messages.length} messages
            </span>
          </header>
          <InterviewFeed messages={messages} />
          {answerError ? (
            <div className="border-t border-line px-4 pt-3">
              <Alert tone="error">
                Couldn&apos;t submit your answer: {answerError} — your text is
                still in the box.
              </Alert>
              <div className="h-3" />
            </div>
          ) : null}
          <AnswerInput
            onSubmit={submitAnswer}
            disabled={evalState === "pending" || completed}
          />
        </div>

        <AIFeedback items={feedback} pending={evalState === "pending"} />

        <EvaluationCard
          evaluation={evaluation}
          state={evalState}
          isLastQuestion={isLastQuestion || completed}
          onNext={goNextQuestion}
          onEnd={() => router.push(`/interviews/${params.id}/result`)}
        />
      </section>

      <Modal
        open={endOpen}
        onClose={() => setEndOpen(false)}
        title="Leave this interview?"
        description="Your answers are saved. You can resume from My Interviews — the report is generated once every question is answered."
      >
        <div className="flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => setEndOpen(false)}
            className="rounded-btn border border-line bg-card px-4 py-2 text-sm font-medium text-ink-2 transition-colors hover:bg-mist"
          >
            Keep going
          </button>
          <button
            type="button"
            onClick={leaveInterview}
            className="inline-flex items-center gap-2 rounded-btn bg-danger px-4 py-2 text-sm font-semibold text-white transition-colors hover:brightness-95"
          >
            <Square className="h-3.5 w-3.5" aria-hidden />
            Leave interview
          </button>
        </div>
      </Modal>
    </div>
  );
}
