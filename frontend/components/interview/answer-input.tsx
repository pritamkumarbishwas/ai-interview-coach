"use client";

import { useState, useCallback, type FormEvent, type KeyboardEvent } from "react";
import { Mic, MicOff, Send } from "lucide-react";
import { cx } from "@/lib/utils";
import { useSTT } from "@/hooks/use-speech";

interface AnswerInputProps {
  onSubmit: (answer: string) => void | Promise<void>;
  disabled?: boolean;
}

export function AnswerInput({ onSubmit, disabled }: AnswerInputProps) {
  const [value, setValue] = useState("");
  // Keep track of user's typed text prior to the current speech session
  const [baseText, setBaseText] = useState("");

  const handleSpeechResult = useCallback((text: string, isFinal: boolean) => {
    // Append the recognized text to whatever was there before we started speaking
    const newText = baseText ? `${baseText} ${text}`.trim() : text;
    setValue(newText);
    if (isFinal) {
      setBaseText(newText);
    }
  }, [baseText]);

  const { recording, startListening, stopListening, isSupported } = useSTT(handleSpeechResult);

  const toggleRecording = () => {
    if (recording) {
      stopListening();
    } else {
      setBaseText(value); // Snapshot current input before speaking
      startListening();
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
          disabled={disabled || recording}
          onChange={(event) => {
            setValue(event.target.value);
            setBaseText(event.target.value);
          }}
          onKeyDown={onKeyDown}
          placeholder={recording ? "Listening..." : "Type your answer… (Ctrl + Enter to send)"}
          className="w-full resize-none bg-transparent px-4 pt-3 text-sm leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none disabled:opacity-60"
        />
        <div className="flex items-center justify-between px-3 pb-3">
          <div className="flex items-center gap-2">
            {isSupported && (
              <button
                type="button"
                onClick={toggleRecording}
                disabled={disabled}
                aria-pressed={recording}
                aria-label={recording ? "Stop voice input" : "Start voice input"}
                className={cx(
                  "flex h-9 w-9 items-center justify-center rounded-full transition-colors",
                  recording
                    ? "bg-danger text-white animate-pulse-dot"
                    : "border border-line bg-card text-ink-2 hover:bg-mist",
                  disabled && "opacity-50 pointer-events-none"
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
                Listening
              </span>
            ) : (
              <span className="text-xs text-ink-3">
                {value.trim().length} characters
              </span>
            )}
          </div>

          <button
            type="submit"
            disabled={disabled || !value.trim()}
            className="inline-flex items-center gap-2 rounded-btn bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-hover disabled:pointer-events-none disabled:opacity-50"
          >
            Send
            <Send className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>
    </form>
  );
}
