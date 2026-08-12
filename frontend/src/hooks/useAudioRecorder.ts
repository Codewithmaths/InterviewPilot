import { useCallback, useEffect, useRef, useState } from "react";

interface RecorderController {
  recording: boolean;
  error: string | null;
  start: () => boolean;
  stop: () => Promise<{ blob: Blob; durationMs: number } | null>;
  isSupported: boolean;
}

/**
 * Records candidate audio via MediaRecorder (real capture). The recorded blob
 * is uploaded to the backend transcription endpoint for Whisper.
 */
export function useAudioRecorder(stream: MediaStream | null): RecorderController {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startedAtRef = useRef<number>(0);
  const supported = typeof MediaRecorder !== "undefined";

  const stop = useCallback((): Promise<{ blob: Blob; durationMs: number } | null> => {
    return new Promise((resolve) => {
      const recorder = recorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        resolve(null);
        return;
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        setRecording(false);
        resolve({ blob, durationMs: Date.now() - startedAtRef.current });
      };
      recorder.stop();
    });
  }, []);

  const start = useCallback((): boolean => {
    setError(null);
    if (!supported) {
      setError("This browser does not support audio recording.");
      return false;
    }
    if (!stream) {
      setError("Microphone stream is not available.");
      return false;
    }
    const audioTracks = stream.getAudioTracks();
    if (!audioTracks.length) {
      setError("No microphone track is available.");
      return false;
    }
    try {
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";
      // MediaRecorder must receive an audio-only stream when using an audio MIME type.
      const audioStream = new MediaStream(audioTracks);
      const recorder = new MediaRecorder(audioStream, mime ? { mimeType: mime } : undefined);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      startedAtRef.current = Date.now();
      recorder.start(250);
      setRecording(true);
      return true;
    } catch (err) {
      setRecording(false);
      setError(err instanceof Error ? err.message : "Could not start audio recording.");
      return false;
    }
  }, [stream, supported]);

  useEffect(() => {
    return () => {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        try {
          recorderRef.current.stop();
        } catch {
          /* ignore */
        }
      }
    };
  }, []);

  return { recording, error, start, stop, isSupported: supported };
}
