export type Role = "interviewer" | "candidate";

export type InterviewType =
  | "Technical"
  | "HR"
  | "Behavioral"
  | "Python"
  | "Machine Learning"
  | "Data Science"
  | "SQL"
  | "Software Engineering"
  | "Custom";

export type Difficulty = "Easy" | "Medium" | "Hard";

export type Classification =
  | "Correct"
  | "Incorrect"
  | "Partially Correct"
  | "Not Confirmed";

export type InterviewState =
  | "CREATED"
  | "READY"
  | "RUNNING"
  | "WAITING_FOR_ANSWER"
  | "TRANSCRIBING"
  | "EVALUATING"
  | "FOLLOW_UP"
  | "NEXT_QUESTION"
  | "COMPLETED";

export type FaceCategory =
  | "Low confident"
  | "Nervous"
  | "Confident"
  | "Energetic"
  | "Face Not Detected";

export interface InterviewSummary {
  id: number;
  candidate_name: string;
  candidate_email: string;
  interview_type: string;
  difficulty: string;
  num_questions: number;
  job_description: string | null;
  status: InterviewState;
  room_code: string;
  join_url: string | null;
  current_question_index: number | null;
  main_questions_count: number;
  follow_up_questions_count: number;
  total_questions_asked: number;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
}

export interface Question {
  id: number;
  question_number: number;
  question: string;
  expected_answer?: string;
  topic: string;
  difficulty: string;
}

export interface MetricScore {
  name: string;
  score: number;
  note?: string;
}

export interface Evaluation {
  classification: Classification;
  score: number;
  reason: string;
  missing_concepts: string[];
  metrics?: MetricScore[];
  follow_up_required: boolean;
  follow_up_questions: string[];
}

export interface Answer {
  id: number;
  question_id: number | null;
  followup_id: number | null;
  is_followup: boolean;
  transcript: string;
  duration_seconds: number | null;
  created_at: string;
  evaluation: Evaluation | null;
}

export interface HistoryItem {
  question_number: number | null;
  question: string;
  expected_answer: string | null;
  topic: string | null;
  difficulty: string | null;
  is_followup: boolean;
  followup_text: string | null;
  answers: Answer[];
}

export interface FollowUp {
  id: number;
  question_id: number;
  followup_number: number;
  text: string;
  answered: boolean;
}

export interface FaceAnalysisResult {
  face_detected: boolean;
  category: FaceCategory;
  confidence: number;
  timestamp: string;
  features?: Record<string, number>;
}

export interface QuestionReportItem {
  question_number: number;
  question: string;
  classification: string;
  score: number;
  reason: string;
  metrics?: MetricScore[];
  follow_up_answers: Array<{ text: string; classification: string; score: number }>;
}

export interface InterviewReport {
  candidate_name: string;
  interview_type: string;
  difficulty: string;
  date: string;
  duration_seconds: number | null;
  main_questions_count: number;
  follow_up_questions_count: number;
  total_questions_asked: number;
  counts: Record<string, number>;
  percentages: Record<string, number>;
  performance_score: number | null;
  scoring_methodology: string;
  visual_cue_summary: Record<string, number>;
  section: {
    strengths: string[];
    weaknesses: string[];
    missing_concepts: string[];
    recommended_study_areas: string[];
    summary_note: string;
  };
  question_analysis: QuestionReportItem[];
  generated_at: string;
}

export interface CreateInterviewInput {
  candidate_name: string;
  candidate_email: string;
  interview_type: InterviewType;
  difficulty: Difficulty;
  num_questions: number;
  job_description?: string | null;
}

export type WsEventType =
  | "INTERVIEW_STARTED"
  | "QUESTION_CHANGED"
  | "INTERVIEW_ENDED"
  | "STATE_CHANGED"
  | "ANSWER_STARTED"
  | "ANSWER_STOPPED"
  | "TRANSCRIPTION_STARTED"
  | "TRANSCRIPTION_UPDATED"
  | "TRANSCRIPTION_COMPLETED"
  | "EVALUATION_STARTED"
  | "EVALUATION_COMPLETED"
  | "FOLLOWUP_GENERATED"
  | "FOLLOWUP_SELECTED"
  | "FACE_ANALYSIS_UPDATED"
  | "MEDIA_STATE"
  | "CONNECTION_OPEN"
  | "CANDIDATE_CONNECTED"
  | "INTERVIEWER_CONNECTED"
  | "PEER_DISCONNECTED"
  | "CONNECTION_CLOSED"
  | "JOIN"
  | "SIGNAL"
  | "ERROR";

export interface WsMessage {
  type: WsEventType;
  interview_id?: number | null;
  role?: Role | null;
  payload?: Record<string, unknown>;
  sent_at?: string | null;
}

export interface EvaluationCompletedPayload {
  answer_id: number;
  question_id: number | null;
  followup_id: number | null;
  is_followup: boolean;
  transcript: string;
  classification: Classification;
  score: number;
  reason: string;
  missing_concepts: string[];
  metrics?: MetricScore[];
  follow_up_required: boolean;
  follow_up_questions: string[];
  followup_ids: number[];
}
