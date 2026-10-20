import { Badge } from "@/components/ui/badge";
import type { InterviewStatus } from "@/types";
import { cx } from "@/lib/utils";

export function StatusBadge({ status }: { status: InterviewStatus }) {
  if (status === "in_progress") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-semibold text-brand-hover">
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand" />
        In progress
      </span>
    );
  }
  if (status === "completed") {
    return <Badge tone="success">Completed</Badge>;
  }
  return <Badge tone="muted">Not started</Badge>;
}

export function DifficultyBadge({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  const tone =
    label === "Advanced"
      ? "bg-danger-soft text-danger-ink"
      : label === "Intermediate"
        ? "bg-warning-soft text-warning-ink"
        : "bg-success-soft text-success-ink";
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        tone,
        className,
      )}
    >
      {label}
    </span>
  );
}
