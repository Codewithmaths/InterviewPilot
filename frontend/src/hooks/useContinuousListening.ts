import { useCallback, useEffect, useRef, useState } from "react";

import { api, transcribeAudio } from "@/lib/api";
import type { WsClient } from "@/lib/ws";

export type ListeningStatus = "idle" | "listening" | "transcribing" | "evaluating";

interface UseContinuousListeningOptions {
  stream: MediaStream | null;
  interviewId: number;
  questionId: number | null;
  followupId: number | null;
  wsClient: WsClient | null;
  enabled: boolean;
  onTranscript?: (text: string) => void;
  onStatusChange?: (status: ListeningStatus) => void;
  onError?: (message: string) => void;
}

function rms(frame: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  return Math.sqrt(sum / frame.length);
}

// Console diagnostics — visible in DevTools so VAD failures are traceable.
const log = (...args: unknown[]) => console.debug("[VAD]", ...args);

/**
 * Continuously listens using Web Audio API RMS-based VAD.
 *
 * Robustness rules (each fixes a real "stuck at listening" failure mode):
 * - Polls via setInterval (keeps running in background tabs, unlike rAF).
 * - A burst must stay loud ~200ms to count as speech (ignores clicks/spikes).
 * - End-of-speech uses ACCUMULATED quiet time: short noise spikes delay the
 *   end by their own length only, they never restart a 2s countdown.
 * - Only a sustained speech burst (>=400ms) resets accumulated quiet time,
 *   so real inter-sentence pauses don't cut an answer short.
 * - Hard caps: 45s per utterance, 1.5s stop-recorder timeout — the pipeline
 *   always reaches transcription/submission, whatever happens.
 */
export function useContinuousListening({
  stream,
  interviewId,
  questionId,
  followupId,
  wsClient,
  enabled,
  onTranscript,
  onStatusChange,
  onError,
}: UseContinuousListeningOptions) {
  const [status, setStatus] = useState<ListeningStatus>("idle");
  const [transcript, setTranscript] = useState("");

  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const loopRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const clonedTracksRef = useRef<MediaStreamTrack[]>([]);

  const isSubmittingRef = useRef(false);
  const speechActiveRef = useRef(false);

  const questionIdRef = useRef(questionId);
  const followupIdRef = useRef(followupId);
  const wsRef = useRef(wsClient);
  const statusRef = useRef<ListeningStatus>("idle");
  const enabledRef = useRef(enabled);
  const interviewIdRef = useRef(interviewId);
  const recorderStartedAtRef = useRef(0);
  const streamRef = useRef(stream);

  // Use refs for callbacks so the loop always has fresh references
  const onTranscriptRef = useRef(onTranscript);
  const onStatusChangeRef = useRef(onStatusChange);
  const onErrorRef = useRef(onError);

  // Noise-floor calibration: measure ambient level for the first ~800ms,
  // then trigger speech at max(absolute minimum, 3x the measured floor).
  const NOISE_CALIBRATION_MS = 800;
  const MIN_THRESHOLD = 0.008;
  const QUIET_END_MS = 2000; // net quiet time that ends an utterance
  const MIN_SPEECH_MS = 600; // minimum confirmed speech to bother transcribing
  const REAL_BURST_MS = 400; // a loud burst this long = real speech (resets quiet acc)
  // VAD polling interval. setInterval keeps firing (throttled) in background
  // tabs, unlike requestAnimationFrame which freezes — that freeze caused
  // "stuck at listening" whenever the candidate looked away from the tab.
  const TICK_MS = 50;
  const SPEECH_FRAMES_NEEDED = Math.ceil(REAL_BURST_MS / TICK_MS); // ~200ms to START speech
  // Safety cap: never record a single utterance longer than this.
  const MAX_UTTERANCE_MS = 45_000;

  useEffect(() => { questionIdRef.current = questionId; }, [questionId]);
  useEffect(() => { followupIdRef.current = followupId; }, [followupId]);
  useEffect(() => { wsRef.current = wsClient; }, [wsClient]);
  useEffect(() => { enabledRef.current = enabled; }, [enabled]);
  useEffect(() => { interviewIdRef.current = interviewId; }, [interviewId]);
  useEffect(() => { streamRef.current = stream; }, [stream]);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onStatusChangeRef.current = onStatusChange; }, [onStatusChange]);
  useEffect(() => { onErrorRef.current = onError; }, [onError]);

  const updateStatus = useCallback((s: ListeningStatus) => {
    if (statusRef.current === s) return;
    statusRef.current = s;
    setStatus(s);
    log("status →", s);
    onStatusChangeRef.current?.(s);
  }, []);

  const releaseClonedTracks = useCallback(() => {
    for (const track of clonedTracksRef.current) {
      try { track.stop(); } catch { /* ignore */ }
    }
    clonedTracksRef.current = [];
  }, []);

  const startRecorder = useCallback((): boolean => {
    const current = streamRef.current;
    if (!current) return false;
    const audioTracks = current.getAudioTracks();
    const liveTracks = audioTracks.filter((t) => t.readyState === "live");
    if (!liveTracks.length) {
      log("startRecorder: no live audio tracks");
      return false;
    }

    try {
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";
      const clones = liveTracks.map((t) => t.clone());
      clonedTracksRef.current = clones;
      const audioStream = new MediaStream(clones);
      const recorder = new MediaRecorder(audioStream, mime ? { mimeType: mime } : undefined);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onerror = (e) => log("recorder error:", e);
      recorderStartedAtRef.current = Date.now();
      recorder.start(3000);
      log("recorder started", mime || "(default)");
      return true;
    } catch (err) {
      log("startRecorder failed:", err);
      releaseClonedTracks();
      return false;
    }
  }, [releaseClonedTracks]);

  const stopRecorder = useCallback((): Promise<{ blob: Blob; durationMs: number } | null> => {
    return new Promise((resolve) => {
      const recorder = recorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        releaseClonedTracks();
        resolve(null);
        return;
      }
      const start = recorderStartedAtRef.current;
      // Safety: never hang waiting for onstop (recorder error paths can skip it)
      const bail = setTimeout(() => {
        log("stopRecorder timed out");
        releaseClonedTracks();
        resolve(null);
      }, 1500);
      recorder.onstop = () => {
        clearTimeout(bail);
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        releaseClonedTracks();
        resolve({ blob, durationMs: Date.now() - start });
      };
      try {
        recorder.stop();
      } catch (err) {
        clearTimeout(bail);
        log("recorder.stop() threw:", err);
        releaseClonedTracks();
        resolve(null);
      }
    });
  }, [releaseClonedTracks]);

  // Submit answer — uses refs so it's safe from the loop
  const doSubmitAnswer = useCallback(
    async (finalTranscript: string, durationSeconds?: number) => {
      if (isSubmittingRef.current || !finalTranscript.trim()) return;
      isSubmittingRef.current = true;
      updateStatus("evaluating");
      const qid = questionIdRef.current;
      const fid = followupIdRef.current;
      log("submitting answer", { qid, fid, chars: finalTranscript.length });
      try {
        if (qid) {
          await api.submitAnswer(interviewIdRef.current, {
            question_id: qid,
            transcript: finalTranscript.trim(),
            duration_seconds: durationSeconds,
          });
        } else if (fid) {
          await api.submitAnswer(interviewIdRef.current, {
            followup_id: fid,
            transcript: finalTranscript.trim(),
            duration_seconds: durationSeconds,
          });
        } else {
          log("no active question/followup — dropping answer");
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        log("submit failed:", msg);
        onErrorRef.current?.(`Could not submit your answer: ${msg}`);
      } finally {
        isSubmittingRef.current = false;
        setTranscript("");
        updateStatus("idle");
      }
    },
    [updateStatus],
  );

  // Handle speech end — called from the loop via ref
  const handleSpeechEnd = useCallback(async (speechMs: number) => {
    if (isSubmittingRef.current || statusRef.current !== "listening") return;

    const result = await stopRecorder();

    // Too little real speech (coughs, bumps) — discard silently, keep listening.
    if (!result || result.blob.size < 500 || speechMs < MIN_SPEECH_MS) {
      log("utterance discarded", { bytes: result?.blob.size ?? 0, speechMs });
      updateStatus("idle");
      return;
    }

    updateStatus("transcribing");
    wsRef.current?.send("ANSWER_STOPPED", {});
    wsRef.current?.send("TRANSCRIPTION_STARTED", {});
    log("transcribing", { bytes: result.blob.size, ms: result.durationMs, speechMs });

    let text = "";
    try {
      const res = await transcribeAudio(result.blob);
      text = res.text?.trim() ?? "";
      log("transcript:", text);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log("transcription failed:", msg);
      onErrorRef.current?.(`Transcription failed: ${msg}. You can also type your answer below.`);
    }

    if (text) {
      setTranscript(text);
      onTranscriptRef.current?.(text);
      await doSubmitAnswer(text, Math.round(result.durationMs / 1000));
    } else {
      updateStatus("idle");
    }
  }, [stopRecorder, doSubmitAnswer, updateStatus]);

  // Store handleSpeechEnd in a ref so the loop always calls the latest version
  const handleSpeechEndRef = useRef(handleSpeechEnd);
  useEffect(() => { handleSpeechEndRef.current = handleSpeechEnd; }, [handleSpeechEnd]);

  // Start/stop VAD loop
  useEffect(() => {
    if (!enabled || !stream) {
      // Cleanup
      if (loopRef.current) { clearInterval(loopRef.current); loopRef.current = null; }
      speechActiveRef.current = false;
      if (sourceRef.current) { try { sourceRef.current.disconnect(); } catch { /* */ } sourceRef.current = null; }
      if (audioCtxRef.current) { audioCtxRef.current.close().catch(() => undefined); audioCtxRef.current = null; }
      analyserRef.current = null;
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        try { recorderRef.current.onstop = null; recorderRef.current.stop(); } catch { /* */ }
      }
      releaseClonedTracks();
      return;
    }

    if (audioCtxRef.current) return; // already running

    let ctx: AudioContext;
    try {
      ctx = new AudioContext();
    } catch (err) {
      log("AudioContext creation failed:", err);
      onErrorRef.current?.("Could not access audio processing. Please reload the page.");
      return;
    }

    // Chrome/Safari can create the context suspended outside a user gesture.
    void ctx.resume().catch(() => undefined);

    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);

    audioCtxRef.current = ctx;
    sourceRef.current = source;
    analyserRef.current = analyser;

    const dataArray = new Float32Array(analyser.fftSize);

    // --- Loop-local state -------------------------------------------------
    let calibrating = true;
    let calibrationStart = Date.now();
    let noiseSamples = 0;
    let noiseSum = 0;
    let threshold = MIN_THRESHOLD * 2;

    let loudStreak = 0;          // consecutive above-threshold ticks
    let recording = false;       // recorder active for current utterance
    let utteranceStart = 0;      // when recording started
    let speechMs = 0;            // total confirmed-speech time this utterance
    let quietMs = 0;             // accumulated quiet time this utterance
    let burstMs = 0;             // length of the current loud burst

    log("VAD loop started", { sampleRate: ctx.sampleRate, state: ctx.state });

    const finishUtterance = (reason: string) => {
      const totalSpeech = speechMs;
      recording = false;
      speechActiveRef.current = false;
      loudStreak = 0;
      burstMs = 0;
      quietMs = 0;
      log("ending utterance:", reason, { speechMs: totalSpeech });
      handleSpeechEndRef.current(totalSpeech);
    };

    const tick = () => {
      if (!enabledRef.current || !analyserRef.current || !audioCtxRef.current) {
        if (loopRef.current) { clearInterval(loopRef.current); loopRef.current = null; }
        return;
      }

      let energy = 0;
      try {
        analyserRef.current.getFloatTimeDomainData(dataArray);
        energy = rms(dataArray);
      } catch (err) {
        log("analyser read failed:", err);
        return;
      }

      if (calibrating) {
        noiseSum += energy;
        noiseSamples += 1;
        if (Date.now() - calibrationStart >= NOISE_CALIBRATION_MS) {
          const floor = noiseSamples ? noiseSum / noiseSamples : 0;
          threshold = Math.max(MIN_THRESHOLD, floor * 3);
          calibrating = false;
          log("calibration done", { floor: floor.toFixed(4), threshold: threshold.toFixed(4) });
        }
        return;
      }

      const loud = energy > threshold;
      loudStreak = loud ? loudStreak + 1 : 0;
      const speechConfirmed = loudStreak >= SPEECH_FRAMES_NEEDED;

      if (speechConfirmed) {
        if (!speechActiveRef.current) {
          speechActiveRef.current = true;
          log("speech started", { energy: energy.toFixed(4), threshold: threshold.toFixed(4) });
        }

        if (!recording && !isSubmittingRef.current) {
          const st = statusRef.current;
          if (st === "idle" || st === "listening") {
            if (!recorderRef.current || recorderRef.current.state === "inactive") {
              if (startRecorder()) {
                recording = true;
                utteranceStart = Date.now();
                speechMs = 0;
                quietMs = 0;
                burstMs = 0;
                updateStatus("listening");
                wsRef.current?.send("ANSWER_STARTED", {
                  question_id: followupIdRef.current ? undefined : questionIdRef.current,
                  followup_id: followupIdRef.current ?? undefined,
                });
              }
            } else {
              // Recorder already running (leftover) — adopt it.
              recording = true;
              utteranceStart = Date.now();
              speechMs = 0;
              quietMs = 0;
              burstMs = 0;
              updateStatus("listening");
            }
          }
        }

        if (recording) {
          speechMs += TICK_MS;
          burstMs += TICK_MS;
          if (burstMs >= REAL_BURST_MS) {
            // A sustained real burst clears accumulated quiet time, so normal
            // pauses between sentences each get the full QUIET_END_MS budget.
            // Short spikes never reach here — they only add their own length.
            quietMs = 0;
          }
          if (Date.now() - utteranceStart > MAX_UTTERANCE_MS) {
            finishUtterance("max utterance duration");
          }
        }
      } else {
        // Quiet tick (or an unconfirmed short spike)
        burstMs = 0;
        if (recording) {
          quietMs += TICK_MS;
          if (quietMs >= QUIET_END_MS) {
            finishUtterance("net silence reached");
          } else if (Date.now() - utteranceStart > MAX_UTTERANCE_MS) {
            finishUtterance("max utterance duration");
          }
        } else if (speechActiveRef.current) {
          // Speech flagged but never recorded (pipeline busy) — release on quiet.
          speechActiveRef.current = false;
        }
      }
    };

    loopRef.current = setInterval(tick, TICK_MS);

    return () => {
      log("VAD loop stopped");
      if (loopRef.current) { clearInterval(loopRef.current); loopRef.current = null; }
      speechActiveRef.current = false;
      if (sourceRef.current) { try { sourceRef.current.disconnect(); } catch { /* */ } sourceRef.current = null; }
      if (audioCtxRef.current) { audioCtxRef.current.close().catch(() => undefined); audioCtxRef.current = null; }
      analyserRef.current = null;
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        try { recorderRef.current.onstop = null; recorderRef.current.stop(); } catch { /* */ }
      }
      releaseClonedTracks();
    };
  }, [enabled, stream]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset transcript when question changes
  useEffect(() => {
    setTranscript("");
  }, [questionId, followupId]);

  return { status, transcript };
}
