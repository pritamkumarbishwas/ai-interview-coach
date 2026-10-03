import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cx } from "@/lib/utils";

interface QuestionCardProps {
  question: string;
  questionNumber: number;
  totalQuestions: number;
}

export function QuestionCard({
  question,
  questionNumber,
  totalQuestions,
}: QuestionCardProps) {
  return (
    <div className="rounded-card border border-[#f8dcb8] bg-ai p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[#b3620a]">
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
          Current question
        </span>
        <Badge tone="brand">
          {questionNumber} / {totalQuestions}
        </Badge>
      </div>
      <p
        className={cx(
          "mt-2.5 text-[15px] font-medium leading-relaxed text-ink",
        )}
      >
        {question}
      </p>
    </div>
  );
}
