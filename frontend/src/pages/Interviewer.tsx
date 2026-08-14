import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, Copy, Loader2, PlayCircle, Video } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { WsClient } from "@/lib/ws";
import { useMedia } from "@/hooks/useMedia";
import { useWebRTC } from "@/hooks/useWebRTC";
import { useInterviewStore } from "@/store/useInterviewStore";
import type { EvaluationCompletedPayload, Question } from "@/types";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { VideoPanel } from "@/components/VideoPanel";
import { AudioControls } from "@/components/AudioControls";
import { QuestionCard } from "@/components/QuestionCard";
import { ExpectedAnswerCard } from "@/components/ExpectedAnswerCard";
import { EvaluationCard } from "@/components/EvaluationCard";
import { FollowUpPanel } from "@/components/FollowUpPanel";
import { InterviewHistory } from "@/components/InterviewHistory";
import { FaceStatus } from "@/components/FaceStatus";
import { InterviewControls } from "@/components/InterviewControls";

export default function InterviewerPage() {
  const { id } = useParams<{ id: string }>();
  const {
    interview,
    setInterview,
    setRole,
    setQuestions,
    questions,
    currentQuestion,
    setCurrentQuestion,
    history,
    setHistory,
    pendingFollowups,
    setPendingFollowups,
    setState,
    state,
    setLastEvaluation,
    lastEvaluation,
    faceStatus,
    setFaceStatus,
    setWsStatus,
    wsStatus,
    peerConnected,
    setPeerConnected,
    errors,
    pushError,
    setPipelineStatus,
  } = useInterviewStore();

  const [loading, setLoading] = useState(true);
  const [started, setStarted] = useState(false);
  const [wsClient, setWsClient] = useState<WsClient | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const wsRef = useRef<WsClient | null>(null);
  const idRef = useRef(id);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const media = useMedia();
  const rtc = useWebRTC("interviewer", wsClient, media.stream);
  const localVideoRef = useRef<HTMLVideoElement | null>(null);
  const questionsRef = useRef<Question[]>([]);

  const isBusy = state === "TRANSCRIBING" || state === "EVALUATING" || state === "WAITING_FOR_ANSWER";

  // Build the candidate link from the current origin (single-origin deploy),
  // so it is correct even if FRONTEND_URL is missing on the server.
  const joinUrl = interview
    ? `${window.location.origin}/candidate/${interview.id}/${interview.room_code}`
    : null;

  useEffect(() => {
    idRef.current = id;
  }, [id]);

  useEffect(() => {
    questionsRef.current = questions;
  }, [questions]);

  // Load initial data + connect WS
  useEffect(() => {
    if (!id) return;
    setRole("interviewer");
    let cancelled = false;

    (async () => {
      try {
        const [iv, qs, h, fups] = await Promise.all([
          api.getInterview(id),
          api.getQuestions(id),
          api.getHistory(id),
          api.getFollowups(id),
        ]);
        if (cancelled) return;
        setInterview(iv);
        setQuestions(qs);
        setHistory(h.items);
        setPendingFollowups(fups);
        setState(iv.status as never);
        setStarted(iv.status !== "CREATED");
        if (iv.current_question_index) {
          const q = qs.find((x) => x.question_number === iv.current_question_index);
          if (q) setCurrentQuestion(q);
        }
      } catch (err) {
        if (!cancelled) pushError(err instanceof ApiError ? err.message : "Failed to load interview");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    const ws = new WsClient(id, "interviewer");
    wsRef.current = ws;
    setWsClient(ws);
    ws.connect();

    const onOpen = ws.on("CONNECTION_OPEN", () => setWsStatus("open"));
    const onJoined = ws.on("CANDIDATE_CONNECTED", () => setPeerConnected(true));
    const onPeerLeft = ws.on("PEER_DISCONNECTED", (m) => {
      if (m.payload?.role === "candidate") setPeerConnected(false);
    });

    const onState = ws.on("STATE_CHANGED", (m) => {
      setState((m.payload?.to as never) ?? null);
    });
    const onStarted = ws.on("INTERVIEW_STARTED", () => {
      setStarted(true);
      setState("RUNNING" as never);
    });
    const onQuestion = ws.on("QUESTION_CHANGED", (m) => {
      const num = m.payload?.question_number as number;
      setCurrentQuestion(questionsRef.current.find((q) => q.question_number === num) ?? null);
    });
    const onEval = ws.on("EVALUATION_COMPLETED", (m) => {
      setLastEvaluation(m.payload as unknown as EvaluationCompletedPayload);
      setState("NEXT_QUESTION" as never);
      setPipelineStatus("idle");
      api.getHistory(id).then((h) => setHistory(h.items)).catch(() => undefined);
      api.getFollowups(id).then(setPendingFollowups).catch(() => undefined);
    });
    const onFace = ws.on("FACE_ANALYSIS_UPDATED", (m) => {
      setFaceStatus(m.payload as never);
    });
    const onEnded = ws.on("INTERVIEW_ENDED", () => {
      setState("COMPLETED" as never);
      setStarted(false);
      rtc.hangup();
      media.stop();
    });
    const onError = ws.on("ERROR", (m) => {
      pushError(String(m.payload?.message ?? "Server error"));
    });

    return () => {
      cancelled = true;
      onOpen();
      onJoined();
      onPeerLeft();
      onState();
      onStarted();
      onQuestion();
      onEval();
      onFace();
      onEnded();
      onError();
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Mirror interviewer's own local video
  useEffect(() => {
    const el = localVideoRef.current;
    if (el && media.stream && el.srcObject !== media.stream) el.srcObject = media.stream;
  }, [media.stream]);

  useEffect(() => {
    if (peerConnected && media.stream && wsStatus === "open" && rtc.status === "idle") {
      void rtc.negotiate();
    }
  }, [media.stream, peerConnected, rtc, wsStatus]);

  const currentQuestionData = currentQuestion ?? null;
  // Show follow-ups only alongside the original question they belong to, and
  // only while they are unanswered. Skipped follow-ups from previous questions
  // no longer clutter the panel.
  const askableFollowups = pendingFollowups.filter(
    (f) => !f.answered && f.question_id === currentQuestionData?.id,
  );

  // Reset the "Copied" indicator timer on unmount.
  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleCopyLink = useCallback(async () => {
    if (!joinUrl) return;
    try {
      await navigator.clipboard.writeText(joinUrl);
      setLinkCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setLinkCopied(false), 2000);
    } catch {
      pushError("Could not copy the link automatically. Please copy it manually.");
    }
  }, [joinUrl, pushError]);

  const handleStart = useCallback(async () => {
    if (!id) return;
    try {
      const granted = await media.requestMedia();
      if (granted && wsClient) {
        const iv = await api.startInterview(id);
        setInterview(iv);
        setStarted(true);
        setState("RUNNING" as never);
      }
    } catch (err) {
      pushError(err instanceof ApiError ? err.message : "Could not start interview");
    }
  }, [id, media, wsClient, setInterview, setState, setStarted, pushError]);

  const handleNext = useCallback(async () => {
    if (!id) return;
    try {
      const q = await api.nextQuestion(id);
      setCurrentQuestion(q);
      setLastEvaluation(null);
      setState("RUNNING" as never);
    } catch (err) {
      pushError(err instanceof ApiError ? err.message : "Could not move to next question");
    }
  }, [id, setCurrentQuestion, setLastEvaluation, setState, pushError]);

  const handleSkip = useCallback(async () => {
    if (!id) return;
    try {
      const q = await api.skipQuestion(id);
      setCurrentQuestion(q);
      setLastEvaluation(null);
      setState("RUNNING" as never);
      api.getFollowups(id).then(setPendingFollowups).catch(() => undefined);
    } catch (err) {
      pushError(err instanceof ApiError ? err.message : "Could not skip question");
    }
  }, [id, setCurrentQuestion, setLastEvaluation, setState, setPendingFollowups, pushError]);

  const handleRepeat = useCallback(async () => {
    if (!id) return;
    try {
      const q = await api.repeatQuestion(id);
      setCurrentQuestion(q);
      setLastEvaluation(null);
    } catch (err) {
      pushError(err instanceof ApiError ? err.message : "Could not repeat question");
    }
  }, [id, setCurrentQuestion, setLastEvaluation, pushError]);

  const handlePrevious = useCallback(async () => {
    const currentNumber = currentQuestion?.question_number ?? interview?.current_question_index;
    if (!id || !currentNumber || currentNumber <= 1) return;
    try {
      const q = await api.moveToQuestion(id, currentNumber - 1);
      setCurrentQuestion(q);
      setLastEvaluation(null);
    } catch (err) {
      pushError(err instanceof ApiError ? err.message : "Could not move to previous question");
    }
  }, [id, currentQuestion, interview, setCurrentQuestion, setLastEvaluation, pushError]);

  const handleEnd = useCallback(async () => {
    if (!id) return;
    try {
      const iv = await api.endInterview(id);
      setInterview(iv);
      setState("COMPLETED" as never);
      setStarted(false);
      rtc.hangup();
      media.stop();
    } catch (err) {
      pushError(err instanceof ApiError ? err.message : "Could not end interview");
    }
  }, [id, media, rtc, setInterview, setState, pushError]);

  const handleSelectFollowup = useCallback(
    async (followupId: number) => {
      if (!id) return;
      try {
        await api.selectFollowup(id, followupId);
        setState("WAITING_FOR_ANSWER" as never);
      } catch (err) {
        pushError(err instanceof ApiError ? err.message : "Could not select follow-up");
      }
    },
    [id, setState, pushError],
  );

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" /> Loading interview…
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
            <Badge variant="success" className="hidden sm:inline-flex">
              Live Interview
            </Badge>
          </div>
          <ConnectionStatus
            wsStatus={wsStatus}
            peerConnected={peerConnected}
            label={peerConnected ? "Candidate connected" : "Waiting for candidate"}
          />
        </div>
      </header>

      <main className="container mt-6">
        {errors.length > 0 && (
          <div className="mb-4 space-y-2">
            {errors.map((e) => (
              <Alert key={e.id} variant="destructive">
                <AlertTitle>Error</AlertTitle>
                <AlertDescription>{e.message}</AlertDescription>
              </Alert>
            ))}
          </div>
        )}

        {state === "COMPLETED" && (
          <Alert className="mb-4">
            <AlertTitle className="text-emerald-400">Interview completed</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center gap-2">
              The interview has ended and the candidate has been notified.
              <Button asChild size="sm" variant="outline">
                <Link to={`/report/${id}`}>View Report</Link>
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {!started && state !== "COMPLETED" && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <PlayCircle className="h-5 w-5 text-primary" />
                Interview ready — {interview?.candidate_name}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{interview?.interview_type}</span> ·{" "}
                {interview?.difficulty} · {interview?.num_questions} questions
              </p>
              <p className="text-sm text-muted-foreground">
                Share this link with the candidate to join:
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded-md bg-secondary/50 p-3 text-xs">
                  {joinUrl}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleCopyLink}
                  disabled={!joinUrl}
                >
                  {linkCopied ? (
                    <Check className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                  {linkCopied ? "Copied" : "Copy link"}
                </Button>
              </div>
              <Button onClick={handleStart} disabled={!interview}>
                <PlayCircle className="h-4 w-4" /> Grant permissions &amp; Start Interview
              </Button>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-6 xl:grid-cols-12">
          {/* Video column */}
          <div className="space-y-4 xl:col-span-4">
            <VideoPanel
              stream={rtc.remoteStream}
              label="Candidate"
              cameraState="connected"
              micState="connected"
              faceCategory={faceStatus?.category ?? null}
            />
            <Card>
              <CardContent className="p-4">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Your camera (interviewer)
                </p>
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
            <Card>
              <CardContent className="p-4">
                <FaceStatus result={faceStatus} />
              </CardContent>
            </Card>
          </div>

          {/* Question column */}
          <div className="space-y-4 xl:col-span-5">
            <QuestionCard
              question={currentQuestionData}
              index={currentQuestionData?.question_number ?? interview?.current_question_index ?? null}
              total={interview?.num_questions ?? questions.length}
            />
            <ExpectedAnswerCard expectedAnswer={currentQuestionData?.expected_answer ?? null} />
            {lastEvaluation && <EvaluationCard evaluation={lastEvaluation} />}
            <FollowUpPanel
              followups={askableFollowups}
              onSelect={handleSelectFollowup}
              disabled={isBusy || state === "COMPLETED"}
              selected={state === "WAITING_FOR_ANSWER" ? askableFollowups[0]?.id : null}
            />
            {state === "WAITING_FOR_ANSWER" && (
              <Alert>
                <AlertTitle className="text-amber-300">Candidate is answering…</AlertTitle>
                <AlertDescription>Transcription will appear here once the candidate stops recording.</AlertDescription>
              </Alert>
            )}
          </div>

          {/* History column */}
          <div className="space-y-4 xl:col-span-3">
            <InterviewControls
              onPrevious={handlePrevious}
              onRepeat={handleRepeat}
              onSkip={handleSkip}
              onNext={handleNext}
              onEnd={handleEnd}
              busy={isBusy || !started || state === "COMPLETED"}
              canNavigate={started && state !== "COMPLETED"}
            />
            <InterviewHistory items={history} />
          </div>
        </div>
      </main>
    </div>
  );
}
