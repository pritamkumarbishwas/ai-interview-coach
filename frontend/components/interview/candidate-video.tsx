"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  Mic,
  MicOff,
  PhoneOff,
  ScreenShare,
  ScreenShareOff,
  Video,
  VideoOff,
} from "lucide-react";

import { Avatar } from "@/components/ui/avatar";
import { cx } from "@/lib/utils";

interface CandidateVideoProps {
  candidateName: string;
  onLeave?: () => void;
  className?: string;
}

type MediaState = "loading" | "active" | "denied" | "unavailable";

function attachStream(
  ref: React.RefObject<HTMLVideoElement | null>,
  stream: MediaStream,
) {
  if (!ref.current) return;
  ref.current.srcObject = stream;
  void ref.current.play().catch(() => {});
}

export function CandidateVideo({
  candidateName,
  onLeave,
  className,
}: CandidateVideoProps) {
  const cameraRef = useRef<HTMLVideoElement>(null);
  const screenRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const autoShareAttempted = useRef(false);

  const [camState, setCamState] = useState<MediaState>("loading");
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [sharing, setSharing] = useState(false);

  const startCamera = useCallback(async () => {
    setCamState("loading");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      });
      streamRef.current = stream;
      attachStream(cameraRef, stream);
      setCamState("active");
    } catch (err) {
      const name = (err as { name?: string })?.name;
      setCamState(
        name === "NotAllowedError" || name === "PermissionDeniedError"
          ? "denied"
          : "unavailable",
      );
    }
  }, []);

  useEffect(() => {
    void startCamera();
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      screenStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [startCamera]);

  // Re-attach the streams whenever the <video> elements (re)mount — e.g. when
  // the camera flips from the fallback placeholder to the live feed.
  useEffect(() => {
    if (cameraRef.current && streamRef.current) {
      attachStream(cameraRef, streamRef.current);
    }
  }, [camState, camOn, sharing]);

  useEffect(() => {
    if (screenRef.current && screenStreamRef.current) {
      attachStream(screenRef, screenStreamRef.current);
    }
  }, [sharing]);

  const startShare = useCallback(async () => {
    if (screenStreamRef.current) return;
    if (!navigator.mediaDevices?.getDisplayMedia) return;
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
      });
      screenStreamRef.current = stream;
      attachStream(screenRef, stream);
      setSharing(true);
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        screenStreamRef.current = null;
        if (screenRef.current) screenRef.current.srcObject = null;
        setSharing(false);
      });
    } catch {
      // User cancelled the picker, or the browser blocked it (no gesture).
    }
  }, []);

  const stopShare = useCallback(() => {
    screenStreamRef.current?.getTracks().forEach((track) => track.stop());
    screenStreamRef.current = null;
    if (screenRef.current) screenRef.current.srcObject = null;
    setSharing(false);
  }, []);

  // Best-effort "share by default": try immediately (some browsers allow it),
  // otherwise retry on the first user gesture — Chrome requires one.
  useEffect(() => {
    if (autoShareAttempted.current) return;
    autoShareAttempted.current = true;
    void startShare();
    const onGesture = () => {
      document.removeEventListener("pointerdown", onGesture);
      document.removeEventListener("keydown", onGesture);
      void startShare();
    };
    document.addEventListener("pointerdown", onGesture);
    document.addEventListener("keydown", onGesture);
    return () => {
      document.removeEventListener("pointerdown", onGesture);
      document.removeEventListener("keydown", onGesture);
    };
  }, [startShare]);

  const toggleMic = () => {
    const stream = streamRef.current;
    if (stream) {
      stream.getAudioTracks().forEach((track) => {
        track.enabled = !micOn;
      });
    }
    setMicOn((value) => !value);
  };

  const toggleCam = () => {
    const stream = streamRef.current;
    if (stream) {
      stream.getVideoTracks().forEach((track) => {
        track.enabled = !camOn;
      });
    }
    setCamOn((value) => !value);
  };

  const cameraLive = camState === "active" && camOn;
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
          <video
            ref={screenRef}
            muted
            playsInline
            autoPlay
            className="absolute inset-0 h-full w-full bg-black object-contain"
            aria-label="Shared screen"
          />
        ) : null}

        {/* Camera feed (mirrored self-view) or fallback */}
        {cameraLive ? (
          <video
            ref={cameraRef}
            muted
            playsInline
            autoPlay
            className={
              sharing
                ? "absolute bottom-2 right-2 h-24 w-auto rounded-lg border border-white/20 shadow-lg -scale-x-100 object-cover"
                : "h-full w-full -scale-x-100 object-cover"
            }
            aria-label="Camera preview"
          />
        ) : (
          <div className="relative flex h-full flex-col items-center justify-center gap-3">
            <Avatar
              name={candidateName}
              size="xl"
              className={camState !== "active" ? "opacity-40" : undefined}
            />
            <p className="text-sm text-white/60">
              {camState === "loading"
                ? "Starting camera…"
                : camState === "denied"
                  ? "Camera access denied"
                  : camState === "unavailable"
                    ? "No camera found"
                    : "Camera is off"}
            </p>
            {camState === "denied" || camState === "unavailable" ? (
              <button
                type="button"
                onClick={() => void startCamera()}
                className="rounded-btn bg-white/10 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-white/20"
              >
                Try again
              </button>
            ) : null}
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
          onClick={sharing ? stopShare : () => void startShare()}
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
