import { ArrowRight, MessagesSquare } from "lucide-react";

import type { FollowUp } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function FollowUpPanel({
  followups,
  onSelect,
  disabled,
  selected,
}: {
  followups: FollowUp[];
  onSelect: (id: number) => void;
  disabled?: boolean;
  selected?: number | null;
}) {
  if (followups.length === 0) {
    return (
      <Card className="border-amber-500/20">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <MessagesSquare className="h-4 w-4 text-amber-400" />
            Follow-up Questions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground/60">
            Follow-ups appear here when an answer is marked Partially Correct.
          </p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className="border-amber-500/30 bg-amber-500/5">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <MessagesSquare className="h-4 w-4 text-amber-400" />
          Follow-up Questions
          <Badge variant="warning" className="ml-auto">
            {followups.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {followups.map((f, i) => (
          <div key={f.id} className="rounded-md border border-border bg-card/60 p-3">
            <p className="text-sm leading-relaxed">
              <span className="mr-2 text-amber-400">{i + 1}.</span>
              {f.text}
            </p>
            <Button
              size="sm"
              variant="outline"
              className="mt-2"
              disabled={disabled || selected === f.id}
              onClick={() => onSelect(f.id)}
            >
              <ArrowRight className="h-3.5 w-3.5" />
              {selected === f.id ? "Selected" : "Ask Follow-up"}
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
