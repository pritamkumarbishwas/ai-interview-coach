"use client";

import { useState } from "react";

import {
  ChevronDown,
  CircleCheck,
  Lightbulb,
  MessageSquare,
  TriangleAlert,
  User,
} from "lucide-react";

import { ScoreBar } from "@/components/ui/score-bar";
import { cx } from "@/lib/utils";
import type { AnswerRecord, Evaluation, Question } from "@/types";

interface AnswerReviewProps {
  questions: Question[];
  answers: AnswerRecord[];
  /** A partial report will never fill in the remaining evaluations. */
  evaluationsFinal?: boolean;
}

interface ReviewEntry {
  question: Question;
  answer: AnswerRecord;
}

/**
 * Per-question review shown after the exam: question, the candidate's
 * answer, 5-dimension scores, strengths/weaknesses, coach feedback, and the
 * improved model answer. Entries without an evaluation (still pending) are
 * shown with a gentle "evaluating" note.
 */
export function AnswerReview({
  questions,
  answers,
  evaluationsFinal = false,
}: AnswerReviewProps) {
  const questionMap = new Map(questions.map((q) => [q.id, q]));
  const entries: ReviewEntry[] = [];
  for (const answer of answers) {
    const question = questionMap.get(answer.question_id);
    if (question) entries.push({ question, answer });
  }
  // Keep chronological order by question sequence.
  entries.sort((a, b) => a.question.sequence - b.question.sequence);

  if (entries.length === 0) return null;

  return (
    <section
      className="rounded-card border border-line bg-card shadow-card"
      aria-label="Answer review"
    >
      <header className="border-b border-line px-4 py-3">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <MessageSquare className="h-4 w-4 text-ink-3" aria-hidden />
          Answer Review
        </h2>
        <p className="mt-0.5 text-xs text-ink-3">
          {entries.length} question{entries.length === 1 ? "" : "s"} ·
          evaluated after the session
        </p>
      </header>
      <div className="divide-y divide-line">
        {entries.map(({ question, answer }, index) => (
          <ReviewItem
            key={answer.id}
            question={question}
            answer={answer}
            evaluation={answer.evaluation}
            defaultOpen={index === 0}
            evaluationsFinal={evaluationsFinal}
          />
        ))}
      </div>
    </section>
  );
}

function ReviewItem({
  question,
  answer,
  evaluation,
  defaultOpen,
  evaluationsFinal,
}: {
  question: Question;
  answer: AnswerRecord;
  evaluation: Evaluation | null;
  defaultOpen: boolean;
  evaluationsFinal: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-surface"
        aria-expanded={open}
      >
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold text-brand">
          {question.sequence}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-ink">{question.text}</p>
          {evaluation ? (
            <p className="mt-0.5 text-xs text-ink-3">
              Overall score: {evaluation.overall}/100
              {evaluation.competency ? ` · ${evaluation.competency}` : ""}
            </p>
          ) : (
            <p className="mt-0.5 text-xs text-ink-3">
              {evaluationsFinal ? "Not evaluated" : "Evaluating…"}
            </p>
          )}
        </div>
        {evaluation ? (
          <span
            className={cx(
              "mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
              evaluation.overall >= 70
                ? "bg-success-soft text-success-ink"
                : evaluation.overall >= 50
                  ? "bg-brand-50 text-brand"
                  : "bg-danger-soft text-danger-ink",
            )}
          >
            {evaluation.overall >= 70 ? (
              <CircleCheck className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
            )}
          </span>
        ) : null}
        <ChevronDown
          className={cx(
            "mt-1 h-4 w-4 shrink-0 text-ink-3 transition-transform",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      {open ? (
        <div className="space-y-4 bg-surface/50 px-4 pb-4 pt-1">
          {/* Candidate answer */}
          <div>
            <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">
              <User className="h-3.5 w-3.5" aria-hidden />
              Your answer
            </h4>
            <p className="mt-1.5 whitespace-pre-wrap rounded-lg border border-line bg-card p-3 text-sm leading-relaxed text-ink-2">
              {answer.text}
            </p>
          </div>

          {evaluation ? (
            <>
              {/* Score bars */}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <ScoreBar label="Technical" score={evaluation.scores.technical} max={100} />
                <ScoreBar label="Relevance" score={evaluation.scores.relevance} max={100} />
                <ScoreBar
                  label="Completeness"
                  score={evaluation.scores.completeness}
                  max={100}
                />
                <ScoreBar label="Structure" score={evaluation.scores.structure} max={100} />
                <ScoreBar label="Clarity" score={evaluation.scores.clarity} max={100} />
              </div>

              {/* Strengths / weaknesses */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {evaluation.strengths.length > 0 ? (
                  <div>
                    <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-success">
                      <CircleCheck className="h-3.5 w-3.5" aria-hidden />
                      Strengths
                    </h4>
                    <ul className="mt-1.5 space-y-1">
                      {evaluation.strengths.map((s, i) => (
                        <li
                          key={i}
                          className="flex gap-2 text-[13px] leading-relaxed text-ink-2"
                        >
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-success" />
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {evaluation.weaknesses.length > 0 ? (
                  <div>
                    <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand">
                      <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
                      To improve
                    </h4>
                    <ul className="mt-1.5 space-y-1">
                      {evaluation.weaknesses.map((w, i) => (
                        <li
                          key={i}
                          className="flex gap-2 text-[13px] leading-relaxed text-ink-2"
                        >
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand" />
                          {w}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>

              {/* Coach feedback */}
              {evaluation.feedback ? (
                <div>
                  <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">
                    <MessageSquare className="h-3.5 w-3.5" aria-hidden />
                    Coach feedback
                  </h4>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-2">
                    {evaluation.feedback}
                  </p>
                </div>
              ) : null}

              {evaluation.evidence.length > 0 ? (
                <div>
                  <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">
                    <MessageSquare className="h-3.5 w-3.5" aria-hidden />
                    Evidence from your answer
                  </h4>
                  <ul className="mt-1.5 space-y-1">
                    {evaluation.evidence.map((quote, i) => (
                      <li
                        key={i}
                        className="rounded-lg border border-line bg-card px-3 py-2 text-[13px] italic leading-relaxed text-ink-2"
                      >
                        “{quote}”
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {/* Improved answer */}
              {evaluation.improved_answer ? (
                <div>
                  <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand">
                    <Lightbulb className="h-3.5 w-3.5" aria-hidden />
                    Improved answer
                  </h4>
                  <p className="mt-1.5 whitespace-pre-wrap rounded-lg border border-brand-100 bg-brand-50 p-3 text-sm leading-relaxed text-ink-2">
                    {evaluation.improved_answer}
                  </p>
                </div>
              ) : null}
            </>
          ) : (
            <div className="flex items-center gap-2 rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink-3">
              {evaluationsFinal ? (
                <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />
              ) : (
                <span className="h-2 w-2 animate-pulse-dot rounded-full bg-brand" />
              )}
              {evaluationsFinal
                ? "This answer could not be evaluated."
                : "This answer is still being evaluated. Refresh in a moment."}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
