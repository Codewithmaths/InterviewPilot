import { Eye } from "lucide-react";

import type { FaceAnalysisResult } from "@/types";
import { faceCategoryColor } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

const FACIAL_DISCLAIMER =
  "Facial-expression analysis is an AI-generated visual cue and should not be treated as a definitive assessment of personality, confidence, mental state, or hiring suitability.";

export function FaceStatus({ result, disclaimer = true }: { result: FaceAnalysisResult | null; disclaimer?: boolean }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Face Analysis</span>
        {result ? (
          <Badge className={faceCategoryColor(result.category)}>
            <Eye className="mr-1 h-3 w-3" />
            {result.category}
          </Badge>
        ) : (
          <Badge variant="muted">Waiting for analysis…</Badge>
        )}
      </div>
      {result && (
        <p className="text-xs text-muted-foreground">
          AI confidence: {Math.round(result.confidence * 100)}%
          {result.features && result.features.head_pitch_deg !== undefined
            ? ` · head pitch ${result.features.head_pitch_deg}° · movement ${result.features.movement}`
            : ""}
        </p>
      )}
      {disclaimer && <p className="text-[11px] leading-relaxed text-muted-foreground/80">{FACIAL_DISCLAIMER}</p>}
    </div>
  );
}
