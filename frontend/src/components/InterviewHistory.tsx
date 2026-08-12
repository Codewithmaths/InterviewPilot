import { History } from "lucide-react";

import type { HistoryItem } from "@/types";
import { classificationColor } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/misc";

export function InterviewHistory({ items, loading }: { items: HistoryItem[]; loading?: boolean }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <History className="h-4 w-4 text-primary" />
          Interview History
          <Badge variant="muted" className="ml-auto">
            {items.length} items
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="max-h-[560px] space-y-4 overflow-y-auto scrollbar-thin">
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}
        {!loading && items.length === 0 && (
          <p className="text-sm text-muted-foreground/60">No questions answered yet.</p>
        )}
        {items.map((item, idx) => (
          <div key={idx} className="relative rounded-md border border-border p-3">
            {idx < items.length - 1 && (
              <span className="absolute -bottom-4 left-4 h-4 w-px bg-border" />
            )}
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <Badge variant={item.is_followup ? "warning" : "info"}>
                {item.is_followup ? "Follow-up" : `Q${item.question_number}`}
              </Badge>
              {item.topic && <Badge variant="muted">{item.topic}</Badge>}
              {item.is_followup && item.followup_text ? (
                <span className="text-sm">{item.followup_text}</span>
              ) : (
                <span className="text-sm font-medium">{item.question}</span>
              )}
            </div>
            {item.answers.length === 0 && (
              <p className="text-xs text-muted-foreground/50">No answer recorded.</p>
            )}
            {item.answers.map((a) => (
              <div key={a.id} className="mt-2 space-y-1.5">
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Answer:</span> {a.transcript}
                </p>
                {a.evaluation && (
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge className={classificationColor(a.evaluation.classification)}>
                      {a.evaluation.classification}
                    </Badge>
                    <span className="text-muted-foreground">
                      Score {Math.round(a.evaluation.score * 100)}% · {a.evaluation.reason}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
