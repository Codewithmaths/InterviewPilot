import { Wifi, WifiOff, Users } from "lucide-react";

import type { WsStatus } from "@/store/useInterviewStore";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export function ConnectionStatus({
  wsStatus,
  peerConnected,
  label,
}: {
  wsStatus: WsStatus;
  peerConnected: boolean;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      {wsStatus === "open" ? (
        <Wifi className="h-4 w-4 text-emerald-400" />
      ) : (
        <WifiOff className="h-4 w-4 text-amber-400" />
      )}
      <Badge variant={peerConnected ? "success" : "muted"} className="gap-1.5">
        <Users className="h-3 w-3" />
        {label}
      </Badge>
      <span
        className={cn(
          "text-xs",
          wsStatus === "open" ? "text-emerald-400" : "text-amber-400",
        )}
      >
        {wsStatus === "open" ? "Connected" : "Reconnecting…"}
      </span>
    </div>
  );
}
