"use client";

import { useEffect } from "react";

import {
  Camera,
  CameraOff,
  CheckCircle2,
  CircleAlert,
  MonitorUp,
  RefreshCw,
  ScreenShare,
} from "lucide-react";

import { StreamVideo } from "@/components/interview/stream-video";
import { Button } from "@/components/ui/button";
import { useMedia, type DeviceStatus } from "@/hooks/use-media";
import { cx } from "@/lib/utils";

interface DeviceCheckProps {
  candidateName: string;
  onNext: () => void;
  nexting?: boolean;
  className?: string;
}

type CheckState = "checking" | "pass" | "fail";

function stateOf(status: DeviceStatus): CheckState {
  if (status === "active") return "pass";
  if (status === "idle" || status === "starting") return "checking";
  return "fail";
}

function StatusPill({ state, label }: { state: CheckState; label: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold",
        state === "pass" && "bg-success-soft text-success-ink",
        state === "checking" && "bg-brand-50 text-brand-hover",
        state === "fail" && "bg-danger-soft text-danger-ink",
      )}
    >
      {state === "pass" ? (
        <CheckCircle2 className="h-3 w-3" aria-hidden />
      ) : state === "fail" ? (
        <CircleAlert className="h-3 w-3" aria-hidden />
      ) : (
        <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse-dot" />
      )}
      {label}
    </span>
  );
}

export function DeviceCheck({
  candidateName,
  onNext,
  nexting,
  className,
}: DeviceCheckProps) {
  const {
    cameraStream,
    screenStream,
    cameraStatus,
    screenStatus,
    startCamera,
    startScreen,
  } = useMedia();

  // Kick off both checks as soon as the step mounts. Screen share usually
  // needs a gesture in Chrome, so the explicit button below covers that.
  useEffect(() => {
    void startCamera();
    void startScreen();
  }, [startCamera, startScreen]);

  const camState = stateOf(cameraStatus);
  const screenState = stateOf(screenStatus);
  const allPassed = camState === "pass" && screenState === "pass";

  return (
    <section
      className={cx(
        "rounded-card border border-line bg-card shadow-card",
        className,
      )}
      aria-label="Device check"
    >
      <header className="border-b border-line px-6 py-5">
        <h2 className="text-lg font-bold tracking-tight text-ink">
          Camera &amp; screen check
        </h2>
        <p className="mt-1 text-sm text-ink-2">
          This is a proctored interview — your camera and screen must be
          active before you begin. Everything below must show green.
        </p>
      </header>

      <div className="grid gap-5 px-6 py-6 md:grid-cols-2">
        {/* Camera check */}
        <div>
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
              <Camera className="h-4 w-4 text-brand" aria-hidden />
              Camera
            </h3>
            <StatusPill
              state={camState}
              label={
                camState === "pass"
                  ? "Working"
                  : camState === "fail"
                    ? cameraStatus === "denied"
                      ? "Access denied"
                      : "No camera found"
                    : "Checking…"
              }
            />
          </div>
          <div className="relative mt-3 aspect-video overflow-hidden rounded-xl bg-gradient-to-b from-[#2b3644] to-[#1f2933]">
            {cameraStatus === "active" && cameraStream ? (
              <>
                <StreamVideo
                  stream={cameraStream}
                  mirror
                  className="h-full w-full object-cover"
                  label="Camera preview"
                />
                <span className="absolute bottom-2 left-2 rounded-md bg-black/40 px-2 py-0.5 text-xs font-medium text-white backdrop-blur-sm">
                  {candidateName}
                </span>
              </>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-white/60">
                {cameraStatus === "denied" ? (
                  <CameraOff className="h-8 w-8" aria-hidden />
                ) : (
                  <Camera className="h-8 w-8" aria-hidden />
                )}
                <p className="text-sm">
                  {cameraStatus === "starting"
                    ? "Starting camera…"
                    : cameraStatus === "denied"
                      ? "Camera access was denied"
                      : cameraStatus === "unavailable"
                        ? "No camera detected"
                        : "Camera not started"}
                </p>
              </div>
            )}
          </div>
          {camState !== "pass" ? (
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => void startCamera()}
              icon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              {cameraStatus === "denied"
                ? "Grant camera access"
                : "Retry camera"}
            </Button>
          ) : null}
        </div>

        {/* Screen-share check */}
        <div>
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
              <MonitorUp className="h-4 w-4 text-brand" aria-hidden />
              Screen share
            </h3>
            <StatusPill
              state={screenState}
              label={
                screenState === "pass"
                  ? "Sharing"
                  : screenState === "fail"
                    ? "Unavailable"
                    : "Waiting…"
              }
            />
          </div>
          <div className="relative mt-3 aspect-video overflow-hidden rounded-xl bg-gradient-to-b from-[#2b3644] to-[#1f2933]">
            {screenStatus === "active" && screenStream ? (
              <StreamVideo
                stream={screenStream}
                className="h-full w-full bg-black object-contain"
                label="Screen share preview"
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-white/60">
                <ScreenShare className="h-8 w-8" aria-hidden />
                <p className="text-sm">
                  {screenStatus === "starting"
                    ? "Waiting for screen selection…"
                    : screenStatus === "unavailable"
                      ? "Screen sharing is not supported here"
                      : "Screen not shared yet"}
                </p>
              </div>
            )}
          </div>
          {screenState !== "pass" ? (
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => void startScreen()}
              icon={<ScreenShare className="h-3.5 w-3.5" />}
            >
              Share your screen
            </Button>
          ) : (
            <p className="mt-3 text-xs text-ink-3">
              Pick &quot;Entire screen&quot; or a window — the interview is
              proctored.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t border-line px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
        <p
          className={cx(
            "text-[13px]",
            allPassed ? "text-success" : "text-ink-3",
          )}
        >
          {allPassed
            ? "All checks passed — you're ready to begin."
            : "Both camera and screen share must be active to continue."}
        </p>
        <Button
          variant="primary"
          size="lg"
          disabled={!allPassed || nexting}
          loading={nexting}
          onClick={onNext}
        >
          Next — start interview
        </Button>
      </div>
    </section>
  );
}
