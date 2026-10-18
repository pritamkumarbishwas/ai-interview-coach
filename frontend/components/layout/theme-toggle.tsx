"use client";

import { useEffect, useRef, useState } from "react";

import { Monitor, Moon, Sun } from "lucide-react";

import { useTheme, type Theme } from "@/hooks/use-theme";
import { cx } from "@/lib/utils";

const OPTIONS: Array<{ value: Theme; label: string; icon: typeof Sun }> = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

export function ThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Keep the trigger stable on first paint (SSR resolves to light).
  const TriggerIcon = !mounted || resolvedTheme === "light" ? Sun : Moon;

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="rounded-btn p-2 text-ink-2 transition-colors hover:bg-mist hover:text-ink"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Theme"
        title="Theme"
      >
        <TriggerIcon className="h-[18px] w-[18px]" aria-hidden />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-40 overflow-hidden rounded-card border border-line bg-card p-1 shadow-lg animate-rise"
        >
          {OPTIONS.map((option) => {
            const Icon = option.icon;
            const active = theme === option.value;
            return (
              <button
                key={option.value}
                type="button"
                role="menuitemradio"
                aria-checked={active}
                onClick={() => {
                  setTheme(option.value);
                  setOpen(false);
                }}
                className={cx(
                  "flex w-full items-center gap-2.5 rounded-btn px-3 py-2 text-left text-sm transition-colors",
                  active
                    ? "bg-brand-100 font-medium text-brand-ink"
                    : "text-ink-2 hover:bg-mist hover:text-ink",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {option.label}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
