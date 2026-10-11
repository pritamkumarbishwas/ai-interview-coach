"use client";

/**
 * Client-side compositor: screen share as the base layer, camera as a
 * bottom-right PiP overlay, mic audio attached. Produces a single
 * `MediaStream` suitable for one `MediaRecorder` (one synced webm).
 *
 * Falls back gracefully: if `captureStream` is unavailable, callers should
 * record the raw camera stream instead (see `use-interview-recorder`).
 */

export interface CompositorOptions {
  /** Frames per second for the canvas capture stream. */
  fps?: number;
  /** PiP overlay width as a fraction of the canvas width (0–1). */
  pipWidthRatio?: number;
}

const DEFAULT_FPS = 24;
const DEFAULT_PIP_RATIO = 0.25;

export interface CompositeHandle {
  stream: MediaStream;
  /** Call each animation frame to redraw (drives the capture stream). */
  draw: () => void;
  /** Stop the canvas track and detach (does NOT stop source streams). */
  stop: () => void;
}

/** Whether the environment supports canvas capture for compositing. */
export function isCompositorSupported(): boolean {
  return (
    typeof document !== "undefined" &&
    typeof HTMLCanvasElement !== "undefined" &&
    typeof HTMLCanvasElement.prototype.captureStream === "function"
  );
}

/**
 * Build a composite stream from screen + camera (+ optional audio track).
 * Returns null when compositing is unsupported so callers can fall back.
 */
export function createCompositeStream(
  screenStream: MediaStream,
  cameraStream: MediaStream,
  options: CompositorOptions = {},
): CompositeHandle | null {
  if (!isCompositorSupported()) return null;

  const fps = options.fps ?? DEFAULT_FPS;
  const pipRatio = options.pipWidthRatio ?? DEFAULT_PIP_RATIO;

  const screenVideo = document.createElement("video");
  screenVideo.muted = true;
  screenVideo.playsInline = true;
  screenVideo.srcObject = screenStream;
  void screenVideo.play().catch(() => {});

  const cameraVideo = document.createElement("video");
  cameraVideo.muted = true;
  cameraVideo.playsInline = true;
  cameraVideo.srcObject = cameraStream;
  void cameraVideo.play().catch(() => {});

  const canvas = document.createElement("canvas");
  // Match the screen track's resolution when available, else 1280x720.
  const screenTrack = screenStream.getVideoTracks()[0];
  const settings = screenTrack?.getSettings?.() ?? {};
  canvas.width = settings.width ?? 1280;
  canvas.height = settings.height ?? 720;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const capture = canvas.captureStream(fps);
  // Attach mic audio (if present) so the composite carries sound.
  for (const track of cameraStream.getAudioTracks()) {
    capture.addTrack(track);
  }

  const draw = () => {
    const w = canvas.width;
    const h = canvas.height;
    // Base layer: screen (cover-fit).
    if (screenVideo.readyState >= 2) {
      ctx.drawImage(screenVideo, 0, 0, w, h);
    } else {
      ctx.fillStyle = "#111";
      ctx.fillRect(0, 0, w, h);
    }
    // PiP overlay: camera, bottom-right, with a subtle border.
    if (cameraVideo.readyState >= 2) {
      const pipW = Math.round(w * pipRatio);
      const pipH = Math.round((pipW * cameraVideo.videoHeight) / (cameraVideo.videoWidth || 1)) || Math.round(pipW * 0.75);
      const x = w - pipW - 16;
      const y = h - pipH - 16;
      ctx.save();
      ctx.beginPath();
      roundRect(ctx, x, y, pipW, pipH, 10);
      ctx.clip();
      ctx.drawImage(cameraVideo, x, y, pipW, pipH);
      ctx.restore();
      ctx.strokeStyle = "rgba(255,255,255,0.6)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      roundRect(ctx, x, y, pipW, pipH, 10);
      ctx.stroke();
    }
  };

  let raf = 0;
  const loop = () => {
    draw();
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);

  const stop = () => {
    cancelAnimationFrame(raf);
    for (const track of capture.getTracks()) track.stop();
    screenVideo.srcObject = null;
    cameraVideo.srcObject = null;
    void screenVideo.pause();
    void cameraVideo.pause();
  };

  return { stream: capture, draw, stop };
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
