import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Returns true when a recorded audio blob contains no meaningful signal
 * (digital silence or near-silence). Fails open (returns false) when the blob
 * cannot be decoded locally, so real audio is never blocked from upload.
 */
export async function isSilentAudio(blob: Blob): Promise<boolean> {
  try {
    const ctx = new AudioContext();
    try {
      const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
      if (buf.duration === 0) return true;
      const data = buf.getChannelData(0);
      // Subsample to bound the work on long recordings.
      const stride = Math.max(1, Math.floor(data.length / 10000));
      let peak = 0;
      for (let i = 0; i < data.length; i += stride) {
        const v = Math.abs(data[i]);
        if (v > peak) peak = v;
      }
      // ~-46 dBFS: below the noise floor of a working microphone.
      return peak < 0.005;
    } finally {
      void ctx.close();
    }
  } catch {
    return false;
  }
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  // The backend stores UTC timestamps, but SQLite returns them without a
  // timezone marker. Interpret naive values as UTC so browsers convert them
  // correctly, and display in IST as the app's standard.
  const normalized = /(?:[zZ]|[+-]\d{2}:?\d{2})/.test(iso) ? iso : `${iso}Z`;
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return "—";
  return (
    d.toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      dateStyle: "medium",
      timeStyle: "short",
    }) + " IST"
  );
}

export function classificationColor(classification: string): string {
  switch (classification) {
    case "Correct":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "Incorrect":
      return "bg-red-500/15 text-red-400 border-red-500/30";
    case "Partially Correct":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "Not Confirmed":
      return "bg-slate-500/15 text-slate-400 border-slate-500/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

export function faceCategoryColor(category: string): string {
  switch (category) {
    case "Confident":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "Energetic":
      return "bg-sky-500/15 text-sky-400 border-sky-500/30";
    case "Nervous":
      return "bg-orange-500/15 text-orange-400 border-orange-500/30";
    case "Low confident":
      return "bg-rose-500/15 text-rose-400 border-rose-500/30";
    case "Face Not Detected":
      return "bg-slate-500/15 text-slate-400 border-slate-500/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}
