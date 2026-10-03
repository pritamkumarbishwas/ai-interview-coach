"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Mic, Square } from "lucide-react";

import { AIInterviewer, type AIStatus } from "@/components/interview/ai-interviewer";
import { AIFeedback } from "@/components/interview/ai-feedback";
import { AnswerInput } from "@/components/interview/answer-input";
import { CandidateVideo } from "@/components/interview/candidate-video";
import { EvaluationCard } from "@/components/interview/evaluation-card";
import { InterviewFeed } from "@/components/interview/interview-feed";
import { InterviewProgress } from "@/components/interview/interview-progress";
import { LiveScore } from "@/components/interview/live-score";
import { Modal } from "@/components/ui/modal";
import { useAuth } from "@/hooks/use-auth";
import {
  MOCK_CONVERSATION,
  MOCK_EVALUATION,
  MOCK_FEEDBACK,
  MOCK_FOLLOW_UP_EVALUATIONS,
  MOCK_FOLLOW_UP_FEEDBACK,
  MOCK_QUESTIONS,
  MOCK_SCORES,
  MOCK_SESSION_META,
  type ChatMessage,
  type FeedbackItem,
  type MockEvaluation,
  type MockScoreMetric,
} from "@/data/mock";

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

const TOTAL_QUESTIONS = MOCK_QUESTIONS.length;

const INITIAL_QUESTION_INDEX = Math.min(
  Math.max(MOCK_SESSION_META.questionNumber - 1, 0),
  TOTAL_QUESTIONS - 1,
);

export default function InterviewWorkspacePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const timers = useRef<number[]>([]);

  const [elapsed, setElapsed] = useState(MOCK_SESSION_META.startElapsedSeconds);
  const [questionIndex, setQuestionIndex] = useState(INITIAL_QUESTION_INDEX);
  const [question, setQuestion] = useState(
    MOCK_QUESTIONS[INITIAL_QUESTION_INDEX],
  );
  const questionNumber = questionIndex + 1;
  const [messages, setMessages] = useState<ChatMessage[]>(MOCK_CONVERSATION);
  const [evaluation, setEvaluation] = useState<MockEvaluation | null>(
    MOCK_EVALUATION,
  );
  const [evalState, setEvalState] = useState<"idle" | "pending" | "done">(
    "done",
  );
  const [feedback, setFeedback] = useState<FeedbackItem[]>(MOCK_FEEDBACK);
  const [scores, setScores] = useState(MOCK_SCORES);
  const [aiStatus, setAiStatus] = useState<AIStatus>("listening");
  const [muted, setMuted] = useState(false);
  const [endOpen, setEndOpen] = useState(false);

  const totalQuestions = TOTAL_QUESTIONS;
  const isLastQuestion = questionIndex >= TOTAL_QUESTIONS - 1;
  const followUpIndex = useRef(0);

  useEffect(() => {
    const id = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((id) => window.clearTimeout(id));
  }, []);

  const schedule = (fn: () => void, ms: number) => {
    const id = window.setTimeout(fn, ms);
    timers.current.push(id);
  };

  const submitAnswer = (text: string) => {
    const now = formatTime(elapsed);
    setMessages((prev) => [
      ...prev,
      { id: `c-${Date.now()}`, author: "candidate", text, time: now },
    ]);
    setEvalState("pending");
    setAiStatus("thinking");

    schedule(() => {
      const index = followUpIndex.current % MOCK_FOLLOW_UP_EVALUATIONS.length;
      followUpIndex.current += 1;
      const nextEvaluation = MOCK_FOLLOW_UP_EVALUATIONS[index];
      setEvaluation(nextEvaluation);
      setFeedback(MOCK_FOLLOW_UP_FEEDBACK[index]);
      setEvalState("done");
      setScores((prev) => {
        const overallDelta = nextEvaluation.overall >= 8 ? 1 : -1;
        return {
          ...prev,
          overall: Math.max(0, Math.min(100, prev.overall + overallDelta)),
          metrics: prev.metrics.map((metric, metricIndex) => ({
            ...metric,
            value: Math.max(
              0,
              Math.min(100, metric.value + (metricIndex % 2 === 0 ? 1 : -1)),
            ),
          })) satisfies MockScoreMetric[],
        };
      });
      setAiStatus("speaking");
      schedule(() => setAiStatus("listening"), 1400);
    }, 1600);
  };

  const goNextQuestion = () => {
    if (isLastQuestion) {
      router.push(`/interviews/${params.id}/result`);
      return;
    }
    const nextIndex = questionIndex + 1;
    const nextQuestion = MOCK_QUESTIONS[nextIndex];
    setQuestionIndex(nextIndex);
    setQuestion(nextQuestion);
    setEvaluation(null);
    setEvalState("idle");
    setMessages((prev) => [
      ...prev,
      {
        id: `ai-${Date.now()}`,
        author: "ai",
        text: nextQuestion,
        time: formatTime(elapsed),
      },
    ]);
    setAiStatus("speaking");
    schedule(() => setAiStatus("listening"), 1600);
  };

  const endInterview = () => {
    setEndOpen(false);
    router.push(`/interviews/${params.id}/result`);
  };

  return (
    <div className="space-y-5">
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
            {MOCK_SESSION_META.role} · {MOCK_SESSION_META.type}
          </p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-3">
          <InterviewProgress
            current={questionNumber}
            total={totalQuestions}
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

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <CandidateVideo candidateName={user?.name ?? "Candidate"} />
        <AIInterviewer
          status={aiStatus}
          question={question}
          questionNumber={questionNumber}
          totalQuestions={totalQuestions}
          muted={muted}
          onToggleMute={() => setMuted((value) => !value)}
        />
        <LiveScore
          overall={scores.overall}
          label={scores.label}
          metrics={scores.metrics}
        />
      </section>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="flex flex-col overflow-hidden rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <header className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="text-[15px] font-semibold text-ink">
              Conversation
            </h2>
            <span className="text-xs text-ink-3">{messages.length} messages</span>
          </header>
          <InterviewFeed messages={messages} />
          <AnswerInput onSubmit={submitAnswer} disabled={evalState === "pending"} />
        </div>

        <AIFeedback items={feedback} pending={evalState === "pending"} />

        <EvaluationCard
          evaluation={evaluation}
          state={evalState}
          isLastQuestion={isLastQuestion}
          onNext={goNextQuestion}
          onEnd={() => router.push(`/interviews/${params.id}/result`)}
        />
      </section>

      <Modal
        open={endOpen}
        onClose={() => setEndOpen(false)}
        title="End this interview?"
        description="Your progress will be saved and a report will be generated."
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
            onClick={endInterview}
            className="inline-flex items-center gap-2 rounded-btn bg-danger px-4 py-2 text-sm font-semibold text-white transition-colors hover:brightness-95"
          >
            <Square className="h-3.5 w-3.5" aria-hidden />
            End interview
          </button>
        </div>
      </Modal>
    </div>
  );
}
