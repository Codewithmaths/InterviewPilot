import { ShieldCheck } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function PrivacyNotice() {
  return (
    <Alert>
      <ShieldCheck className="h-4 w-4" />
      <AlertTitle>Privacy &amp; Consent</AlertTitle>
      <AlertDescription>
        By continuing you consent to the use of your camera and microphone for this interview.
        Audio is transcribed and answers are analyzed by an AI model. Facial-expression
        analysis is an AI-generated visual cue and is <strong>not</strong> a definitive
        assessment of personality, confidence, mental state, or hiring suitability.
        Raw audio/video is not stored.
      </AlertDescription>
    </Alert>
  );
}
