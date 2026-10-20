"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type DeviceStatus =
  | "idle"
  | "starting"
  | "active"
  | "denied"
  | "unavailable";

interface MediaContextValue {
  cameraStream: MediaStream | null;
  screenStream: MediaStream | null;
  cameraStatus: DeviceStatus;
  screenStatus: DeviceStatus;
  micOn: boolean;
  camOn: boolean;
  startCamera: () => Promise<void>;
  startScreen: () => Promise<void>;
  stopCamera: () => void;
  stopScreen: () => void;
  toggleMic: () => void;
  toggleCam: () => void;
}

const MediaContext = createContext<MediaContextValue | null>(null);

function stopTracks(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

export function useMedia(): MediaContextValue {
  const ctx = useContext(MediaContext);
  if (!ctx) {
    throw new Error("useMedia must be used within a MediaProvider");
  }
  return ctx;
}

export function MediaProvider({ children }: { children: ReactNode }) {
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [screenStream, setScreenStream] = useState<MediaStream | null>(null);
  const [cameraStatus, setCameraStatus] = useState<DeviceStatus>("idle");
  const [screenStatus, setScreenStatus] = useState<DeviceStatus>("idle");
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);

  const cameraRef = useRef<MediaStream | null>(null);
  const screenRef = useRef<MediaStream | null>(null);

  // Media capture is asynchronous and cannot be cancelled. These guards make
  // starting idempotent: Strict Mode effects and rapid clicks share one
  // permission request, and late results from a stopped/unmounted provider are
  // discarded instead of leaving a hidden capture running.
  const mountedRef = useRef(true);
  const cameraRequestRef = useRef(0);
  const screenRequestRef = useRef(0);
  const cameraRequestPromiseRef = useRef<Promise<void> | null>(null);
  const screenRequestPromiseRef = useRef<Promise<void> | null>(null);

  const stopCamera = useCallback(() => {
    cameraRequestRef.current += 1;
    cameraRequestPromiseRef.current = null;
    stopTracks(cameraRef.current);
    cameraRef.current = null;
    setCameraStream(null);
    setCameraStatus("idle");
  }, []);

  const stopScreen = useCallback(() => {
    screenRequestRef.current += 1;
    screenRequestPromiseRef.current = null;
    stopTracks(screenRef.current);
    screenRef.current = null;
    setScreenStream(null);
    setScreenStatus("idle");
  }, []);

  const startCamera = useCallback((): Promise<void> => {
    if (cameraRef.current) return Promise.resolve();
    if (cameraRequestPromiseRef.current) return cameraRequestPromiseRef.current;

    const requestId = ++cameraRequestRef.current;
    setCameraStatus("starting");

    const request = (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          if (mountedRef.current && requestId === cameraRequestRef.current) {
            setCameraStatus("unavailable");
          }
          return;
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true,
        });
        if (!mountedRef.current || requestId !== cameraRequestRef.current) {
          stopTracks(stream);
          return;
        }
        cameraRef.current = stream;
        setCameraStream(stream);
        setCamOn(true);
        setMicOn(true);
        setCameraStatus("active");
      } catch (err) {
        if (!mountedRef.current || requestId !== cameraRequestRef.current) return;
        const name = (err as { name?: string })?.name;
        setCameraStatus(
          name === "NotAllowedError" || name === "PermissionDeniedError"
            ? "denied"
            : "unavailable",
        );
      }
    })();

    cameraRequestPromiseRef.current = request;
    void request.finally(() => {
      if (cameraRequestPromiseRef.current === request) {
        cameraRequestPromiseRef.current = null;
      }
    });
    return request;
  }, []);

  const startScreen = useCallback((): Promise<void> => {
    if (screenRef.current) return Promise.resolve();
    if (screenRequestPromiseRef.current) return screenRequestPromiseRef.current;

    const requestId = ++screenRequestRef.current;
    setScreenStatus("starting");

    const request = (async () => {
      try {
        if (!navigator.mediaDevices?.getDisplayMedia) {
          if (mountedRef.current && requestId === screenRequestRef.current) {
            setScreenStatus("unavailable");
          }
          return;
        }
        const stream = await navigator.mediaDevices.getDisplayMedia({
          video: true,
        });
        if (!mountedRef.current || requestId !== screenRequestRef.current) {
          stopTracks(stream);
          return;
        }
        screenRef.current = stream;
        setScreenStream(stream);
        setScreenStatus("active");
        // The user can stop sharing from the browser's own controls.
        stream.getVideoTracks()[0]?.addEventListener("ended", () => {
          screenRef.current = null;
          setScreenStream(null);
          setScreenStatus("idle");
        });
      } catch (err) {
        if (!mountedRef.current || requestId !== screenRequestRef.current) return;
        const name = (err as { name?: string })?.name;
        setScreenStatus(
          name === "NotAllowedError" || name === "PermissionDeniedError"
            ? "denied"
            : "idle",
        );
      }
    })();

    screenRequestPromiseRef.current = request;
    void request.finally(() => {
      if (screenRequestPromiseRef.current === request) {
        screenRequestPromiseRef.current = null;
      }
    });
    return request;
  }, []);

  const toggleMic = useCallback(() => {
    setMicOn((on) => {
      cameraRef.current?.getAudioTracks().forEach((track) => {
        track.enabled = !on;
      });
      return !on;
    });
  }, []);

  const toggleCam = useCallback(() => {
    setCamOn((on) => {
      cameraRef.current?.getVideoTracks().forEach((track) => {
        track.enabled = !on;
      });
      return !on;
    });
  }, []);

  // Stop all tracks when the provider unmounts (leaving the interview). The
  // in-flight promises stay shared across Strict Mode's simulated remount; if
  // they resolve after a real unmount their tracks are stopped above.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopTracks(cameraRef.current);
      stopTracks(screenRef.current);
      cameraRef.current = null;
      screenRef.current = null;
    };
  }, []);

  const value = {
    cameraStream,
    screenStream,
    cameraStatus,
    screenStatus,
    micOn,
    camOn,
    startCamera,
    startScreen,
    stopCamera,
    stopScreen,
    toggleMic,
    toggleCam,
  };

  return (
    <MediaContext.Provider value={value}>{children}</MediaContext.Provider>
  );
}
