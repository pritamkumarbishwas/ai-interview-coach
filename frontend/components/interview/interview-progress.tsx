import { ProgressBar } from "@/components/ui/progress-bar";

interface InterviewProgressProps {
  current: number;
  total: number;
}

export function InterviewProgress({ current, total }: InterviewProgressProps) {
  const safeTotal = Math.max(total, 1);
  const percent = Math.round((Math.min(current, safeTotal) / safeTotal) * 100);

  return (
    <div className="w-full max-w-sm">
      <div className="flex items-center justify-between text-[13px]">
        <span className="font-medium text-ink-2">
          Question {Math.min(current, safeTotal)} of {safeTotal}
        </span>
        <span className="font-semibold text-brand tabular-nums">{percent}%</span>
      </div>
      <ProgressBar value={percent} className="mt-2" label="Interview progress" />
    </div>
  );
}
