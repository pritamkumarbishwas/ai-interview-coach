"use client";

import { useEffect } from "react";

/**
 * Passive integrity signals for a candidate session.
 *
 * These are advisory observations (tab switches, copy/paste, leaving
 * fullscreen) — never blocking, never auto-rejecting. Each one is reported to
 * the API via `onSignal`; the hiring team sees them as context, not verdicts.
 */
export interface IntegritySignalHandlers {
  /** Called for every observed signal. Failures are the caller's concern. */
  onSignal: (type: string, details?: Record<string, unknown>) => void;
}

export interface IntegritySignalOptions extends IntegritySignalHandlers {
  /** Only listen while the interview is actually running. */
  enabled: boolean;
}

export function useIntegritySignals({
  enabled,
  onSignal,
}: IntegritySignalOptions): void {
  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined" || typeof document === "undefined") return;

    let wasFullscreen = document.fullscreenElement !== null;

    const onVisibility = () => {
      onSignal(document.visibilityState === "hidden" ? "tab_blur" : "tab_focus", {
        visibility: document.visibilityState,
      });
    };
    const onBlur = () => onSignal("window_blur");
    const onFocus = () => onSignal("window_focus");
    const onCopy = () =>
      onSignal("copy", { selection: window.getSelection()?.toString().length ?? 0 });
    const onPaste = () => onSignal("paste");
    const onFullscreen = () => {
      const active = document.fullscreenElement !== null;
      if (wasFullscreen && !active) onSignal("fullscreen_exit");
      wasFullscreen = active;
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    document.addEventListener("fullscreenchange", onFullscreen);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("fullscreenchange", onFullscreen);
    };
  }, [enabled, onSignal]);
}
