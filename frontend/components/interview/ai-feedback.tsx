import { CircleCheck, Sparkles, TriangleAlert } from "lucide-react";

import type { FeedbackItem } from "@/data/mock";
import { cx } from "@/lib/utils";

interface AIFeedbackProps {
  items: FeedbackItem[];
  pending?: boolean;
}

export function AIFeedback({ items, pending }: AIFeedbackProps) {
  return (
    <section
      className="rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
      aria-label="AI feedback"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <Sparkles className="h-4 w-4 text-brand" aria-hidden />
          AI Feedback
        </h2>
        <span className="text-xs text-ink-3">Live</span>
      </header>

      <div className="space-y-4 px-4 py-4">
        {pending ? (
          <div className="space-y-3">
            {[0, 1, 2].map((index) => (
              <div key={index} className="skeleton h-14 w-full rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-3">
            Feedback appears as you answer.
          </p>
        ) : (
          <ol className="relative space-y-5 border-l border-dashed border-line pl-5">
            {items.map((item) => {
              const positive = item.tone === "good";
              return (
                <li key={item.id} className="relative animate-rise">
                  <span
                    className={cx(
                      "absolute -left-[27px] top-0.5 flex h-5 w-5 items-center justify-center rounded-full ring-4 ring-card",
                      positive
                        ? "bg-[#e7f6ef] text-success"
                        : "bg-[#fef3e2] text-warning",
                    )}
                  >
                    {positive ? (
                      <CircleCheck className="h-3 w-3" aria-hidden />
                    ) : (
                      <TriangleAlert className="h-3 w-3" aria-hidden />
                    )}
                  </span>
                  <p className="text-[13px] font-semibold text-ink">
                    {item.title}
                  </p>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">
                    {item.detail}
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}
