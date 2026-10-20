"use client";

import { useEffect } from "react";

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

interface CandidatePanelProps {
  candidateName: string;
  /** Recorder state from useInterviewRecorder. */
  recording: boolean;
  /** Seconds recorded so far. */
  elapsedSec: number;
  /** Fired when the candidate toggles camera/mic/screen (for proctoring logs). */
  onDeviceChange?: (kind: "camera" | "mic" | "screen", on: boolean) => void;
  onLeave?: () => void;
  className?: string;
}

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/**
 * In-session candidate panel: live self-view plus recording status. Capture
 * still happens in the background; this panel surfaces the screen-share base
 * layer with a camera PiP (mirroring the composited recording), a camera-only
 * view, or a placeholder, alongside the recording indicator, device status,
 * and controls.
 */
export function CandidatePanel({
  candidateName,
  recording,
  elapsedSec,
  onDeviceChange,
  onLeave,
  className,
}: CandidatePanelProps) {
  const {
    cameraStream,
    screenStream,
    cameraStatus,
    screenStatus,
    micOn,
    camOn,
    startCamera,
    toggleMic,
    toggleCam,
    startScreen,
    stopScreen,
  } = useMedia();

  // Resumed interviews skip the device-check step — open the camera anyway.
  useEffect(() => {
    if (cameraStatus === "idle") {
      void startCamera();
    }
  }, [cameraStatus, startCamera]);

  const handleToggleMic = () => {
    toggleMic();
    onDeviceChange?.("mic", !micOn);
  };
  const handleToggleCam = () => {
    toggleCam();
    onDeviceChange?.("camera", !camOn);
  };
  const handleToggleScreen = () => {
    if (sharing) {
      stopScreen();
      onDeviceChange?.("screen", false);
    } else {
      void startScreen();
      onDeviceChange?.("screen", true);
    }
  };

  const sharing = screenStatus === "active";
  const cameraLive = cameraStatus === "active";
  const cameraReady = cameraLive && camOn && !!cameraStream;
  const screenReady = sharing && !!screenStream;

  return (
    <section
      className={cx(
        "rounded-card border border-line bg-card shadow-card",
        className,
      )}
      aria-label="Candidate panel"
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-[15px] font-semibold text-ink">Candidate</h2>
        {recording ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-danger/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-danger">
            <span className="h-1.5 w-1.5 rounded-full bg-danger animate-pulse-dot" />
            Recording
          </span>
        ) : (
          <span className="rounded-full bg-mist px-2 py-0.5 text-[11px] font-semibold text-ink-3">
            Not recording
          </span>
        )}
      </header>

      {/* Live self-view: screen share as the base layer with a camera PiP
          (mirrors the composited recording), or camera-only, or a placeholder
          when neither is active. */}
      <div className="relative m-3 flex aspect-video flex-col items-center justify-center gap-3 overflow-hidden rounded-xl bg-gradient-to-b from-[#2b3644] to-[#1f2933]">
        {screenReady ? (
          <StreamVideo
            stream={screenStream}
            className="absolute inset-0 h-full w-full bg-black object-contain"
            label="Screen share preview"
          />
        ) : cameraReady ? (
          <StreamVideo
            stream={cameraStream}
            mirror
            className="absolute inset-0 h-full w-full object-cover"
            label="Camera preview"
          />
        ) : (
          <>
            <div
              className="absolute inset-0 opacity-[0.15]"
              style={{
                backgroundImage:
                  "radial-gradient(circle at 30% 20%, #f7931e 0%, transparent 45%), radial-gradient(circle at 75% 80%, #f7931e 0%, transparent 40%)",
              }}
              aria-hidden
            />
            <Avatar
              name={candidateName}
              size="xl"
              className={cameraLive ? undefined : "opacity-40"}
            />
            <p className="relative text-sm text-white/60">
              {recording
                ? `Recording in progress · ${formatTime(elapsedSec)}`
                : cameraStatus === "starting"
                  ? "Starting camera…"
                  : cameraStatus === "denied"
                    ? "Camera access denied"
                    : cameraStatus === "unavailable"
                      ? "No camera found"
                      : "Camera is off"}
            </p>
          </>
        )}

        {screenReady && cameraReady ? (
          <div className="absolute bottom-2 right-2 h-[26%] w-[26%] overflow-hidden rounded-lg border border-white/60 shadow-md">
            <StreamVideo
              stream={cameraStream}
              mirror
              className="h-full w-full object-cover"
              label="Camera preview"
            />
          </div>
        ) : null}

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
            Screen sharing
          </span>
        ) : null}
      </div>

      {/* Status pills */}
      <div className="flex flex-wrap gap-2 px-4 pb-2">
        <StatusPill label="Camera" on={cameraLive && camOn} />
        <StatusPill label="Mic" on={micOn} />
        <StatusPill label="Screen" on={sharing} />
      </div>

      <div className="flex items-center justify-center gap-3 px-4 pb-4">
        <ControlButton
          label={micOn ? "Mute microphone" : "Unmute microphone"}
          active={micOn}
          onClick={handleToggleMic}
          danger={!micOn}
        >
          {micOn ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
        </ControlButton>
        <ControlButton
          label={camOn ? "Turn camera off" : "Turn camera on"}
          active={camOn}
          onClick={handleToggleCam}
          danger={!camOn}
        >
          {camOn ? (
            <Video className="h-4 w-4" />
          ) : (
            <VideoOff className="h-4 w-4" />
          )}
        </ControlButton>
        <ControlButton
          label={
            screenStatus === "starting"
              ? "Starting screen share"
              : sharing
                ? "Stop sharing screen"
                : "Share screen"
          }
          active={sharing}
          disabled={screenStatus === "starting"}
          onClick={handleToggleScreen}
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

function StatusPill({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold",
        on ? "bg-success-soft text-success-ink" : "bg-mist text-ink-3",
      )}
    >
      <span
        className={cx(
          "h-1.5 w-1.5 rounded-full",
          on ? "bg-success" : "bg-ink-3",
        )}
        aria-hidden
      />
      {label}
    </span>
  );
}

function ControlButton({
  children,
  label,
  active,
  danger,
  solid,
  disabled,
  onClick,
}: {
  children: React.ReactNode;
  label: string;
  active?: boolean;
  danger?: boolean;
  solid?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={cx(
        "flex h-10 w-10 items-center justify-center rounded-full transition-all duration-150",
        disabled && "cursor-not-allowed opacity-50",
        solid
          ? "bg-danger text-white hover:brightness-95"
          : danger
            ? "bg-danger-soft text-danger-ink hover:brightness-95"
            : "border border-line bg-card text-ink-2 shadow-sm hover:bg-mist hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}
