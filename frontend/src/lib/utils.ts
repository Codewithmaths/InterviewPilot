import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
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
