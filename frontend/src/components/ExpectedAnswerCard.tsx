import { BookOpenCheck, EyeOff } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function ExpectedAnswerCard({ expectedAnswer }: { expectedAnswer: string | null }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <BookOpenCheck className="h-4 w-4 text-emerald-400" />
          Expected Answer
          <Badge variant="muted" className="ml-auto hidden sm:inline-flex">
            <EyeOff className="mr-1 h-3 w-3" /> Interviewer only
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-relaxed text-muted-foreground">{expectedAnswer || "No reference answer."}</p>
      </CardContent>
    </Card>
  );
}
