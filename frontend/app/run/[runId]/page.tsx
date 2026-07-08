"use client";

import { useEffect, useRef, useState } from "react";
import { streamRun } from "../../../lib/api";

const STEPS = ["Parse Resume", "Search Jobs", "Find Recruiters", "Draft Emails", "Review", "Send"];

const STEP_ICONS = [
  // Parse Resume - Document
  <svg key="parse" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
    <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>,
  // Search Jobs
  <svg key="search" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
    <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>,
  // Find Recruiters
  <svg key="recruiters" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
    <path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
  </svg>,
  // Draft Emails
  <svg key="emails" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
    <path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
  </svg>,
  // Review
  <svg key="review" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
    <path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
  </svg>,
  // Send
  <svg key="send" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
    <path d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
  </svg>,
];

function ScoreBadge({ score }: { score: number }) {
  let cls = "bg-white/5 border border-white/[0.08] text-white/40";
  if (score >= 80)      cls = "bg-emerald-400/10 border border-emerald-400/30 text-emerald-300";
  else if (score >= 65) cls = "bg-blue-400/10 border border-blue-400/30 text-blue-300";
  else if (score >= 45) cls = "bg-amber-400/10 border border-amber-400/30 text-amber-300";
  return (
    <span className={`inline-flex items-center rounded-lg px-2 py-0.5 text-xs font-bold tabular-nums ${cls}`}>
      {score}
    </span>
  );
}

function VerdictPill({ verdict }: { verdict: string }) {
  const map: Record<string, string> = {
    "Strong Match":  "bg-emerald-400/10 border-emerald-400/30 text-emerald-300",
    "Good Match":    "bg-blue-400/10 border-blue-400/30 text-blue-300",
    "Partial Match": "bg-amber-400/10 border-amber-400/30 text-amber-300",
    "Weak Match":    "bg-white/5 border-white/[0.08] text-white/40",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${map[verdict] ?? "bg-white/5 border-white/[0.08] text-white/40"}`}>
      {verdict}
    </span>
  );
}

function borderColorForScore(score: number) {
  if (score >= 80) return "border-l-emerald-500";
  if (score >= 65) return "border-l-blue-500";
  if (score >= 45) return "border-l-amber-500";
  return "border-l-red-500/50";
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function JobCard({ job, rank }: { job: any; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const borderColor = borderColorForScore(job.score ?? 0);

  return (
    <div className={`bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-2xl overflow-hidden border-l-4 ${borderColor}`}>
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-white/[0.03] transition-colors"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="text-xs text-white/25 font-mono w-5 shrink-0 tabular-nums">#{rank}</span>
        <ScoreBadge score={job.score ?? 0} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-white text-sm">{job.company}</span>
            <span className="text-white/20 text-xs">·</span>
            {job.apply_link ? (
              <a
                href={job.apply_link}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-indigo-400/80 hover:text-indigo-300 text-sm hover:underline transition-colors"
              >
                {job.title}
              </a>
            ) : (
              <span className="text-white/60 text-sm">{job.title}</span>
            )}
          </div>
          <p className="text-xs text-white/35 mt-0.5">{job.location}</p>
        </div>
        <VerdictPill verdict={job.verdict ?? ""} />
        <svg
          className={`w-4 h-4 text-white/25 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        >
          <path d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {expanded && (
        <div className="border-t border-white/[0.06] px-4 py-4 space-y-4 bg-white/[0.02]">
          {job.recommendation && (
            <p className="text-sm text-white/60 leading-relaxed">{job.recommendation}</p>
          )}
          <div className="grid grid-cols-2 gap-4">
            {job.matched_skills?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-emerald-400/80 mb-2 flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}>
                    <path d="M5 13l4 4L19 7" />
                  </svg>
                  Matched skills
                </p>
                <div className="flex flex-wrap gap-1">
                  {job.matched_skills.map((s: string) => (
                    <span key={s} className="rounded-full bg-emerald-400/10 border border-emerald-400/20 px-2 py-0.5 text-xs text-emerald-300/80">{s}</span>
                  ))}
                </div>
              </div>
            )}
            {job.missing_skills?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-red-400/80 mb-2 flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}>
                    <path d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  Missing skills
                </p>
                <div className="flex flex-wrap gap-1">
                  {job.missing_skills.map((s: string) => (
                    <span key={s} className="rounded-full bg-red-400/10 border border-red-400/20 px-2 py-0.5 text-xs text-red-300/80">{s}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
          {job.breakdown && (
            <div className="space-y-2 pt-1">
              {Object.entries(job.breakdown).map(([key, val]) => (
                <div key={key} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-white/40 capitalize">{key.replace(/_/g, " ")}</span>
                    <span className="text-xs font-semibold text-white/70 tabular-nums">{val as number}</span>
                  </div>
                  <div className="h-1 rounded-full bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all"
                      style={{ width: `${Math.min(100, (val as number))}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function RunPage({ params }: { params: any }) {
  const runId: string = params.runId;

  const [logs, setLogs]               = useState<{ time: string; msg: string }[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [profile, setProfile]         = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [jobs, setJobs]               = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [drafts, setDrafts]           = useState<any[]>([]);
  const [status, setStatus]           = useState<string>("");
  const [error, setError]             = useState<string | null>(null);
  const [logsOpen, setLogsOpen]       = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const pushLog = (msg: string) => {
    const time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    setLogs((prev) => [...prev, { time, msg }]);
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleEvent = (event: any) => {
    const type: string = event.type;
    if (type === "log") {
      pushLog(event.message as string);
    } else if (type === "node_complete") {
      const node: string = event.node;
      if (node === "parse_resume") {
        setProfile(event.profile);
        setCurrentStep(1);
        pushLog("parse_resume complete");
      } else if (node === "search_jobs") {
        setJobs(event.jobs ?? []);
        setCurrentStep(2);
        pushLog(`search_jobs complete — ${(event.jobs ?? []).length} jobs`);
      } else if (node === "find_recruiters") {
        setCurrentStep(3);
        pushLog("find_recruiters complete");
      } else if (node === "draft_emails") {
        setDrafts(event.drafts ?? []);
        setCurrentStep(4);
        pushLog(`draft_emails complete — ${(event.drafts ?? []).length} drafts`);
      }
    } else if (type === "awaiting_review") {
      setDrafts(event.drafts ?? []);
      setStatus("awaiting_review");
      setCurrentStep(4);
      pushLog("Pipeline paused — ready for human review");
    } else if (type === "error") {
      setError(event.message as string);
      pushLog(`ERROR: ${event.message}`);
    } else if (type === "done") {
      setStatus("done");
      setCurrentStep(5);
    }
  };

  useEffect(() => {
    const cleanup = streamRun(runId, handleEvent);
    return cleanup;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  useEffect(() => {
    if (logsOpen) logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, logsOpen]);

  const goToReview = () => {
    sessionStorage.setItem("job_agent_drafts", JSON.stringify(drafts));
    window.location.href = `/run/${runId}/review`;
  };

  return (
    <main className="relative min-h-screen py-10 px-4">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Pipeline</h1>
            <p className="text-xs text-white/25 mt-0.5 font-mono">{runId}</p>
          </div>
          <a href="/" className="text-sm text-indigo-400/80 hover:text-indigo-300 transition-colors flex items-center gap-1.5 bg-white/[0.04] border border-white/[0.08] px-3 py-2 rounded-xl">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
              <path d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            New Run
          </a>
        </div>

        {/* Stepper */}
        <div className="bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-5">
          <div className="flex items-start">
            {STEPS.map((step, idx) => {
              const done   = currentStep > idx;
              const active = currentStep === idx;
              return (
                <div key={step} className="flex items-start flex-1 last:flex-none">
                  <div className="flex flex-col items-center gap-1.5">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                      done   ? "bg-emerald-500/20 border border-emerald-500/40 text-emerald-400" :
                      active ? "bg-indigo-500/20 border border-indigo-400/50 text-indigo-300 ring-4 ring-indigo-500/10 animate-pulse" :
                               "bg-white/[0.04] border border-white/[0.08] text-white/25"
                    }`}>
                      {done ? (
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}>
                          <path d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        STEP_ICONS[idx] ?? <span>{idx + 1}</span>
                      )}
                    </div>
                    <span className={`text-xs font-medium text-center leading-tight max-w-[60px] ${
                      done ? "text-emerald-400/80" : active ? "text-indigo-300" : "text-white/25"
                    }`}>
                      {step}
                    </span>
                  </div>
                  {idx < STEPS.length - 1 && (
                    <div className={`flex-1 h-px mt-4 mx-1.5 transition-colors ${currentStep > idx ? "bg-emerald-500/30" : "bg-white/[0.06]"}`} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Profile card */}
        {profile && (
          <div className="bg-indigo-500/[0.06] backdrop-blur-2xl border border-indigo-500/[0.15] rounded-2xl p-5">
            <p className="text-xs font-semibold text-indigo-400/70 uppercase tracking-widest mb-3">Candidate</p>
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-indigo-500/10 border border-indigo-400/20 flex items-center justify-center text-sm font-bold text-indigo-300">
                {(profile.name as string)?.[0] ?? "?"}
              </div>
              <div>
                <p className="font-bold text-white">{profile.name}</p>
                <p className="text-sm text-white/50">{profile.current_role} · {profile.total_yoe} YOE</p>
              </div>
            </div>
            {profile.skills?.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {(profile.skills as string[]).slice(0, 14).map((s) => (
                  <span key={s} className="rounded-full bg-indigo-400/[0.08] border border-indigo-400/20 px-2.5 py-0.5 text-xs text-indigo-300/80">{s}</span>
                ))}
                {profile.skills.length > 14 && (
                  <span className="text-xs text-white/25 self-center">+{profile.skills.length - 14} more</span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Live Logs */}
        <div className="bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-2xl overflow-hidden">
          <button
            onClick={() => setLogsOpen((p) => !p)}
            className="w-full flex items-center justify-between px-5 py-3 hover:bg-white/[0.03] transition-colors"
          >
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-white/40 uppercase tracking-widest">Live Logs</span>
              <span className="text-xs text-white/20">({logs.length})</span>
            </div>
            <svg className={`w-4 h-4 text-white/25 transition-transform ${logsOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
              <path d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {logsOpen && (
            <div className="h-44 overflow-y-auto font-mono text-xs bg-black/30 border-t border-white/[0.06] p-3 space-y-0.5">
              {logs.length === 0 ? (
                <span className="text-white/20">Waiting for pipeline to start...</span>
              ) : (
                logs.slice(-30).map((entry, i) => (
                  <div key={i} className="flex gap-2 leading-relaxed">
                    <span className="text-white/25 shrink-0 tabular-nums">{entry.time}</span>
                    <span className={
                      entry.msg.startsWith("ERROR")
                        ? "text-red-400/80"
                        : "text-emerald-400/80"
                    }>
                      {entry.msg}
                    </span>
                  </div>
                ))
              )}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>

        {/* Jobs */}
        {jobs.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">
                Jobs Found <span className="text-white/40 font-normal ml-1">({jobs.length})</span>
              </h2>
              <span className="text-xs text-white/25">Click a row to expand details</span>
            </div>
            {jobs.map((job, idx) => (
              <JobCard key={idx} job={job} rank={idx + 1} />
            ))}
          </div>
        )}

        {/* Awaiting Review Banner */}
        {status === "awaiting_review" && (
          <div className="bg-white/[0.04] backdrop-blur-2xl border border-indigo-500/20 rounded-2xl p-6 flex items-center justify-between gap-4">
            <div>
              <p className="font-bold text-white text-lg">
                {drafts.length} email{drafts.length !== 1 ? "s" : ""} ready for review
              </p>
              <p className="text-sm text-indigo-400/70 mt-1">
                Approve, edit, or skip each draft before anything is sent.
              </p>
            </div>
            <button
              onClick={goToReview}
              className="shrink-0 bg-gradient-to-r from-indigo-500 to-violet-500 hover:from-indigo-400 hover:to-violet-400 rounded-xl px-6 py-3 text-sm font-semibold shadow-lg shadow-indigo-500/20 transition-all flex items-center gap-2"
            >
              Review & Approve
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
                <path d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-500/[0.06] border border-red-500/20 rounded-2xl p-5">
            <p className="text-sm font-semibold text-red-400 mb-2">Pipeline Error</p>
            <pre className="text-xs text-red-300/70 whitespace-pre-wrap break-all leading-relaxed">{error}</pre>
          </div>
        )}

        {/* Done with no emails */}
        {status === "done" && drafts.length === 0 && !error && (
          <div className="bg-emerald-500/[0.04] border border-emerald-500/20 rounded-2xl p-6 text-center">
            <div className="w-10 h-10 rounded-full bg-emerald-400/10 border border-emerald-400/30 flex items-center justify-center mx-auto mb-3">
              <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
                <path d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-emerald-400 font-semibold">Pipeline complete.</p>
            <a href="/" className="mt-2 inline-block text-sm text-white/30 hover:text-white transition-colors">
              Start a new run
            </a>
          </div>
        )}
      </div>
    </main>
  );
}
