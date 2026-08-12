import { CheckCircle2, ListChecks, Loader2, XCircle } from "lucide-react";

import type { EvaluationCompletedPayload } from "@/types";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function EvaluationCard({
  evaluation,
  evaluating,
}: {
  evaluation: EvaluationCompletedPayload | null;
  evaluating?: boolean;
}) {
  if (evaluating && !evaluation) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            Evaluating answer…
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            The LLM is analyzing the candidate&apos;s response against the expected answer.
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!evaluation) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-muted-foreground">Evaluation</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground/60">No evaluation yet.</p>
        </CardContent>
      </Card>
    );
  }

  const success = evaluation.classification === "Correct";
  const fail = evaluation.classification === "Incorrect";
  const partial = evaluation.classification === "Partially Correct";

  return (
    <Card
      className={cn(
        "border-l-4",
        success && "border-l-emerald-500",
        fail && "border-l-red-500",
        partial && "border-l-amber-500",
        !success && !fail && !partial && "border-l-slate-500",
      )}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          {success ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          ) : fail ? (
            <XCircle className="h-4 w-4 text-red-400" />
          ) : (
            <ListChecks className="h-4 w-4 text-amber-400" />
          )}
          Evaluation
          <Badge
            className={cn(
              "ml-auto",
              success && "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
              fail && "border-red-500/30 bg-red-500/10 text-red-400",
              partial && "border-amber-500/30 bg-amber-500/10 text-amber-400",
              !success && !fail && !partial && "border-slate-500/30 bg-slate-500/10 text-slate-400",
            )}
          >
            {evaluation.classification}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">Score</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
            <div
              className={cn(
                "h-full rounded-full",
                success ? "bg-emerald-500" : fail ? "bg-red-500" : partial ? "bg-amber-500" : "bg-slate-400",
              )}
              style={{ width: `${Math.round(evaluation.score * 100)}%` }}
            />
          </div>
          <span className="text-sm font-semibold">{Math.round(evaluation.score * 100)}%</span>
        </div>
        {evaluation.reason && <p className="text-sm leading-relaxed text-muted-foreground">{evaluation.reason}</p>}
        {evaluation.missing_concepts.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {evaluation.missing_concepts.map((c) => (
              <Badge key={c} variant="warning">
                {c}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
