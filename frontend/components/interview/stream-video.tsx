"use client";

import { useEffect, useRef } from "react";

import { cx } from "@/lib/utils";

interface StreamVideoProps {
  stream: MediaStream | null;
  /** Mirror the video horizontally (natural for self-view). */
  mirror?: boolean;
  className?: string;
  label?: string;
}

/** Plays a MediaStream in a <video> element and cleans up on unmount. */
export function StreamVideo({
  stream,
  mirror,
  className,
  label,
}: StreamVideoProps) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.srcObject = stream;
    if (stream) {
      void el.play().catch(() => {});
    }
    return () => {
      el.srcObject = null;
    };
  }, [stream]);

  return (
    <video
      ref={ref}
      muted
      playsInline
      autoPlay
      aria-label={label}
      className={cx(className, mirror && "-scale-x-100")}
    />
  );
}
