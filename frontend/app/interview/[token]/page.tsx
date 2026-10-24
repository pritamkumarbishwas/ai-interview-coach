"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

import {
  Camera,
  CheckCircle2,
  Clock,
  MessageSquare,
  ShieldCheck,
  Square,
  Target,
} from "lucide-react";

import {
  AIInterviewer,
  type AIStatus,
} from "@/components/interview/ai-interviewer";
import { AnswerInput } from "@/components/interview/answer-input";
import { CandidatePanel } from "@/components/interview/candidate-panel";
import { DeviceCheck } from "@/components/interview/device-check";
import { InterviewFeed } from "@/components/interview/interview-feed";
import { InterviewProgress } from "@/components/interview/interview-progress";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FullScreenLoader } from "@/components/ui/loading";
import { Modal } from "@/components/ui/modal";
import { MediaProvider, useMedia } from "@/hooks/use-media";
import { useIntegritySignals } from "@/hooks/use-integrity-signals";
import { useInterviewRecorder } from "@/hooks/use-interview-recorder";
import { toApiError, type ApiError } from "@/lib/api";
import { formatDate, formatElapsed, parseApiDate } from "@/lib/datetime";
import { DIFFICULTY_LABELS, TYPE_LABELS } from "@/lib/interview";
import { PROCTORING_LABELS } from "@/lib/recruiting";
import * as screening from "@/services/screening";
import type { ChatMessage } from "@/data/mock";
import type {
  CurrentQuestion,
  InvitationSession,
  Question,
  ScreeningConversation,
} from "@/types";

type Stage = "precheck" | "device" | "session" | "done";

function formatTime(totalSeconds: number): string {
  const clamped = Math.max(0, totalSeconds);
  const minutes = Math.floor(clamped / 60);
  const seconds = clamped % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function ScreeningInterviewPage() {
  return (
    <MediaProvider>
      <ScreeningInterview />
    </MediaProvider>
  );
}

function ScreeningInterview() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [session, setSession] = useState<InvitationSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiError | null>(null);

  const [stage, setStage] = useState<Stage>("precheck");
  const [consent, setConsent] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [question, setQuestion] = useState<Question | null>(null);
  const [questionNumber, setQuestionNumber] = useState(1);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [aiStatus, setAiStatus] = useState<AIStatus>("listening");
  const [muted, setMuted] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [deadline, setDeadline] = useState<number | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [leaveOpen, setLeaveOpen] = useState(false);

  const startedAtRef = useRef<number>(Date.now());
  const startedAtIsoRef = useRef<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const warnedRef = useRef<Set<number>>(new Set());

  const { cameraStream, screenStream } = useMedia();

  const proctored = session ? session.proctoring_mode !== "off" : false;
  const total = session?.total_questions ?? 5;
  const sessionActive = stage === "session" && !completed;

  const uploadChunk = useCallback(
    (blob: Blob, seq: number, finalize: boolean, captureStartedAtMs: number) =>
      screening.uploadRecordingChunk(
        token,
        seq,
        blob,
        finalize,
        blob.type || "video/webm",
        captureStartedAtMs,
      ),
    [token],
  );

  const recorder = useInterviewRecorder({
    upload: uploadChunk,
    targetQuestions: total,
    active: sessionActive && proctored,
    cameraStream,
    screenStream,
  });
  const { stopAndUpload } = recorder;
  const stoppedRef = useRef(false);

  useEffect(() => {
    if (stage === "done" && !stoppedRef.current) {
      stoppedRef.current = true;
      void stopAndUpload();
    }
  }, [stage, stopAndUpload]);

  const reportSignal = useCallback(
    (type: string, details?: Record<string, unknown>) => {
      if (!proctored) return;
      void screening.recordEvent(token, type, details);
    },
    [proctored, token],
  );

  useIntegritySignals({ enabled: sessionActive && proctored, onSignal: reportSignal });

  const handleSpeechEnd = useCallback(() => setAiStatus("listening"), []);

  const timeLabel = () => formatTime((Date.now() - startedAtRef.current) / 1000);

  const applyQuestion = useCallback((current: CurrentQuestion) => {
    setQuestion(current.question);
    setQuestionNumber(current.question_number);
    setMessages((prev) => [
      ...prev,
      {
        id: `ai-${current.question.id}`,
        author: "ai",
        text: current.question.text,
        time: timeLabel(),
      },
    ]);
    setAiStatus("speaking");
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const current = await screening.getSession(token);
      setSession(current);
      if (current.status === "completed") {
        setCompleted(true);
        setStage("done");
        return;
      }
      if (current.round_deadline) {
        const deadline = parseApiDate(current.round_deadline);
        if (deadline) setDeadline(deadline.getTime());
      }
      if (current.started) {
        // Resuming a started interview: restore the transcript, then the
        // unanswered question. History is best-effort; the current question
        // remains the source of truth.
        let history: ScreeningConversation | null = null;
        try {
          history = await screening.getConversation(token);
        } catch (caught) {
          const apiError = toApiError(caught);
          if (apiError.status === 409) {
            setCompleted(true);
            setStage("done");
            return;
          }
        }

        try {
          const cq = await screening.getCurrentQuestion(token);
          if (history?.started_at) {
            const started = parseApiDate(history.started_at);
            startedAtRef.current = started?.getTime() ?? Date.now();
            startedAtIsoRef.current = history.started_at;
          } else {
            startedAtRef.current = Date.now();
            startedAtIsoRef.current = null;
          }

          const restored: ChatMessage[] = (history?.messages ?? []).map(
            (message) => ({
              id: message.id,
              author: message.author,
              text: message.text,
              time:
                formatElapsed(history?.started_at ?? null, message.created_at) ||
                formatTime(0),
            }),
          );
          const currentMessageId = `ai-${cq.question.id}`;
          if (!restored.some((message) => message.id === currentMessageId)) {
            restored.push({
              id: currentMessageId,
              author: "ai",
              text: cq.question.text,
              time:
                formatElapsed(
                  history?.started_at ?? null,
                  cq.question.created_at,
                ) || formatTime(0),
            });
          }
          setMessages(restored);
          setQuestion(cq.question);
          setQuestionNumber(cq.question_number);
          setAiStatus("speaking");
          setStage("session");
        } catch (caught) {
          const apiError = toApiError(caught);
          if (apiError.status === 409) {
            setCompleted(true);
            setStage("done");
          } else {
            throw caught;
          }
        }
      }
    } catch (caught) {
      setLoadError(toApiError(caught));
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  // Server-authoritative countdown (display only — the API enforces it).
  useEffect(() => {
    if (deadline === null || completed) return;
    const tick = () => {
      const left = Math.floor((deadline - Date.now()) / 1000);
      setRemaining(left);
      if (left <= 0) {
        setCompleted(true);
        setStage("done");
      }
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [deadline, completed]);

  // Screen-reader announcements: the current question, then time warnings.
  useEffect(() => {
    if (!question) return;
    setAnnouncement(
      `Question ${Math.min(questionNumber, total)} of ${total}: ${question.text}`,
    );
  }, [question, questionNumber, total]);

  useEffect(() => {
    if (remaining === null) return;
    for (const mark of [300, 60]) {
      if (remaining <= mark && !warnedRef.current.has(mark)) {
        warnedRef.current.add(mark);
        setAnnouncement(
          mark >= 300 ? "Five minutes remaining." : "One minute remaining.",
        );
      }
    }
  }, [remaining]);

  const doStart = async (consentValue: boolean) => {
    setStarting(true);
    setStartError(null);
    try {
      const cq = await screening.startInterview(token, consentValue);
      startedAtRef.current = Date.now();
      startedAtIsoRef.current = null;
      setMessages([]);
      applyQuestion(cq);
      // Refresh for the server deadline + updated status.
      const refreshed = await screening.getSession(token);
      setSession(refreshed);
      if (refreshed.round_deadline) {
        const deadline = parseApiDate(refreshed.round_deadline);
        if (deadline) setDeadline(deadline.getTime());
      }
      setStage("session");
    } catch (caught) {
      setStartError(toApiError(caught).message);
    } finally {
      setStarting(false);
    }
  };

  const onBegin = () => {
    if (session?.proctoring_mode === "off") {
      void doStart(consent);
    } else {
      setStage("device");
    }
  };

  const submitAnswer = async (text: string): Promise<void> => {
    if (!question || completed) throw new Error("No question available.");
    const messageId = `c-${Date.now()}`;
    setAnswerError(null);
    setMessages((prev) => [
      ...prev,
      { id: messageId, author: "candidate", text, time: timeLabel() },
    ]);
    setAiStatus("thinking");
    try {
      const result = await screening.submitAnswer(token, question.id, text);
      if (result.status === "completed") {
        setCompleted(true);
        setStage("done");
        return;
      }
      const next = result.next_question;
      if (next) {
        const nextTime =
          formatElapsed(startedAtIsoRef.current, next.created_at) || timeLabel();
        setQuestion(next);
        setQuestionNumber(result.questions_answered + 1);
        setMessages((prev) => [
          ...prev,
          { id: `ai-${next.id}`, author: "ai", text: next.text, time: nextTime },
        ]);
        setAiStatus("speaking");
      } else {
        setCompleted(true);
        setStage("done");
      }
    } catch (caught) {
      setMessages((prev) => prev.filter((item) => item.id !== messageId));
      setAiStatus("listening");
      setAnswerError(toApiError(caught).message);
      throw caught;
    }
  };

  if (loading && !session) {
    return <FullScreenLoader label="Loading your interview" />;
  }

  if (loadError || !session) {
    const status = loadError?.status;
    return (
      <div className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6 py-16 text-center">
        <Alert tone="error">
          {status === 404
            ? "This interview link is not valid. Please check the link in your invitation email."
            : status === 409
              ? loadError?.message ||
                "This invitation is no longer available."
              : loadError?.message || "We couldn't load your interview."}
        </Alert>
        {status !== 404 && status !== 409 ? (
          <div className="mt-5">
            <Button variant="outline" onClick={() => void load()} loading={loading}>
              Try again
            </Button>
          </div>
        ) : null}
      </div>
    );
  }

  const canStart = !session.consent_required || consent;

  if (stage === "done") {
    return (
      <div className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6 py-16 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-success-soft text-success-ink">
          <CheckCircle2 className="h-7 w-7" aria-hidden />
        </span>
        <h1 className="mt-5 text-2xl font-bold tracking-tight text-ink">
          Interview complete
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">
          Thanks{session.company ? ` — your responses for the ${session.role} role` : ""} have
          been submitted{proctored ? " and the session was recorded" : ""}. The hiring team
          will review and be in touch. You can close this window.
        </p>
      </div>
    );
  }

  if (stage === "device") {
    return (
      <div className="mx-auto min-h-screen max-w-4xl px-5 py-8 lg:py-12">
        <header className="mb-6">
          <h1 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">
            {session.role}
            {session.company ? ` · ${session.company}` : ""}
          </h1>
          <p className="mt-1 text-sm text-ink-2">
            One quick setup step before your interview begins.
          </p>
        </header>
        <DeviceCheck
          candidateName="Candidate"
          onNext={() => void doStart(true)}
          nexting={starting}
          requireScreen={session.proctoring_mode === "strict"}
        />
        {startError ? (
          <div className="mt-4">
            <Alert tone="error">{startError}</Alert>
          </div>
        ) : null}
        <div className="mt-6 flex justify-center">
          <Button
            variant="ghost"
            size="sm"
            disabled={starting}
            onClick={() => setStage("precheck")}
          >
            ← Back to details
          </Button>
        </div>
      </div>
    );
  }

  if (stage === "precheck") {
    return (
      <div className="mx-auto min-h-screen max-w-4xl px-5 py-8 lg:py-12">
        <Card>
          <CardContent className="p-0">
            <div className="grid lg:grid-cols-[1fr_320px]">
              <div className="px-6 py-8 sm:px-10 sm:py-10">
                <div className="flex items-start gap-4">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-brand-100 text-brand">
                    <Target className="h-6 w-6" aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <h1 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">
                      {session.role}
                    </h1>
                    <p className="mt-1 text-sm text-ink-2">
                      {session.company || "Interview"} · AI screening interview
                    </p>
                  </div>
                </div>

                <div className="mt-5 flex flex-wrap gap-2">
                  <Badge tone="brand">{TYPE_LABELS[session.interview_type]}</Badge>
                  <Badge tone="neutral">
                    {DIFFICULTY_LABELS[session.difficulty]}
                  </Badge>
                  <Badge tone="neutral">
                    {session.total_questions} questions
                  </Badge>
                </div>

                {proctored ? (
                  <div className="mt-6 rounded-xl border border-line bg-surface p-4">
                    <div className="flex gap-3">
                      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand">
                        <Camera className="h-4 w-4" aria-hidden />
                      </span>
                      <div className="min-w-0">
                        <p className="text-[13px] font-semibold text-ink">
                          Recorded &amp; proctored
                        </p>
                        <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">
                          This interview is monitored for integrity (
                          {PROCTORING_LABELS[session.proctoring_mode]}). Your camera
                          and microphone may be used during the session. An AI
                          screens your answers — a human reviews and decides.
                        </p>
                        <label className="mt-3 flex cursor-pointer items-start gap-2.5">
                          <input
                            type="checkbox"
                            checked={consent}
                            onChange={(event) => setConsent(event.target.checked)}
                            className="mt-0.5 h-4 w-4 shrink-0 rounded border-line accent-brand"
                          />
                          <span className="text-[13px] leading-relaxed text-ink">
                            I understand and consent to proctoring
                          </span>
                        </label>
                      </div>
                    </div>
                  </div>
                ) : null}

                {startError ? (
                  <div className="mt-5">
                    <Alert tone="error">{startError}</Alert>
                  </div>
                ) : null}

                <div className="mt-7 max-w-md">
                  <Button
                    size="lg"
                    className="w-full"
                    disabled={!canStart || starting}
                    loading={starting}
                    onClick={onBegin}
                  >
                    {session.started ? "Resume interview" : "Start interview"}
                  </Button>
                  {!canStart ? (
                    <p className="mt-3 text-xs text-warning">
                      Please consent to proctoring to continue.
                    </p>
                  ) : null}
                </div>
              </div>

              <aside className="border-t border-line bg-surface px-6 py-8 sm:px-8 lg:border-l lg:border-t-0">
                <h4 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
                  <ShieldCheck className="h-4 w-4 text-brand" aria-hidden />
                  What to expect
                </h4>
                <ul className="mt-3 space-y-2.5">
                  {[
                    "One question at a time, at your pace",
                    "Type or speak your answers",
                    "No sign-up — this link is your access",
                  ].map((item) => (
                    <li
                      key={item}
                      className="flex gap-2.5 text-[13px] leading-relaxed text-ink-2"
                    >
                      <CheckCircle2
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success"
                        aria-hidden
                      />
                      {item}
                    </li>
                  ))}
                </ul>
                <p className="mt-6 text-xs text-ink-3">
                  This link expires {formatDate(session.expires_at)}.
                </p>
              </aside>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Session
  return (
    <div className="mx-auto min-h-screen w-full max-w-[1200px] px-4 py-5 lg:px-6 lg:py-8">
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
      <header className="flex flex-wrap items-center gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-danger/10 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-danger">
              <span className="h-1.5 w-1.5 rounded-full bg-danger animate-pulse-dot" />
              Live
            </span>
            <h1 className="text-lg font-bold tracking-tight text-ink lg:text-xl">
              {session.role}
            </h1>
          </div>
          <p className="mt-1 text-sm text-ink-2">
            {session.company || "Interview"} · {TYPE_LABELS[session.interview_type]}
          </p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-3">
          <InterviewProgress
            current={Math.min(questionNumber, total)}
            answered={Math.min(Math.max(questionNumber - 1, 0), total)}
            total={total}
          />
          {remaining !== null ? (
            <div
              className="flex items-center gap-2 rounded-btn border border-line bg-card px-3 py-2 shadow-sm"
              aria-label={`Time remaining ${formatTime(remaining)}`}
            >
              <Clock className="h-4 w-4 text-ink-3" aria-hidden />
              <span className="text-sm font-semibold tabular-nums text-ink">
                {formatTime(remaining)}
              </span>
            </div>
          ) : null}
          <Button
            variant="danger-soft"
            size="sm"
            onClick={() => setLeaveOpen(true)}
            icon={<Square className="h-3.5 w-3.5" />}
          >
            Leave
          </Button>
        </div>
      </header>

      {recorder.error ? (
        <div className="mt-4">
          <Alert tone="info">
            Recording issue: {recorder.error}. You can keep answering — your
            answers are still being saved.
          </Alert>
        </div>
      ) : null}

      <section className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <CandidatePanel
          candidateName="You"
          recording={recorder.state === "recording"}
          elapsedSec={recorder.elapsedSec}
          onDeviceChange={(kind, on) =>
            reportSignal(`${kind}_${on ? "on" : "off"}`, { device: kind })
          }
          onLeave={() => setLeaveOpen(true)}
          className="order-3 lg:order-none"
        />
        <AIInterviewer
          status={aiStatus}
          question={question?.text ?? ""}
          questionNumber={Math.min(questionNumber, total)}
          totalQuestions={total}
          muted={muted}
          className="order-1 lg:order-none"
          onToggleMute={() => setMuted((value) => !value)}
          onSpeechEnd={handleSpeechEnd}
          onReplay={() => {
            setAiStatus("listening");
            window.setTimeout(() => setAiStatus("speaking"), 10);
          }}
        />

        <div className="order-2 flex flex-col overflow-hidden rounded-card border border-line bg-card shadow-card lg:order-none">
          <header className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
              <MessageSquare className="h-4 w-4 text-ink-3" aria-hidden />
              Conversation
            </h2>
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
            disabled={aiStatus === "thinking" || completed}
            busy={aiStatus === "thinking"}
            onTranscribe={(audio) => screening.transcribeAnswer(token, audio)}
          />
        </div>
      </section>

      <Modal
        open={leaveOpen}
        onClose={() => setLeaveOpen(false)}
        title="Leave this interview?"
        description="Your answers so far are saved. You can return with the same link until it expires."
      >
        <div className="flex items-center justify-end gap-3">
          <Button variant="outline" onClick={() => setLeaveOpen(false)}>
            Keep going
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              setLeaveOpen(false);
              setStage("done");
            }}
            icon={<Square className="h-3.5 w-3.5" />}
          >
            Leave interview
          </Button>
        </div>
      </Modal>
    </div>
  );
}
