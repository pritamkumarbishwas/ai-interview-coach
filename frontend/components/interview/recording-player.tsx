"use client";

import { useEffect, useState } from "react";

import { Film, Monitor, User } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { getRecordingBlob } from "@/services/interviews";
import { cx } from "@/lib/utils";

type Kind = "camera" | "screen";

interface RecordingPlayerProps {
  interviewId: string;
  /** Which kinds are present (finalized) on the interview. */
  kinds: Kind[];
}

/**
 * Plays a finalized session recording. Fetches the blob with the axios
 * interceptor (Bearer header) and plays via an object URL, revoked on
 * unmount. Shows a Camera/Screen toggle when both kinds exist.
 */
export function RecordingPlayer({ interviewId, kinds }: RecordingPlayerProps) {
  const [active, setActive] = useState<Kind>(kinds[0] ?? "camera");
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const blob = await getRecordingBlob(interviewId, active);
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
  }, [interviewId, active]);

  if (kinds.length === 0) {
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
        {kinds.length > 1 ? (
          <div className="flex gap-1 rounded-lg bg-surface p-0.5">
            {kinds.map((kind) => (
              <button
                key={kind}
                type="button"
                onClick={() => setActive(kind)}
                className={cx(
                  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold transition-colors",
                  active === kind
                    ? "bg-card text-ink shadow-sm"
                    : "text-ink-3 hover:text-ink",
                )}
              >
                {kind === "camera" ? (
                  <User className="h-3.5 w-3.5" aria-hidden />
                ) : (
                  <Monitor className="h-3.5 w-3.5" aria-hidden />
                )}
                {kind === "camera" ? "Camera" : "Screen"}
              </button>
            ))}
          </div>
        ) : null}
      </header>

      <div className="p-4">
        {error ? (
          <Alert tone="error">
            Recording unavailable: {error}
          </Alert>
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
