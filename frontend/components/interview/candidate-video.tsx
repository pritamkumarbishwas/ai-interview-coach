"use client";

import {
  Mic,
  MicOff,
  PhoneOff,
  ScreenShare,
  ScreenShareOff,
  Video,
  VideoOff,
} from "lucide-react";

import { StreamVideo } from "@/components/interview/stream-video";
import { Avatar } from "@/components/ui/avatar";
import { useMedia } from "@/hooks/use-media";
import { cx } from "@/lib/utils";

interface CandidateVideoProps {
  candidateName: string;
  onLeave?: () => void;
  className?: string;
}

export function CandidateVideo({
  candidateName,
  onLeave,
  className,
}: CandidateVideoProps) {
  const {
    cameraStream,
    screenStream,
    cameraStatus,
    screenStatus,
    micOn,
    camOn,
    toggleMic,
    toggleCam,
    startScreen,
    stopScreen,
  } = useMedia();

  const sharing = screenStatus === "active" && !!screenStream;
  const cameraLive = cameraStatus === "active" && camOn && !!cameraStream;

  const statusLabel = sharing
    ? "Sharing screen"
    : cameraLive
      ? "Camera on"
      : "Camera off";

  return (
    <section
      className={cx(
        "rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]",
        className,
      )}
      aria-label="Candidate panel"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-[15px] font-semibold text-ink">Candidate</h2>
        <span
          className={cx(
            "rounded-full px-2 py-0.5 text-[11px] font-semibold",
            sharing
              ? "bg-brand-100 text-brand-hover"
              : cameraLive
                ? "bg-[#e7f6ef] text-success"
                : "bg-mist text-ink-3",
          )}
        >
          {statusLabel}
        </span>
      </header>

      <div className="relative m-3 aspect-video overflow-hidden rounded-xl bg-gradient-to-b from-[#2b3644] to-[#1f2933]">
        <div
          className="absolute inset-0 opacity-[0.15]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 30% 20%, #f7931e 0%, transparent 45%), radial-gradient(circle at 75% 80%, #f7931e 0%, transparent 40%)",
          }}
          aria-hidden
        />

        {/* Screen share takes the main stage when active */}
        {sharing ? (
          <StreamVideo
            stream={screenStream}
            className="absolute inset-0 h-full w-full bg-black object-contain"
            label="Shared screen"
          />
        ) : null}

        {/* Camera feed (mirrored self-view) or fallback */}
        {cameraLive ? (
          <StreamVideo
            stream={cameraStream}
            mirror
            label="Camera preview"
            className={
              sharing
                ? "absolute bottom-2 right-2 h-24 w-auto rounded-lg border border-white/20 shadow-lg object-cover"
                : "h-full w-full object-cover"
            }
          />
        ) : (
          <div className="relative flex h-full flex-col items-center justify-center gap-3">
            <Avatar
              name={candidateName}
              size="xl"
              className={cameraStatus !== "active" ? "opacity-40" : undefined}
            />
            <p className="text-sm text-white/60">
              {cameraStatus === "starting"
                ? "Starting camera…"
                : cameraStatus === "denied"
                  ? "Camera access denied"
                  : cameraStatus === "unavailable"
                    ? "No camera found"
                    : "Camera is off"}
            </p>
          </div>
        )}

        {/* Name label */}
        <span className="absolute bottom-2 left-2 rounded-md bg-black/40 px-2 py-0.5 text-xs font-medium text-white backdrop-blur-sm">
          {candidateName}
        </span>

        {!micOn ? (
          <span className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full bg-danger/90 text-white">
            <MicOff className="h-3.5 w-3.5" aria-hidden />
          </span>
        ) : null}

        {sharing ? (
          <span className="absolute left-2 top-2 inline-flex items-center gap-1.5 rounded-full bg-black/50 px-2 py-1 text-[11px] font-semibold text-white backdrop-blur-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-danger animate-pulse-dot" />
            Your screen is visible to the interviewer
          </span>
        ) : null}
      </div>

      <div className="flex items-center justify-center gap-3 px-4 pb-4">
        <ControlButton
          label={micOn ? "Mute microphone" : "Unmute microphone"}
          active={micOn}
          onClick={toggleMic}
          danger={!micOn}
        >
          {micOn ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
        </ControlButton>
        <ControlButton
          label={camOn ? "Turn camera off" : "Turn camera on"}
          active={camOn}
          onClick={toggleCam}
          danger={!camOn}
        >
          {camOn ? (
            <Video className="h-4 w-4" />
          ) : (
            <VideoOff className="h-4 w-4" />
          )}
        </ControlButton>
        <ControlButton
          label={sharing ? "Stop sharing screen" : "Share screen"}
          active={sharing}
          onClick={sharing ? stopScreen : () => void startScreen()}
        >
          {sharing ? (
            <ScreenShareOff className="h-4 w-4" />
          ) : (
            <ScreenShare className="h-4 w-4" />
          )}
        </ControlButton>
        <ControlButton label="Leave interview" danger solid onClick={onLeave}>
          <PhoneOff className="h-4 w-4" />
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
