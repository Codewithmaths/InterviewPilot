import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Loader2, Mic, Square, Video } from "lucide-react";

import { api, ApiError, transcribeAudio } from "@/lib/api";
import { WsClient } from "@/lib/ws";
import { useMedia } from "@/hooks/useMedia";
import { useWebRTC } from "@/hooks/useWebRTC";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { useFaceSampler } from "@/hooks/useFaceSampler";
import { useInterviewStore } from "@/store/useInterviewStore";
import { formatDuration, isSilentAudio } from "@/lib/utils";
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
    pipelineStatus,
    setPipelineStatus,
    transcript,
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
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const localVideoRef = useRef<HTMLVideoElement | null>(null);
  const currentQidRef = useRef<number | null>(null);
  const currentFupRef = useRef<number | null>(null);
  const wsRef = useRef<WsClient | null>(null);
  const recordingRef = useRef(false);
  const questionsRef = useRef(questions);

  const media = useMedia();
  const rtc = useWebRTC("candidate", wsClient, media.stream);
  const recorder = useAudioRecorder(media.stream);
  const { lastResult } = useFaceSampler(localVideoRef, interview?.id ?? null, {
    intervalMs: 1000,
    active: joined && !!interview && state !== "COMPLETED",
  });
  void lastResult; // candidate never sees face-analysis output

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
      if (m.payload?.role === "interviewer") setPeerConnected(false);
    });
    const onStarted = ws.on("INTERVIEW_STARTED", () => setState("RUNNING" as never));
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
      currentFupRef.current = fupId;
      currentQidRef.current = null;
      setState("WAITING_FOR_ANSWER" as never);
    });
    const onEvalDone = ws.on("EVALUATION_COMPLETED", () => {
      setPipelineStatus("idle");
      setTranscript("");
    });
    const onEnded = ws.on("INTERVIEW_ENDED", () => {
      setState("COMPLETED" as never);
      setPipelineStatus("idle");
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
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, roomCode]);

  // Mirror candidate's own local video
  useEffect(() => {
    const el = localVideoRef.current;
    if (el && media.stream && el.srcObject !== media.stream) el.srcObject = media.stream;
  }, [media.stream]);

  // Answer timer
  useEffect(() => {
    if (recorder.recording) {
      const start = Date.now();
      timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [recorder.recording]);

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

  const handleStartAnswer = useCallback(() => {
    if (!interview || !currentQuestion) return;
    if (!media.stream?.getAudioTracks().length) {
      pushError("No microphone available. Check your microphone permission.");
      return;
    }
    if (!recorder.start()) {
      pushError(recorder.error ?? "Could not start recording. Check microphone permissions.");
      return;
    }
    wsRef.current?.send("ANSWER_STARTED", {
      question_id: currentFollowupId ? undefined : currentQuestion.id,
      followup_id: currentFollowupId ?? undefined,
    });
    currentQidRef.current = currentFollowupId ? null : currentQuestion.id;
    setTranscript("");
    setElapsed(0);
    recordingRef.current = true;
    setPipelineStatus("recording");
  }, [interview, currentQuestion, currentFollowupId, media.stream, recorder, setPipelineStatus, setTranscript, pushError]);

  const handleStopAnswer = useCallback(async () => {
    if (!interview) return;
    recordingRef.current = false;
    wsRef.current?.send("ANSWER_STOPPED", {});
    const result = await recorder.stop();
    if (!result || result.blob.size === 0) {
      pushError("No audio captured. Please try again.");
      setPipelineStatus("idle");
      return;
    }
    if (result.blob.size < 1000 || (await isSilentAudio(result.blob))) {
      pushError(
        "The recording captured no audio. Check that your microphone is not muted and the correct input device is selected, then try again.",
      );
      setPipelineStatus("idle");
      return;
    }
    setPipelineStatus("transcribing");
    wsRef.current?.send("TRANSCRIPTION_STARTED", {});
    try {
      const { text } = await transcribeAudio(result.blob);
      if (!text.trim()) {
        pushError("No speech detected. Please try again.");
        setPipelineStatus("idle");
        return;
      }
      setTranscript(text);
      setPipelineStatus("evaluating");
      if (currentFollowupId && currentFupRef.current) {
        await api.submitAnswer(interview.id, {
          followup_id: currentFollowupId,
          transcript: text,
          duration_seconds: Math.max(1, Math.round(result.durationMs / 1000)),
        });
      } else if (currentQidRef.current ?? currentQuestion?.id) {
        await api.submitAnswer(interview.id, {
          question_id: currentQidRef.current ?? currentQuestion!.id,
          transcript: text,
          duration_seconds: Math.max(1, Math.round(result.durationMs / 1000)),
        });
      }
    } catch (err) {
      pushError(err instanceof ApiError ? err.message : "Transcription or evaluation failed");
      setPipelineStatus("idle");
    }
  }, [interview, currentQuestion, currentFollowupId, recorder, setPipelineStatus, setTranscript, pushError]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" /> Joining interview…
      </div>
    );
  }

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
            <Card>
              <CardHeader>
                <CardTitle>Welcome, {interview?.candidate_name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  You are joining a <span className="font-medium text-foreground">{interview?.interview_type}</span>{" "}
                  interview ({interview?.difficulty} · {interview?.num_questions} questions).
                </p>
                <Button onClick={handleJoin} size="lg" className="w-full">
                  <Mic className="h-4 w-4" /> Grant Camera &amp; Microphone Permission
                </Button>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-4">
              <VideoPanel
                stream={rtc.remoteStream}
                label="Interviewer"
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
                  <div className="flex flex-wrap items-center gap-3">
                    {!recorder.recording ? (
                      <Button onClick={handleStartAnswer} disabled={!currentQuestion || state === "COMPLETED" || pipelineStatus !== "idle"}>
                        <Mic className="h-4 w-4" /> Start Answer
                      </Button>
                    ) : (
                      <Button variant="destructive" onClick={handleStopAnswer}>
                        <Square className="h-4 w-4 fill-current" /> Stop Answer
                      </Button>
                    )}
                    <Badge variant="muted">{formatDuration(elapsed)}</Badge>
                    {pipelineStatus === "transcribing" && (
                      <Badge variant="warning">
                        <Spinner className="mr-1 h-3 w-3" /> Transcribing…
                      </Badge>
                    )}
                    {pipelineStatus === "evaluating" && (
                      <Badge variant="info">
                        <Spinner className="mr-1 h-3 w-3" /> Evaluating…
                      </Badge>
                    )}
                  </div>
                  {transcript ? (
                    <p className="whitespace-pre-wrap rounded-md bg-secondary/40 p-3 text-sm">{transcript}</p>
                  ) : (
                    <p className="text-sm text-muted-foreground/60">
                      Click “Start Answer”, speak clearly, then “Stop Answer”. Your answer will be transcribed
                      automatically.
                    </p>
                  )}
                  {recorder.recording && (
                    <p className="flex items-center gap-2 text-xs text-red-400">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" /> Recording…
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
