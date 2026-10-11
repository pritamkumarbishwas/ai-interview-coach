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

  const stopCamera = useCallback(() => {
    cameraRef.current?.getTracks().forEach((track) => track.stop());
    cameraRef.current = null;
    setCameraStream(null);
    setCameraStatus("idle");
  }, []);

  const stopScreen = useCallback(() => {
    screenRef.current?.getTracks().forEach((track) => track.stop());
    screenRef.current = null;
    setScreenStream(null);
    setScreenStatus("idle");
  }, []);

  const startCamera = useCallback(async () => {
    if (cameraRef.current) return;
    setCameraStatus("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      });
      cameraRef.current = stream;
      setCameraStream(stream);
      setCamOn(true);
      setMicOn(true);
      setCameraStatus("active");
    } catch (err) {
      const name = (err as { name?: string })?.name;
      setCameraStatus(
        name === "NotAllowedError" || name === "PermissionDeniedError"
          ? "denied"
          : "unavailable",
      );
    }
  }, []);

  const startScreen = useCallback(async () => {
    if (screenRef.current) return;
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setScreenStatus("unavailable");
      return;
    }
    setScreenStatus("starting");
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
      });
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
      const name = (err as { name?: string })?.name;
      setScreenStatus(
        name === "NotAllowedError" || name === "PermissionDeniedError"
          ? "denied"
          : "idle",
      );
    }
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

  // Stop all tracks when the provider unmounts (leaving the interview).
  useEffect(() => {
    return () => {
      cameraRef.current?.getTracks().forEach((track) => track.stop());
      screenRef.current?.getTracks().forEach((track) => track.stop());
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
