import type {
  CreateInterviewInput,
  FollowUp,
  HistoryItem,
  InterviewReport,
  InterviewSummary,
  Question,
} from "@/types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  createInterview(input: CreateInterviewInput): Promise<InterviewSummary> {
    return request("/interviews", { method: "POST", body: JSON.stringify(input) });
  },
  listInterviews(): Promise<InterviewSummary[]> {
    return request("/interviews");
  },
  getInterview(id: number | string): Promise<InterviewSummary> {
    return request(`/interviews/${id}`);
  },
  getByRoom(roomCode: string): Promise<InterviewSummary> {
    return request(`/interviews/room/${roomCode}`);
  },
  startInterview(id: number | string): Promise<InterviewSummary> {
    return request(`/interviews/${id}/start`, { method: "POST" });
  },
  endInterview(id: number | string): Promise<InterviewSummary> {
    return request(`/interviews/${id}/end`, { method: "POST" });
  },
  getQuestions(id: number | string): Promise<Question[]> {
    return request(`/interviews/${id}/questions`);
  },
  getCandidateQuestions(id: number | string): Promise<Question[]> {
    return request(`/interviews/${id}/candidate/questions`);
  },
  getHistory(id: number | string): Promise<{ items: HistoryItem[] }> {
    return request(`/interviews/${id}/history`);
  },
  getFollowups(id: number | string): Promise<FollowUp[]> {
    return request(`/interviews/${id}/followups`);
  },
  selectFollowup(id: number | string, followupId: number): Promise<{ followup_id: number; text: string }> {
    return request(`/interviews/${id}/followups/${followupId}/select`, { method: "POST" });
  },
  submitAnswer(
    id: number | string,
    payload: {
      question_id?: number;
      followup_id?: number;
      transcript: string;
      duration_seconds?: number;
    },
  ): Promise<{
    answer_id: number;
    classification: string;
    score: number;
    reason: string;
    missing_concepts: string[];
    follow_up_required: boolean;
    follow_up_questions: string[];
  }> {
    return request(`/interviews/${id}/answers`, { method: "POST", body: JSON.stringify(payload) });
  },
  getReport(id: number | string): Promise<InterviewReport> {
    return request(`/interviews/${id}/report`);
  },
  getState(id: number | string): Promise<{ state: string; current_question_index: number | null; main_questions: number }> {
    return request(`/interviews/${id}/state`);
  },
  nextQuestion(id: number | string): Promise<Question> {
    return request(`/interviews/${id}/question/next`, { method: "POST" });
  },
  repeatQuestion(id: number | string): Promise<Question> {
    return request(`/interviews/${id}/question/repeat`, { method: "POST" });
  },
  moveToQuestion(id: number | string, questionNumber: number): Promise<Question> {
    return request(`/interviews/${id}/question/${questionNumber}`, { method: "POST" });
  },
  setState(id: number | string, toState: string): Promise<{ state: string }> {
    return request(`/interviews/${id}/state`, { method: "POST", body: JSON.stringify({ to_state: toState }) });
  },
};

export async function transcribeAudio(audioBlob: Blob): Promise<{ text: string; language: string | null }> {
  const form = new FormData();
  form.append("audio", audioBlob, "answer.webm");
  const res = await fetch(`${BASE}/transcription`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as { text: string; language: string | null };
}

export async function analyzeFace(imageBase64: string, interviewId: number | null) {
  const res = await fetch(`${BASE}/face-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_base64: imageBase64, interview_id: interviewId }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as {
    face_detected: boolean;
    category: string;
    confidence: number;
    timestamp: string;
  };
}
