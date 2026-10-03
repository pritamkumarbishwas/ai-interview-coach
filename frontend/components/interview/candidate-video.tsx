"use client";

import { useState } from "react";

import { Mic, MicOff, Settings, Video, VideoOff, PhoneOff } from "lucide-react";

import { Avatar } from "@/components/ui/avatar";
import { cx } from "@/lib/utils";

export function CandidateVideo({ candidateName }: { candidateName: string }) {
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);

  return (
    <section
      className="rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
      aria-label="Candidate panel"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-[15px] font-semibold text-ink">Candidate</h2>
        <span
          className={cx(
            "rounded-full px-2 py-0.5 text-[11px] font-semibold",
            camOn ? "bg-[#e7f6ef] text-success" : "bg-mist text-ink-3",
          )}
        >
          {camOn ? "Camera on" : "Camera off"}
        </span>
      </header>

      <div className="relative flex aspect-video items-center justify-center overflow-hidden bg-gradient-to-b from-[#2b3644] to-[#1f2933] m-3 rounded-xl">
        <div
          className="absolute inset-0 opacity-[0.15]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, #f7931e 0%, transparent 45%), radial-gradient(circle at 75% 80%, #f7931e 0%, transparent 40%)",
          }}
          aria-hidden
        />
        {camOn ? (
          <div className="relative flex flex-col items-center gap-3">
            <Avatar name={candidateName} size="xl" />
            <p className="text-sm font-medium text-white/80">
              {candidateName}
            </p>
          </div>
        ) : (
          <div className="relative flex flex-col items-center gap-3">
            <Avatar name={candidateName} size="xl" className="opacity-40" />
            <p className="text-sm text-white/60">Camera is off</p>
          </div>
        )}
        {!micOn ? (
          <span className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-danger/90 text-white">
            <MicOff className="h-3.5 w-3.5" aria-hidden />
          </span>
        ) : null}
      </div>

      <div className="flex items-center justify-center gap-3 px-4 pb-4">
        <ControlButton
          label={micOn ? "Mute microphone" : "Unmute microphone"}
          active={micOn}
          onClick={() => setMicOn((value) => !value)}
          danger={!micOn}
        >
          {micOn ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
        </ControlButton>
        <ControlButton
          label={camOn ? "Turn camera off" : "Turn camera on"}
          active={camOn}
          onClick={() => setCamOn((value) => !value)}
          danger={!camOn}
        >
          {camOn ? (
            <Video className="h-4 w-4" />
          ) : (
            <VideoOff className="h-4 w-4" />
          )}
        </ControlButton>
        <ControlButton label="Leave interview" danger solid>
          <PhoneOff className="h-4 w-4" />
        </ControlButton>
        <ControlButton label="Settings">
          <Settings className="h-4 w-4" />
        </ControlButton>
      </div>
    </section>
  );
}

function ControlButton({
  children,
  label,
  active,
  danger,
  solid,
  onClick,
}: {
  children: React.ReactNode;
  label: string;
  active?: boolean;
  danger?: boolean;
  solid?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={cx(
        "flex h-10 w-10 items-center justify-center rounded-full transition-all duration-150",
        solid
          ? "bg-danger text-white hover:brightness-95"
          : danger
            ? "bg-[#fdf0f0] text-danger hover:bg-[#fbe6e6]"
            : "border border-line bg-card text-ink-2 shadow-sm hover:bg-mist hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}
