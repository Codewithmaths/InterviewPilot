import { Award, BarChart3, FileText, TrendingUp, TrendingDown } from "lucide-react";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { InterviewReport } from "@/types";
import { classificationColor, formatDate, formatDuration } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";

const CLASS_COLORS: Record<string, string> = {
  Correct: "#10b981",
  Incorrect: "#ef4444",
  "Partially Correct": "#f59e0b",
  "Not Confirmed": "#94a3b8",
  Skipped: "#8b5cf6",
  "Not Answered": "#64748b",
};

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/30 p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

export function ReportDashboard({ report }: { report: InterviewReport }) {
  const counts = Object.entries(report.counts)
    .filter(([k, v]) => (v ?? 0) > 0 || (k !== "Skipped" && k !== "Not Answered"))
    .map(([name, value]) => ({ name, value }));

  const visualData = Object.entries(report.visual_cue_summary).map(([name, value]) => ({
    name,
    value,
  }));

  const scorePct = report.performance_score !== null ? Math.round(report.performance_score * 100) : null;
  const skipped = report.counts["Skipped"] ?? 0;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            Interview Summary
          </CardTitle>
          <CardDescription>Generated {formatDate(report.generated_at)}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Candidate" value={report.candidate_name} sub={`${report.interview_type} · ${report.difficulty}`} />
          <Stat label="Date" value={formatDate(report.date)} sub={`Duration ${formatDuration(report.duration_seconds)}`} />
          <Stat label="Questions" value={report.total_questions_asked} sub={`${report.main_questions_count} main + ${report.follow_up_questions_count} follow-up${skipped > 0 ? ` · ${skipped} skipped` : ""}`} />
          <Stat
            label="Performance Score"
            value={scorePct !== null ? `${scorePct}%` : "—"}
            sub={scorePct !== null ? (scorePct >= 70 ? "Strong performance" : scorePct >= 45 ? "Moderate" : "Needs improvement") : "No evaluated answers"}
          />
        </CardContent>
      </Card>

      <Alert>
        <AlertDescription>{report.scoring_methodology}</AlertDescription>
      </Alert>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-primary" /> Answer Classification
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={counts}>
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#94a3b8" }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#94a3b8" }} />
                <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {counts.map((c) => (
                    <Cell key={c.name} fill={CLASS_COLORS[c.name] ?? "#64748b"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {visualData.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Award className="h-4 w-4 text-primary" /> Visual Cue Summary
              </CardTitle>
              <CardDescription>
                AI-estimated cues. Kept separate from knowledge scoring. Not a definitive assessment.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={visualData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={90} label>
                    {visualData.map((_, i) => (
                      <Cell key={i} fill={`hsl(${200 + i * 40} 70% 50%)`} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm text-emerald-400">
              <TrendingUp className="h-4 w-4" /> Strengths
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
              {report.section.strengths.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm text-red-400">
              <TrendingDown className="h-4 w-4" /> Weaknesses
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
              {report.section.weaknesses.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm text-amber-400">
              <Award className="h-4 w-4" /> Recommended Study Areas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
              {report.section.recommended_study_areas.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      {report.section.summary_note && (
        <Alert>
          <AlertDescription>{report.section.summary_note}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Question-by-question Analysis</CardTitle>
        </CardHeader>
        <CardContent className="max-h-[520px] space-y-3 overflow-y-auto scrollbar-thin">
          {report.question_analysis.map((q) => (
            <div key={q.question_number} className="rounded-lg border border-border p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="info">Q{q.question_number}</Badge>
                <span className="flex-1 text-sm font-medium">{q.question}</span>
                <Badge className={classificationColor(q.classification)}>{q.classification}</Badge>
                {q.classification !== "Not Answered" && (
                  <span className="text-xs text-muted-foreground">{Math.round(q.score * 100)}%</span>
                )}
              </div>
              {q.reason && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{q.reason}</p>}
              {q.metrics && q.metrics.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {q.metrics.map((m) => (
                    <Badge key={m.name} variant="muted" title={m.note}>
                      {m.name} {Math.round(m.score * 100)}%
                    </Badge>
                  ))}
                </div>
              )}
              {q.follow_up_answers.length > 0 && (
                <div className="mt-2 space-y-1.5 border-t border-border pt-2">
                  {q.follow_up_answers.map((fu, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <Badge variant="warning">FU{i + 1}</Badge>
                      <span className="flex-1 text-muted-foreground">{fu.text}</span>
                      <Badge className={classificationColor(fu.classification)}>{fu.classification}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
