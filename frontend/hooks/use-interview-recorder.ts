"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  createCompositeStream,
  isCompositorSupported,
  type CompositeHandle,
} from "@/lib/compositor";
import { uploadRecordingChunk } from "@/services/interviews";

/**
 * Silent session recorder: composites screen + camera into one canvas stream,
 * records with a 10s timeslice, and uploads each blob as a chunk. No preview
 * is rendered — capture is purely internal.
 *
 * State machine: idle → recording → (uploading) → uploaded | error.
 * The recording length is capped; hitting the cap auto-finalizes.
 */

export type RecorderState =
  | "idle"
  | "recording"
  | "uploading"
  | "uploaded"
  | "error";

const TIMESLICE_MS = 10_000;
const MAX_RECORDING_MS = 25 * 60 * 1000; // hard cap
const PER_QUESTION_MS = 4 * 60 * 1000; // budget per question

interface UseInterviewRecorderOptions {
  /**
   * Authenticated interview id. Required unless `upload` is supplied (guest
   * token sessions upload through `/screening/{token}/...` instead).
   */
  interviewId?: string;
  /**
   * Overrides the default uploader. Guest sessions pass a token-addressed
   * uploader so the recorder never hits the authenticated endpoint. The final
   * argument is the wall-clock ms when capture started, so the reviewer's
   * timeline can anchor offsets to media time 0.
   */
  upload?: (
    blob: Blob,
    seq: number,
    finalize: boolean,
    captureStartedAtMs: number,
  ) => Promise<void>;
  targetQuestions: number;
  /** Whether the interview is actively in progress (drives auto-start). */
  active: boolean;
  cameraStream: MediaStream | null;
  screenStream: MediaStream | null;
}

interface UseInterviewRecorderResult {
  state: RecorderState;
  /** Seconds recorded so far (0 when idle). */
  elapsedSec: number;
  /** Kick the recorder if idle (used on resume). No-op while recording. */
  start: () => void;
  /** Stop recording and upload+finalize. Resolves when upload completes. */
  stopAndUpload: () => Promise<void>;
  /** Error message when state === "error". */
  error: string | null;
}

export function useInterviewRecorder({
  interviewId,
  upload,
  targetQuestions,
  active,
  cameraStream,
  screenStream,
}: UseInterviewRecorderOptions): UseInterviewRecorderResult {
  const [state, setState] = useState<RecorderState>("idle");
  const [elapsedSec, setElapsedSec] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const compositeRef = useRef<CompositeHandle | null>(null);
  const seqRef = useRef(0);
  const startedAtRef = useRef<number>(0);
  const stoppingRef = useRef(false);
  const uploadedRef = useRef(false);
  const maxMsRef = useRef(
    Math.min(targetQuestions * PER_QUESTION_MS, MAX_RECORDING_MS),
  );
  const elapsedTimerRef = useRef<number | null>(null);

  const clearElapsed = () => {
    if (elapsedTimerRef.current !== null) {
      window.clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  };

  const pickMime = (): string => {
    const candidates = [
      "video/webm;codecs=vp9,opus",
      "video/webm;codecs=vp8,opus",
      "video/webm",
    ];
    for (const mime of candidates) {
      if (
        typeof MediaRecorder !== "undefined" &&
        MediaRecorder.isTypeSupported(mime)
      ) {
        return mime;
      }
    }
    return "video/webm";
  };

  const uploadChunk = useCallback(
    async (blob: Blob, seq: number, finalize: boolean) => {
      const captureStartedAtMs = startedAtRef.current;
      if (upload) {
        await upload(blob, seq, finalize, captureStartedAtMs);
        return;
      }
      if (!interviewId) {
        throw new Error("Recorder needs either an interviewId or an upload handler.");
      }
      await uploadRecordingChunk(
        interviewId,
        seq,
        blob,
        finalize,
        blob.type || "video/webm",
        captureStartedAtMs,
      );
    },
    [interviewId, upload],
  );

  const handleData = useCallback(
    (event: BlobEvent) => {
      const blob = event.data;
      if (!blob || blob.size === 0) return;
      const seq = seqRef.current++;
      // Best-effort upload: retry once, then log and continue the session.
      void uploadChunk(blob, seq, false).catch(async (first) => {
        try {
          await uploadChunk(blob, seq, false);
        } catch (second) {
          console.warn("Recording chunk upload failed", first, second);
        }
      });
    },
    [uploadChunk],
  );

  const buildSourceStream = useCallback((): MediaStream | null => {
    // Prefer composite (screen + camera PiP + mic); fall back to camera.
    if (
      isCompositorSupported() &&
      screenStream &&
      cameraStream &&
      screenStream.getVideoTracks().length > 0 &&
      cameraStream.getVideoTracks().length > 0
    ) {
      const handle = createCompositeStream(screenStream, cameraStream);
      if (handle) {
        compositeRef.current = handle;
        return handle.stream;
      }
    }
    return cameraStream;
  }, [cameraStream, screenStream]);

  const finalize = useCallback(async () => {
    if (uploadedRef.current) return;
    uploadedRef.current = true;
    setState("uploading");
    try {
      // Empty marker chunk with finalize=true seals the recording even when
      // no media data was produced (e.g. an instant stop).
      const marker = new Blob([], { type: "video/webm" });
      await uploadChunk(marker, seqRef.current, true);
      setState("uploaded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setState("error");
    }
  }, [uploadChunk]);

  const startInternal = useCallback(() => {
    if (recorderRef.current || stoppingRef.current) return;
    const source = buildSourceStream();
    if (!source || source.getTracks().length === 0) {
      setError("No camera stream available to record.");
      setState("error");
      return;
    }
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(source, { mimeType: pickMime() });
    } catch {
      setError("Recording is not supported in this browser.");
      setState("error");
      return;
    }
    recorderRef.current = recorder;
    seqRef.current = 0;
    uploadedRef.current = false;
    stoppingRef.current = false;
    startedAtRef.current = Date.now();
    setElapsedSec(0);

    recorder.ondataavailable = handleData;
    recorder.onerror = () => {
      setError("Recording failed.");
      setState("error");
    };
    recorder.start(TIMESLICE_MS);
    setState("recording");

    elapsedTimerRef.current = window.setInterval(() => {
      const elapsed = Date.now() - startedAtRef.current;
      setElapsedSec(Math.floor(elapsed / 1000));
      if (elapsed >= maxMsRef.current) {
        void stopAndUploadRef.current?.();
      }
    }, 1000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildSourceStream, handleData]);

  // Keep a stable ref to stopAndUpload for the elapsed timer to call.
  const stopAndUploadRef = useRef<(() => Promise<void>) | null>(null);

  const stopAndUpload = useCallback(async () => {
    if (stoppingRef.current) return;
    stoppingRef.current = true;
    clearElapsed();
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      // Swap the handler rather than wrapping it: the final dataavailable
      // must upload exactly once, or the tail of the recording is duplicated.
      await new Promise<void>((resolve) => {
        recorder.ondataavailable = (event) => {
          const blob = event.data;
          if (blob && blob.size > 0) {
            void uploadChunk(blob, seqRef.current++, false)
              .catch(() => {})
              .finally(() => resolve());
          } else {
            resolve();
          }
        };
        recorder.stop();
      });
    }
    recorderRef.current = null;
    compositeRef.current?.stop();
    compositeRef.current = null;
    await finalize();
  }, [finalize, uploadChunk]);

  // Expose stopAndUpload to the elapsed timer.
  useEffect(() => {
    stopAndUploadRef.current = stopAndUpload;
  }, [stopAndUpload]);

  // Auto-start when the interview becomes active and streams are ready.
  useEffect(() => {
    if (active && !recorderRef.current && !stoppingRef.current) {
      if (cameraStream || screenStream) {
        startInternal();
      }
    }
  }, [active, cameraStream, screenStream, startInternal]);

  // Cleanup on unmount: stop recorder + composite (best-effort finalize).
  useEffect(() => {
    return () => {
      clearElapsed();
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          /* ignore */
        }
      }
      compositeRef.current?.stop();
      compositeRef.current = null;
    };
  }, []);

  const start = useCallback(() => {
    if (!recorderRef.current && !stoppingRef.current) {
      startInternal();
    }
  }, [startInternal]);

  return { state, elapsedSec, start, stopAndUpload, error };
}
