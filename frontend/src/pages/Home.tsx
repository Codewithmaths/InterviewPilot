import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BarChart3, ChevronDown, History, Loader2, Video } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { CreateInterviewInput, Difficulty, InterviewSummary, InterviewType } from "@/types";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";

const INTERVIEW_TYPES: InterviewType[] = [
  "Technical",
  "HR",
  "Behavioral",
  "Python",
  "Machine Learning",
  "Data Science",
  "SQL",
  "Software Engineering",
  "Custom",
];

const DIFFICULTIES: Difficulty[] = ["Easy", "Medium", "Hard"];

function interviewTypeOptions() {
  return INTERVIEW_TYPES.map((t) => ({ value: t, label: t }));
}
function difficultyOptions() {
  return DIFFICULTIES.map((d) => ({ value: d, label: d }));
}
function countOptions() {
  return Array.from({ length: 11 }, (_, i) => i + 20).map((n) => ({ value: String(n), label: `${n} questions` }));
}

export default function HomePage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<CreateInterviewInput>({
    candidate_name: "",
    candidate_email: "",
    interview_type: "Python",
    difficulty: "Medium",
    num_questions: 20,
    job_description: "",
  });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
  const [showRecent, setShowRecent] = useState(false);

  useEffect(() => {
    api.listInterviews().then(setInterviews).catch(() => setInterviews([]));
  }, []);

  const submit = async () => {
    setCreating(true);
    setError(null);
    try {
      const interview = await api.createInterview({
        ...form,
        job_description: form.job_description?.trim() ? form.job_description : null,
      });
      navigate(`/interviewer/${interview.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create interview");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-0">
        <div className="absolute -right-40 -top-40 h-[34rem] w-[34rem] rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="absolute -bottom-56 -left-40 h-[30rem] w-[30rem] rounded-full bg-blue-600/10 blur-3xl" />
        <div className="perspective-grid absolute -bottom-28 left-[-12%] h-[48%] w-[124%] opacity-40" />
      </div>

      <div className="container relative z-10 max-w-7xl px-6 py-10 sm:px-8 lg:px-12">
      <header className="mb-8 rounded-2xl border border-border/70 bg-card/50 px-5 py-5 backdrop-blur-sm sm:px-7">
        <div className="flex items-center gap-3">
          <Video className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">InterviewPilot</h1>
            <p className="text-sm text-muted-foreground">
              AI-assisted live interviews with real-time transcription, evaluation and visual-cue analysis.
            </p>
          </div>
        </div>
      </header>

      <div className={showRecent ? "grid gap-8 lg:grid-cols-[2fr_1fr]" : "block"}>
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Create Interview</CardTitle>
              <CardDescription>Generate 20–30 LLM questions and generate a join link.</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => setShowRecent((visible) => !visible)}>
              <History className="h-4 w-4" />
              {showRecent ? "Hide Recent" : `Recent Interviews (${Math.min(interviews.length, 5)})`}
              <ChevronDown className={`h-4 w-4 transition-transform ${showRecent ? "rotate-180" : ""}`} />
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="candidate_name">Candidate Name</Label>
                <Input
                  id="candidate_name"
                  placeholder="Jane Doe"
                  value={form.candidate_name}
                  onChange={(e) => setForm({ ...form, candidate_name: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="candidate_email">Candidate Email</Label>
                <Input
                  id="candidate_email"
                  type="email"
                  placeholder="jane@example.com"
                  value={form.candidate_email}
                  onChange={(e) => setForm({ ...form, candidate_email: e.target.value })}
                />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="type">Interview Type</Label>
                <Select
                  id="type"
                  options={interviewTypeOptions()}
                  value={form.interview_type}
                  onChange={(e) => setForm({ ...form, interview_type: e.target.value as InterviewType })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="difficulty">Difficulty</Label>
                <Select
                  id="difficulty"
                  options={difficultyOptions()}
                  value={form.difficulty}
                  onChange={(e) => setForm({ ...form, difficulty: e.target.value as Difficulty })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="count">Questions</Label>
                <Select
                  id="count"
                  options={countOptions()}
                  value={String(form.num_questions)}
                  onChange={(e) => setForm({ ...form, num_questions: Number(e.target.value) })}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="jd">Job Description (optional)</Label>
              <Textarea
                id="jd"
                rows={4}
                placeholder="Paste the job description to align questions with the role…"
                value={form.job_description ?? ""}
                onChange={(e) => setForm({ ...form, job_description: e.target.value })}
              />
            </div>
            <Button onClick={submit} disabled={creating || !form.candidate_name || !form.candidate_email}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
              {creating ? "Generating questions…" : "Create Interview"}
            </Button>
          </CardContent>
        </Card>

        {showRecent && <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <History className="h-5 w-5 text-primary" /> Recent Interviews
            </CardTitle>
            <CardDescription>Reopen a live interview or view a completed report.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {interviews.length === 0 && (
              <p className="text-sm text-muted-foreground/60">No interviews yet. Create one to begin.</p>
            )}
            {interviews.slice(0, 5).map((iv) => (
              <div
                key={iv.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-border p-3 transition-colors hover:bg-secondary/30"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {iv.candidate_name} · {iv.interview_type}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {iv.difficulty} · {iv.num_questions} questions · {formatDate(iv.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge variant={iv.status === "COMPLETED" ? "muted" : iv.status === "RUNNING" ? "success" : "info"}>
                    {iv.status}
                  </Badge>
                  {iv.status === "COMPLETED" ? (
                    <Button size="sm" variant="outline" asChild>
                      <Link to={`/report/${iv.id}`}>
                        <BarChart3 className="h-3.5 w-3.5" /> Report
                      </Link>
                    </Button>
                  ) : (
                    <Button size="sm" variant="outline" asChild>
                      <Link to={`/interviewer/${iv.id}`}>Resume</Link>
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>}
      </div>
      </div>
    </div>
  );
}
