import { create } from "zustand";

import type {
  Classification,
  EvaluationCompletedPayload,
  FaceAnalysisResult,
  FollowUp,
  HistoryItem,
  InterviewState,
  InterviewSummary,
  Question,
  Role,
} from "@/types";

export type PipelineStatus = "idle" | "recording" | "transcribing" | "evaluating";
export type WsStatus = "connecting" | "open" | "closed";
export interface ErrorNotice {
  id: number;
  message: string;
}

const ERROR_DISMISS_MS = 5000;
let errorIdCounter = 0;

interface InterviewStoreState {
  interview: InterviewSummary | null;
  role: Role | null;
  questions: Question[];
  currentQuestion: Question | null;
  currentFollowup: FollowUp | null;
  history: HistoryItem[];
  pendingFollowups: FollowUp[];
  state: InterviewState | null;
  pipelineStatus: PipelineStatus;
  transcript: string;
  lastEvaluation: EvaluationCompletedPayload | null;
  faceStatus: FaceAnalysisResult | null;
  wsStatus: WsStatus;
  peerConnected: boolean;
  errors: ErrorNotice[];

  setInterview: (i: InterviewSummary | null) => void;
  setRole: (r: Role) => void;
  setQuestions: (q: Question[]) => void;
  setCurrentQuestion: (q: Question | null) => void;
  setCurrentFollowup: (f: FollowUp | null) => void;
  setHistory: (h: HistoryItem[]) => void;
  setPendingFollowups: (f: FollowUp[]) => void;
  setState: (s: InterviewState | null) => void;
  setPipelineStatus: (s: PipelineStatus) => void;
  setTranscript: (t: string) => void;
  setLastEvaluation: (e: EvaluationCompletedPayload | null) => void;
  setFaceStatus: (f: FaceAnalysisResult | null) => void;
  setWsStatus: (s: WsStatus) => void;
  setPeerConnected: (c: boolean) => void;
  pushError: (e: string) => void;
  clearErrors: () => void;
  reset: () => void;
}

export const useInterviewStore = create<InterviewStoreState>((set) => ({
  interview: null,
  role: null,
  questions: [],
  currentQuestion: null,
  currentFollowup: null,
  history: [],
  pendingFollowups: [],
  state: null,
  pipelineStatus: "idle",
  transcript: "",
  lastEvaluation: null,
  faceStatus: null,
  wsStatus: "connecting",
  peerConnected: false,
  errors: [],

  setInterview: (interview) => set({ interview }),
  setRole: (role) => set({ role }),
  setQuestions: (questions) => set({ questions }),
  setCurrentQuestion: (currentQuestion) =>
    set({ currentQuestion, currentFollowup: null }),
  setCurrentFollowup: (currentFollowup) => set({ currentFollowup }),
  setHistory: (history) => set({ history }),
  setPendingFollowups: (pendingFollowups) => set({ pendingFollowups }),
  setState: (state) => set({ state }),
  setPipelineStatus: (pipelineStatus) => set({ pipelineStatus }),
  setTranscript: (transcript) => set({ transcript }),
  setLastEvaluation: (lastEvaluation) => set({ lastEvaluation }),
  setFaceStatus: (faceStatus) => set({ faceStatus }),
  setWsStatus: (wsStatus) => set({ wsStatus }),
  setPeerConnected: (peerConnected) => set({ peerConnected }),
  pushError: (message) => {
    const id = ++errorIdCounter;
    set((s) => ({ errors: [...s.errors.slice(-4), { id, message }] }));
    globalThis.setTimeout(() => {
      set((s) => ({ errors: s.errors.filter((e) => e.id !== id) }));
    }, ERROR_DISMISS_MS);  },
  clearErrors: () => set({ errors: [] }),
  reset: () =>
    set({
      interview: null,
      role: null,
      questions: [],
      currentQuestion: null,
      currentFollowup: null,
      history: [],
      pendingFollowups: [],
      state: null,
      pipelineStatus: "idle",
      transcript: "",
      lastEvaluation: null,
      faceStatus: null,
      wsStatus: "connecting",
      peerConnected: false,
      errors: [],
    }),
}));

export function classificationBadge(classification: Classification): string {
  switch (classification) {
    case "Correct":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "Incorrect":
      return "bg-red-500/15 text-red-400 border-red-500/30";
    case "Partially Correct":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "Not Confirmed":
      return "bg-slate-500/15 text-slate-400 border-slate-500/30";
  }
}
