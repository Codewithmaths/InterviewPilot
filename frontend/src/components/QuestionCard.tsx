import { HelpCircle } from "lucide-react";

import type { Question } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function QuestionCard({
  question,
  index,
  total,
  followupText,
}: {
  question: Question | null;
  index: number | null;
  total: number;
  followupText?: string | null;
}) {
  if (!question) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base text-muted-foreground">Waiting for the first question…</CardTitle>
        </CardHeader>
      </Card>
    );
  }
  return (
    <Card className="border-primary/20">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <HelpCircle className="h-4 w-4 text-primary" />
            {followupText ? (
              <span>Follow-up question</span>
            ) : (
              <span>
                Question {index ?? question.question_number} / {total}
              </span>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="info">{question.topic}</Badge>
            <Badge
              variant={
                question.difficulty === "Hard" ? "danger" : question.difficulty === "Easy" ? "success" : "warning"
              }
            >
              {question.difficulty}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-base leading-relaxed">{followupText || question.question}</p>
      </CardContent>
    </Card>
  );
}
