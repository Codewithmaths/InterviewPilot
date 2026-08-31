import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Loader2, Mic, MicOff, Send, Video } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { WsClient } from "@/lib/ws";
import { useMedia } from "@/hooks/useMedia";
import { useWebRTC } from "@/hooks/useWebRTC";
import { useContinuousListening } from "@/hooks/useContinuousListening";
import { useFaceSampler } from "@/hooks/useFaceSampler";
import { useInterviewStore } from "@/store/useInterviewStore";
import type { DeviceState } from "@/hooks/useMedia";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { VideoPanel } from "@/components/VideoPanel";
import { AudioControls } from "@/components/AudioControls";
import { QuestionCard } from "@/components/QuestionCard";
import { PrivacyNotice } from "@/components/PrivacyNotice";
import { Spinner } from "@/components/ui/misc";

export default function CandidatePage() {
  const { id, roomCode } = useParams<{ id: string; roomCode: string }>();
  const {
    interview,
    setInterview,
    setRole,
    questions,
    setQuestions,
    currentQuestion,
    setCurrentQuestion,
    setState,
    state,
    setPipelineStatus,
    setTranscript,
    setWsStatus,
    wsStatus,
    peerConnected,
    setPeerConnected,
    errors,
    pushError,
    clearErrors,
  } = useInterviewStore();

  const [joined, setJoined] = useState(false);
  const [loading, setLoading] = useState(true);
  const [wsClient, setWsClient] = useState<WsClient | null>(null);
  const [currentFollowupId, setCurrentFollowupId] = useState<number | null>(null);
  const [currentFollowupText, setCurrentFollowupText] = useState<string | null>(null);
  const [textInput, setTextInput] = useState("");
  const localVideoRef = useRef<HTMLVideoElement | null>(null);
  const wsRef = useRef<WsClient | null>(null);
  const questionsRef = useRef(questions);

  const media = useMedia();
  const rtc = useWebRTC("candidate", wsClient, media.stream);

  const [remoteCameraState, setRemoteCameraState] = useState<DeviceState>("off");
  const [remoteMicState, setRemoteMicState] = useState<DeviceState>("off");
  const { lastResult } = useFaceSampler(localVideoRef, interview?.id ?? null, {
    intervalMs: 1000,
    active: joined && !!interview && state !== "COMPLETED",
  });
  void lastResult;

  const activeQuestionId = currentFollowupId ? null : (currentQuestion?.id ?? null);
  const activeFollowupId = currentFollowupId;

  const { status: listenStatus, transcript: liveTranscript } =
    useContinuousListening({
      stream: media.stream,
      interviewId: interview?.id ?? 0,
      questionId: activeQuestionId,
      followupId: activeFollowupId,
      wsClient: wsClient,
      enabled: joined && !!interview && state !== "COMPLETED" && !!currentQuestion && !textInput.trim(),
      onTranscript: (text) => setTranscript(text),
      onStatusChange: (s) => {
        if (s === "transcribing") setPipelineStatus("transcribing");
        else if (s === "evaluating") setPipelineStatus("evaluating");
        else setPipelineStatus("idle");
      },
      onError: (message) => pushError(message),
    });

  useEffect(() => {
    questionsRef.current = questions;
  }, [questions]);

  // Load interview by room code and connect WS
  useEffect(() => {
    if (!roomCode) return;
    setRole("candidate");
    let cancelled = false;

    (async () => {
      try {
        const iv = await api.getByRoom(roomCode);
        if (cancelled) return;
        setInterview(iv);
        setState(iv.status as never);
        const qs = await api.getCandidateQuestions(iv.id);
        if (!cancelled) {
          setQuestions(qs);
          if (iv.current_question_index) {
            const q = qs.find((x) => x.question_number === iv.current_question_index);
            if (q) setCurrentQuestion(q);
          }
        }
      } catch (err) {
        if (!cancelled) pushError(err instanceof ApiError ? err.message : "Could not find interview");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    const ws = new WsClient(id!, "candidate");
    wsRef.current = ws;
    setWsClient(ws);
    ws.connect();

    const onOpen = ws.on("CONNECTION_OPEN", () => setWsStatus("open"));
    const onInterviewer = ws.on("INTERVIEWER_CONNECTED", () => setPeerConnected(true));
    const onPeerLeft = ws.on("PEER_DISCONNECTED", (m) => {
      if (m.payload?.role === "interviewer") {
        setPeerConnected(false);
        setRemoteCameraState("off");
        setRemoteMicState("off");
      }
    });
    const onStarted = ws.on("INTERVIEW_STARTED", () => setState("RUNNING" as never));
    const onMediaState = ws.on("MEDIA_STATE", (m) => {
      if (m.payload?.from_role === "interviewer") {
        if (typeof m.payload.camera === "string") setRemoteCameraState(m.payload.camera as DeviceState);
        if (typeof m.payload.mic === "string") setRemoteMicState(m.payload.mic as DeviceState);
      }
    });
    const onQuestion = ws.on("QUESTION_CHANGED", (m) => {
      const num = m.payload?.question_number as number;
      setCurrentQuestion(questionsRef.current.find((q) => q.question_number === num) ?? null);
      setCurrentFollowupId(null);
      setCurrentFollowupText(null);
    });
    const onFollowup = ws.on("FOLLOWUP_SELECTED", (m) => {
      const fupId = m.payload?.followup_id as number;
      const text = m.payload?.text as string;
      setCurrentFollowupId(fupId);
      setCurrentFollowupText(text);
    });
    const onEvalDone = ws.on("EVALUATION_COMPLETED", () => {
      setPipelineStatus("idle");
      setTranscript("");
    });
    const onEnded = ws.on("INTERVIEW_ENDED", () => {
      setState("COMPLETED" as never);
      setPipelineStatus("idle");
      rtc.hangup();
      media.stop();
    });
    const onError = ws.on("ERROR", (m) => pushError(String(m.payload?.message ?? "Server error")));

    return () => {
      cancelled = true;
      onOpen();
      onInterviewer();
      onPeerLeft();
      onStarted();
      onQuestion();
      onFollowup();
      onEvalDone();
      onEnded();
      onError();
      onMediaState();
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, roomCode]);

  // Mirror candidate's own local video
  useEffect(() => {
    const el = localVideoRef.current;
    if (el && media.stream && el.srcObject !== media.stream) el.srcObject = media.stream;
  }, [media.stream]);

  // Broadcast local camera/mic state to the interviewer so their video panel
  // reflects whether we currently have the camera/mic on or off.
  useEffect(() => {
    if (!joined || !wsClient) return;
    wsClient.sendMediaState(media.cameraState, media.micState);
  }, [joined, wsClient, media.cameraState, media.micState]);

  const handleJoin = useCallback(async () => {
    const granted = await media.requestMedia();
    if (granted) {
      setJoined(true);
      clearErrors();
    } else {
      pushError(
        "Camera/microphone permission is required. Please allow access and try again.",
      );
    }
  }, [media, clearErrors, pushError]);

  const handleTextSubmit = useCallback(async () => {
    if (!interview || !textInput.trim()) return;
    setPipelineStatus("evaluating");
    try {
      if (activeFollowupId) {
        await api.submitAnswer(interview.id, {
          followup_id: activeFollowupId,
          transcript: textInput.trim(),
        });
      } else if (activeQuestionId) {
        await api.submitAnswer(interview.id, {
          question_id: activeQuestionId,
          transcript: textInput.trim(),
        });
      }
      setTextInput("");
    } catch (err) {
      pushError(err instanceof ApiError ? err.message : "Failed to submit answer");
    } finally {
      setPipelineStatus("idle");
    }
  }, [interview, activeQuestionId, activeFollowupId, textInput, setPipelineStatus, pushError]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" /> Joining interview…
      </div>
    );
  }

  const isListening = listenStatus === "listening";
  const isTranscribing = listenStatus === "transcribing";
  const isEvaluating = listenStatus === "evaluating";
  const isBusy = isTranscribing || isEvaluating;

  return (
    <div className="min-h-screen pb-10">
      <header className="sticky top-0 z-10 border-b border-border bg-background/90 backdrop-blur">
        <div className="container flex h-14 items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Video className="h-5 w-5 text-primary" />
            <span className="font-semibold">InterviewPilot</span>
            <Badge variant="muted">Candidate</Badge>
          </div>
          <ConnectionStatus
            wsStatus={wsStatus}
            peerConnected={peerConnected}
            label={peerConnected ? "Interviewer connected" : "Waiting for interviewer"}
          />
        </div>
      </header>

      <main className="container mt-6">
        {!joined ? (
          <div className="mx-auto max-w-xl space-y-4">
            <PrivacyNotice />
            {errors.length > 0 && (
              <div className="space-y-2">
                {errors.map((e) => (
                  <Alert key={e.id} variant="destructive">
                    <AlertTitle>Notice</AlertTitle>
                    <AlertDescription>{e.message}</AlertDescription>
                  </Alert>
                ))}
              </div>
            )}
            {interview ? (
              <Card>
                <CardHeader>
                  <CardTitle>Welcome, {interview.candidate_name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    You are joining a <span className="font-medium text-foreground">{interview.interview_type}</span>{" "}
                    interview ({interview.difficulty} · {interview.num_questions} questions).
                  </p>
                  <Button onClick={handleJoin} size="lg" className="w-full">
                    <Mic className="h-4 w-4" /> Grant Camera &amp; Microphone Permission
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="p-6 text-sm text-muted-foreground">
                  This interview could not be loaded. Check that the link is correct, or ask the
                  interviewer to resend it.
                </CardContent>
              </Card>
            )}
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-4">
              <VideoPanel
                stream={rtc.remoteStream}
                label="Interviewer"
                cameraState={remoteCameraState}
                micState={remoteMicState}
                showOverlay={false}
              />
              <Card>
                <CardContent className="p-4">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Your camera</p>
                  <div className="relative aspect-video overflow-hidden rounded-md border border-border bg-black">
                    {media.stream ? (
                      <video ref={localVideoRef} autoPlay playsInline muted className="h-full w-full -scale-x-100 object-cover" />
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                        No camera
                      </div>
                    )}
                  </div>
                  <div className="mt-3">
                    <AudioControls
                      cameraState={media.cameraState}
                      micState={media.micState}
                      onToggleCamera={media.toggleCamera}
                      onToggleMic={media.toggleMic}
                    />
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="space-y-4">
              {state === "COMPLETED" && (
                <Alert>
                  <AlertTitle>The interviewer has ended this session.</AlertTitle>
                  <AlertDescription>Thank you for participating. You can close this window.</AlertDescription>
                </Alert>
              )}

              {errors.length > 0 && (
                <div className="space-y-2">
                  {errors.map((e) => (
                    <Alert key={e.id} variant="destructive">
                      <AlertTitle>Notice</AlertTitle>
                      <AlertDescription>{e.message}</AlertDescription>
                    </Alert>
                  ))}
                </div>
              )}

              <QuestionCard
                question={currentQuestion}
                index={currentQuestion?.question_number ?? interview?.current_question_index ?? null}
                total={interview?.num_questions ?? questions.length}
                followupText={currentFollowupText}
              />

              {!currentQuestion && state === "RUNNING" && (
                <Alert>
                  <AlertDescription>Waiting for the interviewer to move to the next question…</AlertDescription>
                </Alert>
              )}

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Your Answer</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* Listening status indicator */}
                  <div className="flex flex-wrap items-center gap-3">
                    {isListening && (
                      <div className="flex items-center gap-2 text-sm text-emerald-400">
                        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500" />
                        Listening… speak now
                      </div>
                    )}
                    {isTranscribing && (
                      <Badge variant="warning">
                        <Spinner className="mr-1 h-3 w-3" /> Transcribing…
                      </Badge>
                    )}
                    {isEvaluating && (
                      <Badge variant="info">
                        <Spinner className="mr-1 h-3 w-3" /> Evaluating…
                      </Badge>
                    )}
                    {!isBusy && !isListening && state !== "COMPLETED" && currentQuestion && (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Mic className="h-4 w-4" /> Waiting for speech…
                      </div>
                    )}
                    {media.micState === "off" && state !== "COMPLETED" && currentQuestion && (
                      <Badge variant="warning" className="text-amber-300">
                        <MicOff className="mr-1 h-3 w-3" /> Microphone is off — turn it on to answer
                      </Badge>
                    )}
                  </div>

                  {/* Live transcript */}
                  {liveTranscript ? (
                    <p className="whitespace-pre-wrap rounded-md bg-secondary/40 p-3 text-sm">{liveTranscript}</p>
                  ) : (
                    <p className="text-sm text-muted-foreground/60">
                      The system is listening continuously. Just speak your answer — it will be
                      transcribed and evaluated automatically.
                    </p>
                  )}

                  {/* Text input fallback */}
                  <div className="border-t border-border pt-3">
                    <p className="mb-2 text-xs font-medium text-muted-foreground">Or type your answer:</p>
                    <textarea
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      placeholder="Type your answer here…"
                      rows={3}
                      disabled={isBusy || state === "COMPLETED"}
                      className="w-full rounded-md border border-border bg-secondary/30 p-2 text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
                    />
                    <Button
                      onClick={handleTextSubmit}
                      disabled={!textInput.trim() || isBusy || state === "COMPLETED"}
                      className="mt-2"
                      size="sm"
                    >
                      <Send className="h-4 w-4" /> Submit Text Answer
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
