import { cx } from "@/lib/utils";

interface ScoreMetricProps {
  label: string;
  value: number;
  max?: number;
}

export function ScoreMetric({ label, value, max = 100 }: ScoreMetricProps) {
  const safe = Math.max(0, Math.min(value, max));
  const percent = Math.round((safe / max) * 100);

  return (
    <div>
      <div className="flex items-center justify-between text-[13px]">
        <span className="text-ink-2">{label}</span>
        <span className="font-semibold tabular-nums text-ink">
          {safe}
          <span className="font-normal text-ink-3">/{max}</span>
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-mist">
        <div
          className={cx(
            "h-full rounded-full bg-brand transition-[width] duration-700 ease-out",
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
