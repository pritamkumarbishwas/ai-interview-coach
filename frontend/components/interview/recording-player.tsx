"use client";

import { useEffect, useState } from "react";

import { Film, Play } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { getRecordingPlaybackUrl } from "@/services/interviews";
import { formatBytes } from "@/lib/utils";

interface RecordingPlayerProps {
  interviewId: string;
  /** Whether a finalized session recording is present on the interview. */
  available: boolean;
  /** Byte size from the recording metadata, shown before playback loads. */
  sizeBytes?: number;
}

/**
 * Plays the finalized session recording (screen + camera composite). Playback
 * is lazy: the browser only receives a short-lived signed URL after the user
 * chooses to load it, which lets the video element issue Range requests.
 */
export function RecordingPlayer({
  interviewId,
  available,
  sizeBytes,
}: RecordingPlayerProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUrl(null);
    setError(null);
    setLoading(false);
  }, [interviewId, available]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const playback = await getRecordingPlaybackUrl(interviewId);
      setUrl(playback.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load recording.");
      setUrl(null);
    } finally {
      setLoading(false);
    }
  };

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
      className="overflow-hidden rounded-card border border-line bg-card shadow-card"
      aria-label="Session recording"
    >
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <Film className="h-4 w-4 text-ink-3" aria-hidden />
          Session Recording
        </h2>
        {sizeBytes ? (
          <span className="text-xs text-ink-3">{formatBytes(sizeBytes)}</span>
        ) : null}
      </header>

      <div className="p-4">
        {error ? (
          <div className="space-y-3">
            <Alert tone="error">Recording unavailable: {error}</Alert>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void load()}
              loading={loading}
            >
              Try again
            </Button>
          </div>
        ) : url ? (
          <video
            key={url}
            src={url}
            controls
            preload="metadata"
            playsInline
            className="aspect-video w-full rounded-xl bg-black"
            onError={() => {
              setError("The playback link expired or the video is unavailable.");
              setUrl(null);
            }}
          >
            Your browser does not support video playback.
          </video>
        ) : (
          <div className="flex aspect-video flex-col items-center justify-center gap-3 rounded-xl bg-surface text-sm text-ink-3">
            <Film className="h-8 w-8" aria-hidden />
            <p>Load the recording when you are ready to review it.</p>
            <Button
              variant="outline"
              onClick={() => void load()}
              loading={loading}
              icon={<Play className="h-4 w-4" aria-hidden />}
            >
              Load recording
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
