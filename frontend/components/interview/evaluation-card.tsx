import {
  ArrowRight,
  CircleCheck,
  Lightbulb,
  MessageSquare,
  TriangleAlert,
} from "lucide-react";

import { ScoreBar } from "@/components/ui/score-bar";
import type { Evaluation } from "@/types";

interface EvaluationCardProps {
  evaluation: Evaluation | null;
  state: "idle" | "pending" | "done";
  isLastQuestion: boolean;
  onNext: () => void;
  onEnd?: () => void;
}

export function EvaluationCard({
  evaluation,
  state,
  isLastQuestion,
  onNext,
  onEnd,
}: EvaluationCardProps) {
  if (state === "idle") {
    return (
      <section
        className="rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
        aria-label="Answer evaluation"
      >
        <header className="border-b border-line px-4 py-3">
          <h2 className="text-[15px] font-semibold text-ink">
            Answer Evaluation
          </h2>
        </header>
        <div className="flex flex-col items-center px-6 py-10 text-center">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand">
            <MessageSquare className="h-5 w-5" aria-hidden />
          </span>
          <p className="mt-3.5 text-sm font-medium text-ink">
            Answer the question to see your evaluation
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
            The AI scores structure, relevance, completeness, and clarity for
            each answer.
          </p>
        </div>
      </section>
    );
  }

  if (state === "pending" || !evaluation) {
    return (
      <section
        className="rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
        aria-label="Answer evaluation"
        aria-busy="true"
      >
        <header className="border-b border-line px-4 py-3">
          <h2 className="text-[15px] font-semibold text-ink">
            Answer Evaluation
          </h2>
        </header>
        <div className="space-y-4 px-4 py-6">
          <div className="flex items-center gap-3 rounded-xl bg-ai px-4 py-3">
            <span className="flex h-2 w-2 rounded-full bg-brand animate-pulse-dot" />
            <p className="text-sm font-medium text-[#b3620a]">
              AI is evaluating your answer…
            </p>
          </div>
          <div className="skeleton h-16 w-full rounded-xl" />
          <div className="space-y-3">
            <div className="skeleton h-4 w-2/3 rounded" />
            <div className="skeleton h-4 w-1/2 rounded" />
            <div className="skeleton h-4 w-3/4 rounded" />
          </div>
        </div>
      </section>
    );
  }

  const scores = evaluation.scores;

  return (
    <section
      className="rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
      aria-label="Answer evaluation"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-[15px] font-semibold text-ink">
          Answer Evaluation
        </h2>
        <span className="rounded-full bg-brand-100 px-2.5 py-0.5 text-[11px] font-semibold text-brand-hover">
          {evaluation.overall.toFixed(0)} / 100
        </span>
      </header>

      <div className="space-y-5 px-4 py-4">
        <div className="space-y-3">
          <ScoreBar label="Technical" score={scores.technical} max={100} />
          <ScoreBar label="Relevance" score={scores.relevance} max={100} />
          <ScoreBar
            label="Completeness"
            score={scores.completeness}
            max={100}
          />
          <ScoreBar label="Structure" score={scores.structure} max={100} />
          <ScoreBar label="Clarity" score={scores.clarity} max={100} />
        </div>

        <div>
          <h3 className="flex items-center gap-1.5 text-[13px] font-semibold text-success">
            <CircleCheck className="h-3.5 w-3.5" aria-hidden />
            Strengths
          </h3>
          {evaluation.strengths.length === 0 ? (
            <p className="mt-1.5 text-[13px] text-ink-3">
              No clear strengths flagged.
            </p>
          ) : (
            <ul className="mt-1.5 space-y-1">
              {evaluation.strengths.map((point) => (
                <li
                  key={point}
                  className="flex gap-2 text-[13px] leading-relaxed text-ink-2"
                >
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-success" />
                  {point}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3 className="flex items-center gap-1.5 text-[13px] font-semibold text-warning">
            <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
            To improve
          </h3>
          {evaluation.weaknesses.length === 0 ? (
            <p className="mt-1.5 text-[13px] text-ink-3">
              Nothing flagged — keep it up.
            </p>
          ) : (
            <ul className="mt-1.5 space-y-1">
              {evaluation.weaknesses.map((point) => (
                <li
                  key={point}
                  className="flex gap-2 text-[13px] leading-relaxed text-ink-2"
                >
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-warning" />
                  {point}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex gap-2.5 rounded-xl border border-[#f8dcb8] bg-ai px-4 py-3">
          <Lightbulb
            className="mt-0.5 h-4 w-4 shrink-0 text-brand"
            aria-hidden
          />
          <div>
            <p className="text-[13px] font-semibold text-[#b3620a]">
              Coach feedback
            </p>
            <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">
              {evaluation.feedback}
            </p>
            {evaluation.improved_answer ? (
              <>
                <p className="mt-3 text-[13px] font-semibold text-[#b3620a]">
                  Stronger answer
                </p>
                <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">
                  {evaluation.improved_answer}
                </p>
              </>
            ) : null}
          </div>
        </div>

        <button
          type="button"
          onClick={isLastQuestion ? onEnd : onNext}
          className="flex w-full items-center justify-center gap-2 rounded-btn bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-hover"
        >
          {isLastQuestion ? "Finish Interview" : "Next Question"}
          <ArrowRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </section>
  );
}
