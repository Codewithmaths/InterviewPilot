import { useEffect, useRef, useState } from "react";

import { analyzeFace } from "@/lib/api";

interface FaceSamplerOptions {
  intervalMs?: number;
  active: boolean;
}

/**
 * Samples frames from the candidate's local video at a configurable interval
 * and sends them to the backend /api/face-analysis endpoint (local frame
 * sampling - never every frame, never raw video). The backend classifies and
 * broadcasts FACE_ANALYSIS_UPDATED to the interviewer.
 */
export function useFaceSampler(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  interviewId: number | null,
  options: FaceSamplerOptions = { intervalMs: 1000, active: true },
): { lastResult: { category: string; confidence: number } | null } {
  const [lastResult, setLastResult] = useState<{ category: string; confidence: number } | null>(null);
  const busyRef = useRef(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!options.active || !interviewId) return;
    const video = videoRef.current;
    if (!video) return;

    if (!canvasRef.current) {
      canvasRef.current = document.createElement("canvas");
    }
    const canvas = canvasRef.current;

    let cancelled = false;

    const sample = async () => {
      if (busyRef.current || cancelled) return;
      busyRef.current = true;
      try {
        if (video.readyState >= 2 && video.videoWidth > 0 && !video.paused) {
          const scale = Math.min(1, 360 / video.videoWidth);
          canvas.width = Math.round(video.videoWidth * scale);
          canvas.height = Math.round(video.videoHeight * scale);
          const ctx = canvas.getContext("2d");
          if (ctx) {
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
            const base64 = dataUrl.split(",")[1];
            const result = await analyzeFace(base64, interviewId);
            if (!cancelled) setLastResult({ category: result.category, confidence: result.confidence });
          }
        }
      } catch {
        /* analysis failures are non-fatal; keep sampling */
      } finally {
        busyRef.current = false;
      }
    };

    const timer = setInterval(sample, options.intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [videoRef, interviewId, options.active, options.intervalMs]);

  return { lastResult };
}
