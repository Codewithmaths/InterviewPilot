import { ChevronLeft, ChevronRight, Flag, Repeat, SkipForward, Square } from "lucide-react";

import { Button } from "@/components/ui/button";

export function InterviewControls({
  onPrevious,
  onRepeat,
  onSkip,
  onNext,
  onEnd,
  busy,
  canNavigate,
}: {
  onPrevious: () => void;
  onRepeat: () => void;
  onSkip: () => void;
  onNext: () => void;
  onEnd: () => void;
  busy?: boolean;
  canNavigate?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" onClick={onPrevious} disabled={busy || !canNavigate}>
        <ChevronLeft className="h-4 w-4" /> Previous
      </Button>
      <Button variant="outline" size="sm" onClick={onRepeat} disabled={busy || !canNavigate}>
        <Repeat className="h-4 w-4" /> Repeat Question
      </Button>
      <Button variant="outline" size="sm" onClick={onSkip} disabled={busy || !canNavigate}>
        <SkipForward className="h-4 w-4" /> Skip
      </Button>
      <Button variant="secondary" size="sm" onClick={onNext} disabled={busy || !canNavigate}>
        Next <ChevronRight className="h-4 w-4" />
      </Button>
      <Button variant="destructive" size="sm" className="ml-auto" onClick={onEnd} disabled={busy}>
        <Square className="h-3.5 w-3.5 fill-current" /> End Interview
      </Button>
      <span className="hidden text-xs text-muted-foreground lg:inline">
        <Flag className="mr-1 inline h-3 w-3" />
        Controls are disabled while an answer is being evaluated.
      </span>
    </div>
  );
}
