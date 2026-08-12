import { useCallback, useEffect, useRef, useState } from "react";

export type DeviceState = "connected" | "off" | "permission-required" | "unavailable";

interface MediaController {
  stream: MediaStream | null;
  cameraState: DeviceState;
  micState: DeviceState;
  requestMedia: () => Promise<boolean>;
  toggleCamera: () => void;
  toggleMic: () => void;
  stop: () => void;
}

function errorToState(err: unknown): DeviceState {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "permission-required";
  return "unavailable";
}

/**
 * Manages camera + microphone access. Real getUserMedia, no simulation.
 * Reuses a single stream so WebRTC and MediaRecorder share the tracks.
 */
export function useMedia(): MediaController {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [cameraState, setCameraState] = useState<DeviceState>("permission-required");
  const [micState, setMicState] = useState<DeviceState>("permission-required");
  const streamRef = useRef<MediaStream | null>(null);
  const statesRef = useRef({ camera: "permission-required" as DeviceState, mic: "permission-required" as DeviceState });

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  const sync = useCallback(() => {
    const s = streamRef.current;
    if (!s) {
      setCameraState(statesRef.current.camera);
      setMicState(statesRef.current.mic);
      return;
    }
    const camTracks = s.getVideoTracks();
    const micTracks = s.getAudioTracks();
    setCameraState(camTracks.length ? (camTracks[0].enabled ? "connected" : "off") : "unavailable");
    setMicState(micTracks.length ? (micTracks[0].enabled ? "connected" : "off") : "unavailable");
  }, []);

  const requestMedia = useCallback(async (): Promise<boolean> => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = s;
      setStream(s);
      statesRef.current = { camera: "connected", mic: "connected" };
      sync();
      return true;
    } catch (err) {
      statesRef.current = { camera: errorToState(err), mic: errorToState(err) };
      sync();
      return false;
    }
  }, [sync]);

  const toggleCamera = useCallback(() => {
    streamRef.current?.getVideoTracks().forEach((t) => (t.enabled = !t.enabled));
    sync();
  }, [sync]);

  const toggleMic = useCallback(() => {
    streamRef.current?.getAudioTracks().forEach((t) => (t.enabled = !t.enabled));
    sync();
  }, [sync]);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setStream(null);
    statesRef.current = { camera: "permission-required", mic: "permission-required" };
    sync();
  }, [sync]);

  return { stream, cameraState, micState, requestMedia, toggleCamera, toggleMic, stop };
}
