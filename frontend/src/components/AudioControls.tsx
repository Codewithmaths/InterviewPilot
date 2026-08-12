import { Video, VideoOff, Mic, MicOff, CircleAlert } from "lucide-react";

import type { DeviceState } from "@/hooks/useMedia";
import { Button } from "@/components/ui/button";

export function AudioControls({
  cameraState,
  micState,
  onToggleCamera,
  onToggleMic,
}: {
  cameraState: DeviceState;
  micState: DeviceState;
  onToggleCamera: () => void;
  onToggleMic: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={onToggleCamera}
        disabled={cameraState === "unavailable"}
        title={cameraState === "permission-required" ? "Camera permission required" : "Toggle camera"}
      >
        {cameraState === "connected" || cameraState === "off" ? (
          cameraState === "connected" ? (
            <Video className="h-4 w-4" />
          ) : (
            <VideoOff className="h-4 w-4" />
          )
        ) : (
          <CircleAlert className="h-4 w-4" />
        )}
        {cameraState === "connected" ? "Camera On" : cameraState === "off" ? "Camera Off" : "Camera"}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={onToggleMic}
        disabled={micState === "unavailable"}
        title={micState === "permission-required" ? "Microphone permission required" : "Toggle microphone"}
      >
        {micState === "connected" || micState === "off" ? (
          micState === "connected" ? (
            <Mic className="h-4 w-4" />
          ) : (
            <MicOff className="h-4 w-4" />
          )
        ) : (
          <CircleAlert className="h-4 w-4" />
        )}
        {micState === "connected" ? "Mic On" : micState === "off" ? "Mic Off" : "Microphone"}
      </Button>
    </div>
  );
}
