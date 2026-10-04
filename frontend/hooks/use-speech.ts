"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// @ts-ignore - webkitSpeechRecognition is not standard in TS types
const SpeechRecognition = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;

export function useTTS(muted = false) {
  const [speaking, setSpeaking] = useState(false);
  const synth = typeof window !== "undefined" ? window.speechSynthesis : null;

  const speak = useCallback((text: string, onEnd?: () => void) => {
    if (!synth || muted) {
      if (onEnd) onEnd();
      return;
    }
    
    synth.cancel(); // clear previous
    
    if (!text) return;
    
    const utterance = new SpeechSynthesisUtterance(text);
    // Optionally set voice/pitch/rate here
    utterance.rate = 1.0;
    
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => {
      setSpeaking(false);
      if (onEnd) onEnd();
    };
    utterance.onerror = (e) => {
      console.warn("TTS Error:", e);
      setSpeaking(false);
      if (onEnd) onEnd();
    };
    
    synth.speak(utterance);
  }, [synth, muted]);

  const stop = useCallback(() => {
    if (synth) {
      synth.cancel();
      setSpeaking(false);
    }
  }, [synth]);

  useEffect(() => {
    return () => {
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
