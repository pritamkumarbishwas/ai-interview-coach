import { useEffect } from "react";
import { Bot, RotateCcw, Settings, Volume2, VolumeX } from "lucide-react";

import { AudioWaveform } from "@/components/interview/audio-waveform";
import { QuestionCard } from "@/components/interview/question-card";
import { cx } from "@/lib/utils";
import { useTTS } from "@/hooks/use-speech";

export type AIStatus = "listening" | "speaking" | "thinking";

const STATUS_META: Record<AIStatus, { label: string; dot: string }> = {
  listening: { label: "Listening", dot: "bg-success" },
  speaking: { label: "Speaking", dot: "bg-brand" },
  thinking: { label: "Thinking", dot: "bg-warning" },
};

interface AIInterviewerProps {
  status: AIStatus;
  question: string;
  questionNumber: number;
  totalQuestions: number;
  muted?: boolean;
  onToggleMute?: () => void;
  onReplay?: () => void;
  onSpeechEnd?: () => void;
}

export function AIInterviewer({
  status,
  question,
  questionNumber,
  totalQuestions,
  muted = false,
  onToggleMute,
  onReplay,
  onSpeechEnd,
}: AIInterviewerProps) {
  const meta = STATUS_META[status];
  const { speak, stop, speaking } = useTTS(muted);

  useEffect(() => {
    if (status === "speaking" && question) {
      speak(question, onSpeechEnd);
    } else {
      stop();
    }
  }, [status, question, speak, stop, onSpeechEnd]);

  // Use the actual speaking status from the TTS engine for the waveform animation
  const isSpeaking = status === "speaking" && speaking;

  return (
    <section
      className="flex flex-col rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
      aria-label="AI interviewer"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-[15px] font-semibold text-ink">AI Interviewer</h2>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-hover">
          <span
            className={cx(
              "h-1.5 w-1.5 rounded-full animate-pulse-dot",
              meta.dot,
            )}
          />
          {meta.label}
        </span>
      </header>

      <div className="flex flex-col items-center gap-2 px-4 pt-5">
        <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-brand text-white shadow-md">
          <Bot className="h-8 w-8" aria-hidden />
          <span className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-card shadow ring-1 ring-line">
            <span
              className={cx(
                "h-2 w-2 rounded-full animate-pulse-dot",
                status === "thinking" ? "bg-warning" : "bg-success",
              )}
            />
          </span>
        </div>
        <AudioWaveform active={isSpeaking} className="mt-1" />
        <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">
          AI Coach · {meta.label}
        </p>
      </div>

      <div className="px-4 pt-4">
        <QuestionCard
          question={question}
          questionNumber={questionNumber}
          totalQuestions={totalQuestions}
        />
      </div>

      <div className="flex items-center justify-center gap-2 px-4 py-4">
        <SmallControl label="Replay question" onClick={onReplay}>
          <RotateCcw className="h-4 w-4" />
        </SmallControl>
        <SmallControl label={muted ? "Unmute interviewer" : "Mute interviewer"} onClick={onToggleMute} active={!muted}>
          {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
        </SmallControl>
        <SmallControl label="Interviewer settings">
          <Settings className="h-4 w-4" />
        </SmallControl>
      </div>
    </section>
  );
}

function SmallControl({
  children,
  label,
  onClick,
  active,
}: {
  children: React.ReactNode;
  label: string;
  onClick?: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-btn border px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "border-line bg-mist text-ink"
          : "border-line bg-card text-ink-2 hover:bg-mist",
      )}
    >
      {children}
    </button>
  );
}
