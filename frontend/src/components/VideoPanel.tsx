import { Camera, CameraOff, Mic, MicOff, UserX } from "lucide-react";

import { cn } from "@/lib/utils";
import type { DeviceState } from "@/hooks/useMedia";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/misc";

function DeviceIndicator({ label, state, icon }: { label: string; state: DeviceState; icon: React.ReactNode }) {
  const config: Record<DeviceState, { text: string; cls: string }> = {
    connected: { text: `${label} Connected`, cls: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" },
    off: { text: `${label} Off`, cls: "text-slate-300 border-border bg-muted" },
    "permission-required": { text: `${label} Permission Required`, cls: "text-amber-400 border-amber-500/30 bg-amber-500/10" },
    unavailable: { text: `${label} Unavailable`, cls: "text-red-400 border-red-500/30 bg-red-500/10" },
  };
  const c = config[state];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        c.cls,
      )}
    >
      {icon}
      {c.text}
    </span>
  );
}

export function VideoPanel({
  stream,
  cameraState,
  micState,
  label,
  isLocal,
  faceCategory,
  showOverlay = true,
}: {
  stream: MediaStream | null;
  cameraState?: DeviceState;
  micState?: DeviceState;
  label: string;
  isLocal?: boolean;
  faceCategory?: string | null;
  showOverlay?: boolean;
}) {
  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-border bg-black">
      {stream ? (
        <video
          ref={(el) => {
            if (el && el.srcObject !== stream) el.srcObject = stream;
          }}
          autoPlay
          playsInline
          muted={isLocal}
          className={cn("h-full w-full object-cover", isLocal && "-scale-x-100")}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <UserX className="h-10 w-10" />
            <p className="text-sm">Waiting for video…</p>
            <Skeleton className="h-24 w-32" />
          </div>
        </div>
      )}

      {showOverlay && (
        <div className="absolute inset-x-0 top-0 flex items-center justify-between p-2">
          <span className="flex items-center gap-1.5 rounded-full bg-black/70 px-2.5 py-0.5 text-xs font-semibold text-red-400">
            <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
            LIVE VIDEO
          </span>
          <Badge variant="muted" className="bg-black/70">
            {label}
          </Badge>
        </div>
      )}

      {(cameraState || micState) && (
        <div className="absolute inset-x-0 bottom-0 flex flex-wrap items-center gap-2 bg-black/60 p-2">
          {cameraState && (
            <DeviceIndicator
              label="Camera"
              state={cameraState}
              icon={cameraState === "connected" ? <Camera className="h-3 w-3" /> : <CameraOff className="h-3 w-3" />}
            />
          )}
          {micState && (
            <DeviceIndicator
              label="Microphone"
              state={micState}
              icon={micState === "connected" ? <Mic className="h-3 w-3" /> : <MicOff className="h-3 w-3" />}
            />
          )}
          {faceCategory && (
            <Badge variant="info" className="bg-black/70">
              Face: {faceCategory}
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}
