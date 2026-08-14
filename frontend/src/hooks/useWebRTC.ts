import { useCallback, useEffect, useRef, useState } from "react";

import type { WsClient } from "@/lib/ws";
import type { Role } from "@/types";

export type PeerStatus = "idle" | "connecting" | "connected" | "failed" | "disconnected";

const RTC_CONFIG: RTCConfiguration = {
  iceServers: [
    // Google STUN (public, unlimited) — works when both peers have public IPs.
    { urls: "stun:stun.l.google.com:19302" },
    // Cloudflare STUN — reliable fallback, free and unlimited.
    { urls: "stun:stun.cloudflare.com:3478" },
    // Free Open Relay TURN (Metered) — relays media through restrictive NATs /
    // firewalls where UDP is blocked (TCP fallback on 443 looks like HTTPS).
    {
      urls: [
        "turn:openrelay.metered.ca:80",
        "turn:openrelay.metered.ca:443",
        "turn:openrelay.metered.ca:443?transport=tcp",
      ],
      username: "openrelayproject",
      credential: "openrelayproject",
    },
  ],
};

interface WebRTCController {
  remoteStream: MediaStream | null;
  status: PeerStatus;
  error: string | null;
  negotiate: () => void;
  hangup: () => void;
}

/**
 * Real WebRTC peer connection with signaling relayed through the backend
 * WebSocket. The interviewer acts as the offerer; the candidate answers.
 * Host candidates work for local development; TURN is included so production
 * calls survive restrictive NATs (see ARCHITECTURE.md).
 */
export function useWebRTC(role: Role, ws: WsClient | null, localStream: MediaStream | null): WebRTCController {
  const peerRef = useRef<RTCPeerConnection | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [status, setStatus] = useState<PeerStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const remoteRef = useRef<MediaStream | null>(null);
  const localStreamRef = useRef<MediaStream | null>(localStream);
  const attachedTracksRef = useRef<Set<MediaStreamTrack>>(new Set());
  const pendingOfferRef = useRef<RTCSessionDescriptionInit | null>(null);
  const pendingIceRef = useRef<RTCIceCandidateInit[]>([]);

  useEffect(() => {
    localStreamRef.current = localStream;
  }, [localStream]);

  const attachLocalTracks = useCallback((peer: RTCPeerConnection) => {
    const stream = localStreamRef.current;
    if (!stream) return;
    for (const track of stream.getTracks()) {
      if (attachedTracksRef.current.has(track)) continue;
      peer.addTrack(track, stream);
      attachedTracksRef.current.add(track);
    }
  }, []);

  const ensurePeer = useCallback(() => {
    if (peerRef.current) return peerRef.current;
    const peer = new RTCPeerConnection(RTC_CONFIG);
    peerRef.current = peer;
    attachLocalTracks(peer);

    remoteRef.current = new MediaStream();
    setRemoteStream(remoteRef.current);

    peer.onicecandidate = (e) => {
      if (e.candidate) {
        ws?.sendSignal("ice", { candidate: e.candidate.toJSON() });
      }
    };
    peer.ontrack = (e) => {
      const stream = remoteRef.current;
      if (stream) {
        stream.addTrack(e.track);
        setRemoteStream(new MediaStream(stream.getTracks()));
      }
    };
    peer.onconnectionstatechange = () => {
      const s = peer.connectionState;
      if (s === "connected") setStatus("connected");
      else if (s === "failed") setStatus("failed");
      else if (s === "disconnected") setStatus("disconnected");
      else if (s === "connecting") setStatus("connecting");
    };
    peer.onicecandidateerror = (e) => {
      if ((e as RTCPeerConnectionIceErrorEvent).errorCode) {
        setError(`ICE error ${(e as RTCPeerConnectionIceErrorEvent).errorCode}`);
      }
    };
    return peer;
  }, [attachLocalTracks, ws]);

  // Attach local tracks whenever the local stream becomes available.
  useEffect(() => {
    const peer = peerRef.current;
    if (!peer || !localStream) return;
    attachLocalTracks(peer);
  }, [attachLocalTracks, localStream]);

  const flushPendingIce = useCallback(async (peer: RTCPeerConnection) => {
    const pending = pendingIceRef.current;
    pendingIceRef.current = [];
    for (const candidate of pending) {
      await peer.addIceCandidate(candidate);
    }
  }, []);

  const acceptOffer = useCallback(async (offer: RTCSessionDescriptionInit) => {
    if (role !== "candidate" || !ws) return;
    const peer = ensurePeer();
    if (!localStreamRef.current) {
      pendingOfferRef.current = offer;
      setStatus("connecting");
      return;
    }
    try {
      attachLocalTracks(peer);
      await peer.setRemoteDescription(offer);
      await flushPendingIce(peer);
      const answer = await peer.createAnswer();
      await peer.setLocalDescription(answer);
      ws.sendSignal("answer", { sdp: peer.localDescription!.sdp });
      setStatus("connecting");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not answer WebRTC offer");
    }
  }, [attachLocalTracks, ensurePeer, flushPendingIce, role, ws]);

  useEffect(() => {
    if (!localStream || !pendingOfferRef.current) return;
    const offer = pendingOfferRef.current;
    pendingOfferRef.current = null;
    void acceptOffer(offer);
  }, [acceptOffer, localStream]);

  // Listen for signaling from the peer.
  useEffect(() => {
    if (!ws) return;
    const unsub = ws.on("SIGNAL", async (message) => {
      const payload = (message.payload || {}) as { kind?: string; from_role?: Role; sdp?: string; candidate?: RTCIceCandidateInit };
      if (!payload.kind || payload.from_role === role) return;
      const peer = ensurePeer();
      try {
        if (payload.kind === "offer" && role === "candidate") {
          await acceptOffer({ type: "offer", sdp: payload.sdp! });
        } else if (payload.kind === "answer" && role === "interviewer") {
          await peer.setRemoteDescription({ type: "answer", sdp: payload.sdp! });
          await flushPendingIce(peer);
        } else if (payload.kind === "ice") {
          if (payload.candidate) {
            if (peer.remoteDescription) {
              await peer.addIceCandidate(payload.candidate);
            } else {
              pendingIceRef.current.push(payload.candidate);
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Signaling failed");
      }
    });
    return unsub;
  }, [acceptOffer, ensurePeer, flushPendingIce, role, ws]);

  const negotiate = useCallback(async () => {
    if (role !== "interviewer" || !ws) return;
    const peer = ensurePeer();
    attachLocalTracks(peer);
    if (peer.signalingState !== "stable" && peer.signalingState !== "have-local-offer") return;
    setStatus("connecting");
    try {
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      ws.sendSignal("offer", { sdp: peer.localDescription!.sdp });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create offer");
    }
  }, [attachLocalTracks, ensurePeer, role, ws]);

  const hangup = useCallback(() => {
    peerRef.current?.close();
    peerRef.current = null;
    attachedTracksRef.current.clear();
    pendingOfferRef.current = null;
    pendingIceRef.current = [];
    remoteRef.current = null;
    setRemoteStream(null);
    setStatus("idle");
  }, []);

  useEffect(() => {
    return () => {
      peerRef.current?.close();
      peerRef.current = null;
    };
  }, []);

  return { remoteStream, status, error, negotiate, hangup };
}
