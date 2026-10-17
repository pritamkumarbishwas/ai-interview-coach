"use client";

import { useEffect, useState } from "react";

import { Film } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { getRecordingBlob } from "@/services/interviews";

interface RecordingPlayerProps {
  interviewId: string;
  /** Whether a finalized session recording is present on the interview. */
  available: boolean;
}

/**
 * Plays the finalized session recording (screen + camera composite). Fetches
 * the blob with the axios interceptor (Bearer header) and plays via an object
 * URL, revoked on unmount.
 */
export function RecordingPlayer({
  interviewId,
  available,
}: RecordingPlayerProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!available) return;
    let cancelled = false;
    let objectUrl: string | null = null;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const blob = await getRecordingBlob(interviewId);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Could not load recording.",
        );
        setUrl(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [interviewId, available]);

  if (!available) {
    return (
      <div className="flex items-center gap-2 rounded-card border border-line bg-card px-4 py-3 text-sm text-ink-3">
        <Film className="h-4 w-4" aria-hidden />
        No recording was saved for this session.
      </div>
    );
  }

  return (
    <section
      className="overflow-hidden rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
      aria-label="Session recording"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <Film className="h-4 w-4 text-ink-3" aria-hidden />
          Session Recording
        </h2>
      </header>

      <div className="p-4">
        {error ? (
          <Alert tone="error">Recording unavailable: {error}</Alert>
        ) : loading ? (
          <div className="flex aspect-video items-center justify-center rounded-xl bg-surface text-sm text-ink-3">
            Loading recording…
          </div>
        ) : url ? (
          <video
            key={url}
            src={url}
            controls
            className="aspect-video w-full rounded-xl bg-black"
          />
        ) : (
          <div className="flex aspect-video items-center justify-center rounded-xl bg-surface text-sm text-ink-3">
            Recording not available.
          </div>
        )}
      </div>
    </section>
  );
}
