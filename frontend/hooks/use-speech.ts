"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// @ts-ignore - webkitSpeechRecognition is not standard in TS types
const SpeechRecognition = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;

export function useTTS(muted = false) {
  const [speaking, setSpeaking] = useState(false);
  const synth = typeof window !== "undefined" ? window.speechSynthesis : null;
  const activeUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const utteranceSeqRef = useRef(0);
  const onEndRef = useRef<(() => void) | null>(null);

  const speak = useCallback((text: string, onEnd?: () => void) => {
    const seq = ++utteranceSeqRef.current;
    activeUtteranceRef.current = null;
    onEndRef.current = null;

    if (synth) synth.cancel();
    setSpeaking(false);

    if (!synth || muted || !text) {
      if (onEnd) onEnd();
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    // Optionally set voice/pitch/rate here
    utterance.rate = 1.0;

    let settled = false;
    const isCurrent = () =>
      utteranceSeqRef.current === seq &&
      activeUtteranceRef.current === utterance;

    const finish = (notify: boolean) => {
      if (settled || !isCurrent()) return;
      settled = true;
      activeUtteranceRef.current = null;
      onEndRef.current = null;
      setSpeaking(false);
      if (notify) onEnd?.();
    };

    utterance.onstart = () => {
      if (isCurrent()) setSpeaking(true);
    };
    utterance.onend = () => finish(true);
    utterance.onerror = (event) => {
      const code = event.error;
      if (code !== "canceled" && code !== "interrupted") {
        console.warn(`TTS error: ${code || "unknown"}`);
      }
      finish(true);
    };

    activeUtteranceRef.current = utterance;
    onEndRef.current = onEnd ?? null;

    try {
      synth.speak(utterance);
    } catch (error) {
      console.warn("TTS start failed:", error);
      finish(true);
    }
  }, [synth, muted]);

  const stop = useCallback((notify = false) => {
    const active = activeUtteranceRef.current;
    const onEnd = onEndRef.current;
    utteranceSeqRef.current += 1;
    activeUtteranceRef.current = null;
    onEndRef.current = null;
    if (synth) synth.cancel();
    setSpeaking(false);
    if (notify && active) onEnd?.();
  }, [synth]);

  useEffect(() => {
    return () => {
      utteranceSeqRef.current += 1;
      activeUtteranceRef.current = null;
      onEndRef.current = null;
      if (synth) synth.cancel();
    };
  }, [synth]);

  return { speak, stop, speaking };
}

export function useSTT(onResult: (text: string, isFinal: boolean) => void, onError?: (err: any) => void) {
  const [recording, setRecording] = useState(false);
  const recognitionRef = useRef<any>(null);

  const onResultRef = useRef(onResult);
  useEffect(() => {
    onResultRef.current = onResult;
  }, [onResult]);

  const onErrorRef = useRef(onError);
  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    if (!SpeechRecognition) return;
    
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    
    recognition.onstart = () => {
      setRecording(true);
    };
    
    recognition.onresult = (event: any) => {
      let finalTranscript = "";
      let interimTranscript = "";
      
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript + " ";
        } else {
          interimTranscript += transcript;
        }
      }
      
      if (finalTranscript || interimTranscript) {
        onResultRef.current(finalTranscript + interimTranscript, !!finalTranscript);
      }
    };
    
    recognition.onerror = (event: any) => {
      console.warn("STT Error:", event.error);
      if (onErrorRef.current) onErrorRef.current(event.error);
      setRecording(false);
    };
    
    recognition.onend = () => {
      setRecording(false);
    };
    
    recognitionRef.current = recognition;
    
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  const startListening = useCallback(() => {
    if (recognitionRef.current && !recording) {
      try {
        recognitionRef.current.start();
      } catch (e) {
        console.warn("Failed to start listening", e);
      }
    }
  }, [recording]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current && recording) {
      recognitionRef.current.stop();
    }
  }, [recording]);

  return { recording, startListening, stopListening, isSupported: !!SpeechRecognition };
}
