import { cx } from "@/lib/utils";

interface AvatarProps {
  name: string;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  className?: string;
  square?: boolean;
}

const SIZES: Record<NonNullable<AvatarProps["size"]>, string> = {
  xs: "h-6 w-6 text-[10px]",
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-14 w-14 text-lg",
  xl: "h-24 w-24 text-2xl",
};

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}

export function Avatar({
  name,
  size = "md",
  className,
  square,
}: AvatarProps) {
  return (
    <span
      className={cx(
        "inline-flex shrink-0 select-none items-center justify-center bg-brand-100 font-semibold text-brand-hover",
        square ? "rounded-xl" : "rounded-full",
        SIZES[size],
        className,
      )}
      aria-hidden
    >
      {initialsOf(name)}
    </span>
  );
}
