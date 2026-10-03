import { cx } from "@/lib/utils";

interface ScoreBarProps {
  label: string;
  score: number;
  max?: number;
}

export function ScoreBar({ label, score, max = 10 }: ScoreBarProps) {
  const safeScore = Math.max(0, Math.min(score, max));
  const percent = Math.round((safeScore / max) * 100);

  return (
    <div>
      <div className="flex items-center justify-between text-[13px]">
        <span className="font-medium text-ink-2">{label}</span>
        <span className="tabular-nums font-semibold text-ink">
          {safeScore.toFixed(1)}
          <span className="font-normal text-ink-3">/{max}</span>
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-mist">
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-700 ease-out"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
