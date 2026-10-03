import { cx } from "@/lib/utils";

interface AudioWaveformProps {
  active?: boolean;
  bars?: number;
  className?: string;
}

export function AudioWaveform({
  active = true,
  bars = 7,
  className,
}: AudioWaveformProps) {
  return (
    <div
      className={cx("flex h-5 items-center gap-[3px]", className)}
      aria-hidden
    >
      {Array.from({ length: bars }).map((_, index) => (
        <span
          key={index}
          className={cx(
            "h-4 w-[3px] origin-center rounded-full bg-brand",
            active ? "animate-wave" : "opacity-30",
          )}
          style={active ? { animationDelay: `${index * 0.12}s` } : undefined}
        />
      ))}
    </div>
  );
}
