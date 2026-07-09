"use client";

import { use, useEffect, useState } from "react";
import { sendApproved } from "../../../../lib/api";

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

function WordCount({ body }: { body: string }) {
  const count = body.trim() ? body.trim().split(/\s+/).length : 0;
  const color =
    count > 100 ? "text-red-400" :
    count >= 80  ? "text-amber-300" :
                   "text-white/40";
  return (
    <span className={`text-xs font-medium tabular-nums ${color} inline-flex items-center gap-1`}>
      {count} words
      {count > 100 && (
        <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
          <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      )}
    </span>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function ReviewPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [drafts, setDrafts]       = useState<any[]>([]);
  const [approved, setApproved]   = useState<Set<number>>(new Set());
  const [subjects, setSubjects]   = useState<string[]>([]);
  const [bodies, setBodies]       = useState<string[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [sending, setSending]       = useState(false);
  const [redrafting, setRedrafting] = useState(false);
  const [result, setResult]         = useState<string | null>(null);
  const [sendError, setSendError]   = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("job_agent_drafts");
      if (raw) {
        const parsed = JSON.parse(raw);
        setDrafts(parsed);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        setSubjects(parsed.map((d: any) => d.subject ?? ""));
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        setBodies(parsed.map((d: any) => d.body ?? ""));
      }
    } catch { /* ignore */ }
    setSessionId(localStorage.getItem("job_agent_session_id") ?? "");
  }, []);

  const toggleApproval = (idx: number) =>
    setApproved((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });

  const approveAll = () =>
    setApproved(new Set(drafts.map((_, i) => i)));

  const clearAll = () =>
    setApproved(new Set());

  const updateSubject = (idx: number, val: string) =>
    setSubjects((prev) => { const n = [...prev]; n[idx] = val; return n; });

  const updateBody = (idx: number, val: string) =>
    setBodies((prev) => { const n = [...prev]; n[idx] = val; return n; });

  const handleRedraft = async () => {
    setRedrafting(true);
    setSendError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/runs/${runId}/redraft`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data: any = await res.json();
      const newDrafts = data.drafts ?? [];
      setDrafts(newDrafts);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      setSubjects(newDrafts.map((d: any) => d.subject ?? ""));
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      setBodies(newDrafts.map((d: any) => d.body ?? ""));
      setApproved(new Set());
      sessionStorage.setItem("job_agent_drafts", JSON.stringify(newDrafts));
    } catch (err: unknown) {
      setSendError(err instanceof Error ? err.message : "Re-draft failed.");
    } finally {
      setRedrafting(false);
    }
  };

  const handleSend = async () => {
    if (approved.size === 0) return;
    setSending(true);
    setSendError(null);
    const updatedDrafts = drafts.map((d, i) => ({
      ...d,
      subject: subjects[i] ?? d.subject,
      body:    bodies[i]   ?? d.body,
    }));
    try {
      const { sent } = await sendApproved(runId, [...approved], sessionId, updatedDrafts);
      setResult(`${sent} email${sent !== 1 ? "s" : ""} sent successfully.`);
    } catch (err: unknown) {
      setSendError(err instanceof Error ? err.message : "Send failed.");
    } finally {
      setSending(false);
    }
  };

  if (drafts.length === 0) {
    return (
      <main className="relative min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mx-auto">
            <svg className="w-7 h-7 text-white/25" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
              <path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <p className="text-lg font-medium text-white/60">No drafts found.</p>
          <a href="/" className="inline-block text-sm text-indigo-400/80 hover:text-indigo-300 transition-colors">
            Start a new run
          </a>
        </div>
      </main>
    );
  }

  const warningCount = drafts.filter((d) => d.guardrail_warnings?.length > 0).length;

  return (
    <main className="relative min-h-screen py-10 px-4 pb-32">
      <div className="max-w-3xl mx-auto space-y-5">

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Review Emails</h1>
            <p className="text-sm text-white/40 mt-1">
              {approved.size} of {drafts.length} approved
              {warningCount > 0 && (
                <span className="ml-2 text-amber-300/80">· {warningCount} with warnings</span>
              )}
            </p>
          </div>
          <a href={`/run/${runId}`} className="text-sm text-indigo-400/80 hover:text-indigo-300 transition-colors flex items-center gap-1.5 bg-white/[0.04] border border-white/[0.08] px-3 py-2 rounded-xl shrink-0">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
              <path d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back to pipeline
          </a>
        </div>

        {/* Bulk actions */}
        {!result && (
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={approveAll}
              className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06] hover:bg-emerald-500/[0.10] px-4 py-2 text-sm text-emerald-400 font-medium transition-all flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}>
                <path d="M5 13l4 4L19 7" />
              </svg>
              Approve all ({drafts.length})
            </button>
            <button
              onClick={clearAll}
              className="bg-white/[0.06] border border-white/[0.10] hover:bg-white/[0.10] rounded-xl px-4 py-2 text-sm text-white/50 font-medium transition-all"
            >
              Clear all
            </button>
            <button
              onClick={handleRedraft}
              disabled={redrafting}
              className="ml-auto rounded-xl border border-indigo-500/20 bg-indigo-500/[0.06] hover:bg-indigo-500/[0.10] disabled:opacity-40 disabled:cursor-not-allowed px-4 py-2 text-sm text-indigo-400 font-medium transition-all flex items-center gap-1.5"
            >
              {redrafting ? (
                <>
                  <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Re-drafting...
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
                    <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Re-draft emails
                </>
              )}
            </button>
          </div>
        )}

        {/* Success */}
        {result && (
          <div className="bg-emerald-500/[0.04] border border-emerald-500/30 rounded-2xl p-6 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-emerald-400/10 border border-emerald-400/30 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
                <path d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-emerald-300 font-bold text-lg">{result}</p>
            <a href={`/run/${runId}`} className="inline-block text-sm text-white/30 hover:text-white transition-colors">
              Back to results
            </a>
          </div>
        )}

        {/* Send error */}
        {sendError && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300 flex items-start gap-2">
            <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
              <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {sendError}
          </div>
        )}

        {/* Draft cards */}
        {!result && drafts.map((draft, idx) => {
          const isApproved = approved.has(idx);
          const warnings: string[] = draft.guardrail_warnings ?? [];

          return (
            <div
              key={idx}
              className={`backdrop-blur-2xl rounded-2xl border overflow-hidden transition-all ${
                isApproved
                  ? "bg-emerald-500/[0.04] border-emerald-500/30"
                  : "bg-white/[0.04] border-white/[0.08]"
              }`}
            >
              {/* Card header */}
              <div className="flex items-start justify-between gap-4 px-5 pt-4 pb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-white">{draft.company}</span>
                    <span className="text-white/20 text-sm">·</span>
                    <span className="text-white/60 text-sm">{draft.job_title}</span>
                    <ScoreBadge score={draft.score ?? 0} />
                  </div>
                  <p className="text-xs text-white/35 mt-0.5 flex items-center gap-1">
                    <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
                      <path d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                    {draft.to_name} · {draft.to_email}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => toggleApproval(idx)}
                    className={`rounded-xl px-3 py-1.5 text-xs font-semibold border transition-all flex items-center gap-1 ${
                      isApproved
                        ? "bg-emerald-500/20 border-emerald-400/40 text-emerald-300"
                        : "bg-white/[0.04] border-white/[0.08] text-white/50 hover:border-emerald-500/30 hover:text-emerald-400"
                    }`}
                  >
                    {isApproved && (
                      <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}>
                        <path d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                    {isApproved ? "Approved" : "Approve"}
                  </button>
                  {isApproved && (
                    <button
                      onClick={() => toggleApproval(idx)}
                      className="bg-white/[0.06] border border-white/[0.10] hover:bg-white/[0.10] rounded-xl px-3 py-1.5 text-xs font-semibold text-white/40 transition-all"
                    >
                      Skip
                    </button>
                  )}
                </div>
              </div>

              {/* Guardrail warnings */}
              {warnings.length > 0 && (
                <div className="mx-5 mb-3 bg-amber-500/[0.06] border border-amber-500/20 rounded-xl px-3 py-2.5">
                  <p className="text-xs font-semibold text-amber-300/80 mb-1 flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
                      <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    Guardrail warnings
                  </p>
                  <ul className="space-y-0.5">
                    {warnings.map((w, wi) => (
                      <li key={wi} className="text-xs text-amber-300/60">· {w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Editable fields */}
              <div className="px-5 pb-5 space-y-3">
                <div>
                  <label className="block text-xs font-medium text-white/35 mb-1.5">Subject</label>
                  <input
                    type="text"
                    value={subjects[idx] ?? ""}
                    onChange={(e) => updateSubject(idx, e.target.value)}
                    className="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl focus:border-indigo-400/60 focus:outline-none focus:bg-white/[0.07] transition-all px-3 py-2 text-sm text-white/80"
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-medium text-white/35">Body</label>
                    <WordCount body={bodies[idx] ?? ""} />
                  </div>
                  <textarea
                    rows={6}
                    value={bodies[idx] ?? ""}
                    onChange={(e) => updateBody(idx, e.target.value)}
                    className="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl focus:border-indigo-400/60 focus:outline-none focus:bg-white/[0.07] transition-all px-3 py-2 text-sm text-white/70 resize-y font-mono leading-relaxed"
                  />
                </div>
                {draft.apply_link && (
                  <a
                    href={draft.apply_link}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-indigo-400/70 hover:text-indigo-300 transition-colors"
                  >
                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
                      <path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                    View job posting
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Sticky send bar */}
      {!result && (
        <div className="fixed bottom-0 left-0 right-0 bg-[#030712]/80 backdrop-blur-2xl border-t border-white/[0.08] px-4 py-4">
          <div className="max-w-3xl mx-auto flex items-center justify-between gap-4">
            <p className="text-sm text-white/50">
              {approved.size > 0 ? (
                <>
                  <span className="text-white font-semibold">{approved.size}</span>
                  {" "}email{approved.size !== 1 ? "s" : ""} selected
                </>
              ) : (
                <span className="text-white/25">No emails selected — approve at least one</span>
              )}
            </p>
            <button
              onClick={handleSend}
              disabled={approved.size === 0 || sending}
              className="bg-gradient-to-r from-indigo-500 to-violet-500 hover:from-indigo-400 hover:to-violet-400 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl px-6 py-3 text-sm font-semibold shadow-lg shadow-indigo-500/20 transition-all min-w-[180px] text-center"
            >
              {sending ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Sending...
                </span>
              ) : (
                `Send ${approved.size > 0 ? approved.size : ""} Email${approved.size !== 1 ? "s" : ""}`
              )}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
