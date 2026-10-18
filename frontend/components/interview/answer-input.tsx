"use client";

import {
  useState,
  useCallback,
  useRef,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Mic, MicOff, Send } from "lucide-react";
import { cx } from "@/lib/utils";
import { useSTT } from "@/hooks/use-speech";

interface AnswerInputProps {
  onSubmit: (answer: string) => void | Promise<void>;
  disabled?: boolean;
  busy?: boolean;
  /**
   * Optional server-side transcription (Safari/Firefox path). When the browser
   * Web Speech API is unavailable, the mic button records audio and hands the
   * blob here for STT.
   */
  onTranscribe?: (audio: Blob) => Promise<string>;
}

function pickAudioMime(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const mime of candidates) {
    if (
      typeof MediaRecorder !== "undefined" &&
      MediaRecorder.isTypeSupported(mime)
    ) {
      return mime;
    }
  }
  return "audio/webm";
}

export function AnswerInput({
  onSubmit,
  disabled,
  busy,
  onTranscribe,
}: AnswerInputProps) {
  const [value, setValue] = useState("");
  // Keep track of user's typed text prior to the current speech session
  const [baseText, setBaseText] = useState("");
  const [serverRecording, setServerRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const handleSpeechResult = useCallback(
    (text: string, isFinal: boolean) => {
      // Append the recognized text to whatever was there before we started speaking
      const newText = baseText ? `${baseText} ${text}`.trim() : text;
      setValue(newText);
      if (isFinal) {
        setBaseText(newText);
      }
    },
    [baseText],
  );

  const {
    recording: speechRecording,
    startListening,
    stopListening,
    isSupported,
  } = useSTT(handleSpeechResult);

  const canRecord = isSupported || Boolean(onTranscribe);
  const recording = speechRecording || serverRecording;

  const stopServerRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      recorder.stop();
    });
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    const type = recorder.mimeType || "audio/webm";
    const blob = new Blob(chunksRef.current, { type });
    chunksRef.current = [];
    setServerRecording(false);

    if (!onTranscribe || blob.size === 0) return;
    setTranscribing(true);
    setVoiceError(null);
    try {
      const text = (await onTranscribe(blob)).trim();
      if (text) {
        const base = baseText || value;
        const next = base ? `${base} ${text}`.trim() : text;
        setValue(next);
        setBaseText(next);
      }
    } catch (error) {
      setVoiceError(
        error instanceof Error ? error.message : "Could not transcribe your answer.",
      );
    } finally {
      setTranscribing(false);
    }
  }, [baseText, onTranscribe, value]);

  const startServerRecording = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setVoiceError("Voice input is not supported in this browser.");
      return;
    }
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType: pickAudioMime() });
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorderRef.current = recorder;
      recorder.start();
      setServerRecording(true);
    } catch {
      setVoiceError("Microphone access is needed for voice input.");
    }
  }, []);

  const toggleRecording = () => {
    if (recording) {
      if (serverRecording) {
        void stopServerRecording();
      } else {
        stopListening();
      }
    } else if (isSupported) {
      setBaseText(value); // Snapshot current input before speaking
      startListening();
    } else {
      void startServerRecording();
    }
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (recording) stopListening();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    try {
      await Promise.resolve(onSubmit(trimmed));
      setValue("");
      setBaseText("");
      setVoiceError(null);
    } catch {
      // Keep the text so the user can retry after an error.
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  };

  const locked = disabled || recording || transcribing;

  return (
    <form
      onSubmit={submit}
      className="border-t border-line bg-card px-4 py-3"
      aria-label="Answer input"
    >
      <div className="rounded-xl border border-line bg-surface transition-colors focus-within:border-brand focus-within:ring-4 focus-within:ring-brand-100">
        <label htmlFor="answer" className="sr-only">
          Your answer
        </label>
        <textarea
          id="answer"
          rows={3}
          value={value}
          disabled={locked}
          onChange={(event) => {
            setValue(event.target.value);
            setBaseText(event.target.value);
          }}
          onKeyDown={onKeyDown}
          placeholder={
            recording
              ? "Listening..."
              : transcribing
                ? "Transcribing…"
                : "Type your answer… (Ctrl + Enter to send)"
          }
          className="w-full resize-none bg-transparent px-4 pt-3 text-sm leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none disabled:opacity-60"
        />
        <div className="flex items-center justify-between px-3 pb-3">
          <div className="flex items-center gap-2">
            {canRecord && (
              <button
                type="button"
                onClick={toggleRecording}
                disabled={disabled || transcribing}
                aria-pressed={recording}
                aria-label={recording ? "Stop voice input" : "Start voice input"}
                className={cx(
                  "flex h-9 w-9 items-center justify-center rounded-full transition-colors",
                  recording
                    ? "bg-danger text-white animate-pulse-dot"
                    : "border border-line bg-card text-ink-2 hover:bg-mist",
                  (disabled || transcribing) && "opacity-50 pointer-events-none",
                )}
              >
                {recording ? (
                  <MicOff className="h-4 w-4" aria-hidden />
                ) : (
                  <Mic className="h-4 w-4" aria-hidden />
                )}
              </button>
            )}
            {recording ? (
              <span className="flex items-center gap-1.5 text-xs font-medium text-danger">
                <span className="h-1.5 w-1.5 rounded-full bg-danger animate-pulse-dot" />
                {serverRecording ? "Recording answer" : "Listening"}
              </span>
            ) : transcribing ? (
              <span className="flex items-center gap-1.5 text-xs font-medium text-brand">
                <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse-dot" />
                Transcribing…
              </span>
            ) : busy ? (
              <span className="flex items-center gap-1.5 text-xs font-medium text-brand">
                <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse-dot" />
                AI is preparing the next question…
              </span>
            ) : (
              <span className="text-xs text-ink-3">
                {value.trim().length} characters
              </span>
            )}
          </div>

          <button
            type="submit"
            disabled={locked || !value.trim()}
            className="inline-flex items-center gap-2 rounded-btn bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-hover disabled:pointer-events-none disabled:opacity-50"
          >
            Send
            <Send className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>
      {voiceError ? (
        <p className="mt-2 text-xs text-danger" role="alert">
          {voiceError}
        </p>
      ) : null}
    </form>
  );
}
