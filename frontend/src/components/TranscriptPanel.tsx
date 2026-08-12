import { FileText, Loader2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function TranscriptPanel({
  transcript,
  live,
  transcribing,
  placeholder,
}: {
  transcript: string;
  live?: boolean;
  transcribing?: boolean;
  placeholder?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <FileText className="h-4 w-4 text-sky-400" />
          {live ? "Live Transcript" : "Candidate Answer"}
          {transcribing && (
            <span className="ml-auto flex items-center gap-1 text-xs text-amber-400">
              <Loader2 className="h-3 w-3 animate-spin" /> Transcribing…
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {transcript ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{transcript}</p>
        ) : (
          <p className="text-sm text-muted-foreground/60">{placeholder || "No answer recorded yet."}</p>
        )}
      </CardContent>
    </Card>
  );
}
