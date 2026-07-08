"use client";

import { useEffect, useRef, useState } from "react";
import { startRun, getGmailAuthUrl } from "../lib/api";

const DEFAULT_LOCATIONS = ["Remote", "United States", "Bangalore, India"];

const PIPELINE_STEPS = [
  {
    label: "Parse resume",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    label: "Search jobs",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
        <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    ),
  },
  {
    label: "Score & rank",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
        <path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    label: "Find recruiters",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
        <path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    label: "Draft emails",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
        <path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    label: "You approve",
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
        <path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  },
];

export default function HomePage() {
  const [file, setFile]                     = useState<File | null>(null);
  const [isDragging, setIsDragging]         = useState(false);
  const [locations, setLocations]           = useState<string[]>([...DEFAULT_LOCATIONS]);
  const [topN, setTopN]                     = useState(10);
  const [minScore, setMinScore]             = useState(65);
  const [loading, setLoading]               = useState(false);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [sessionId, setSessionId]           = useState("");
  const [customLocation, setCustomLocation] = useState("");
  const [error, setError]                   = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("gmail") === "connected") {
      setGmailConnected(true);
      window.history.replaceState({}, "", "/");
    }
    let sid = localStorage.getItem("job_agent_session_id");
    if (!sid) {
      sid = crypto.randomUUID();
      localStorage.setItem("job_agent_session_id", sid);
    }
    setSessionId(sid);
  }, []);

  const handleFileSelect = (f: File) => {
    if (f && (f.name.endsWith(".pdf") || f.name.endsWith(".docx"))) {
      setFile(f);
      setError(null);
    } else {
      setError("Please upload a PDF or DOCX file.");
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  };

  const toggleLocation = (loc: string) =>
    setLocations((prev) =>
      prev.includes(loc) ? prev.filter((l) => l !== loc) : [...prev, loc]
    );

  const addCustomLocation = () => {
    const trimmed = customLocation.trim();
    if (trimmed && !locations.includes(trimmed)) setLocations((prev) => [...prev, trimmed]);
    setCustomLocation("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) { setError("Please upload your resume first."); return; }
    if (locations.length === 0) { setError("Select at least one location."); return; }
    setLoading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("resume", file);
      fd.append("locations", JSON.stringify(locations));
      fd.append("top_n", String(topN));
      fd.append("min_score", String(minScore));
      fd.append("session_id", sessionId);
      const { run_id } = await startRun(fd);
      window.location.href = `/run/${run_id}`;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start run.");
      setLoading(false);
    }
  };

  const fileSizeLabel = file
    ? file.size > 1_000_000
      ? `${(file.size / 1_000_000).toFixed(1)} MB`
      : `${Math.round(file.size / 1024)} KB`
    : null;

  return (
    <main className="relative min-h-screen py-16 px-4">
      <div className="max-w-xl mx-auto space-y-6">

        {/* Hero */}
        <div className="text-center space-y-4 mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white/[0.06] border border-white/[0.10] backdrop-blur-xl mb-2 shadow-xl shadow-black/20">
            <svg className="w-8 h-8 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
              <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
            </svg>
          </div>
          <h1 className="text-5xl font-bold tracking-tight bg-gradient-to-b from-white to-white/60 bg-clip-text text-transparent">
            Job Agent
          </h1>
          <p className="text-white/50 text-base leading-relaxed max-w-sm mx-auto">
            Upload your resume. Find jobs, score them, locate recruiters, draft cold emails — you approve before anything sends.
          </p>
        </div>

        {/* Pipeline steps */}
        <div className="bg-white/[0.03] backdrop-blur-2xl border border-white/[0.06] rounded-2xl p-5">
          <p className="text-xs font-semibold text-white/30 uppercase tracking-widest mb-4">How it works</p>
          <div className="flex items-center justify-between">
            {PIPELINE_STEPS.map((step, i) => (
              <div key={i} className="flex items-center">
                <div className="flex flex-col items-center gap-2">
                  <div className="w-9 h-9 rounded-xl bg-white/[0.05] border border-white/[0.08] flex items-center justify-center text-white/50">
                    {step.icon}
                  </div>
                  <span className="text-[10px] text-white/35 leading-tight text-center max-w-[52px]">{step.label}</span>
                </div>
                {i < PIPELINE_STEPS.length - 1 && (
                  <svg className="w-3 h-3 text-white/20 mx-1 mb-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
                    <path d="M9 5l7 7-7 7" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">

          {/* Gmail card */}
          <div className="bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-5">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-white">Gmail</h2>
                <p className="text-xs text-white/40 mt-0.5 leading-relaxed">
                  {gmailConnected
                    ? "Connected via OAuth — emails will be sent on your behalf."
                    : "Connect to send via OAuth, or set GMAIL_USER env var as fallback."}
                </p>
              </div>
              {gmailConnected ? (
                <div className="flex items-center gap-1.5 text-emerald-400 text-sm font-medium shrink-0">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}>
                    <path d="M5 13l4 4L19 7" />
                  </svg>
                  Connected
                </div>
              ) : (
                <a
                  href={sessionId ? getGmailAuthUrl(sessionId) : "#"}
                  className="shrink-0 inline-flex items-center gap-2 bg-white/[0.06] border border-white/[0.10] hover:bg-white/[0.10] rounded-xl px-4 py-2 text-sm font-medium transition-all"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                  </svg>
                  <span className="text-white/80">Connect Gmail</span>
                </a>
              )}
            </div>
          </div>

          {/* Resume upload */}
          <div className="bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-white mb-3">Resume</h2>
            <div
              className={`relative rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-all ${
                isDragging
                  ? "border-indigo-400/40 bg-indigo-500/[0.06] scale-[1.01]"
                  : file
                  ? "border-emerald-500/40 bg-emerald-500/[0.04]"
                  : "border-white/[0.12] hover:border-white/[0.20] hover:bg-white/[0.02]"
              }`}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }}
              />
              {file ? (
                <div className="flex flex-col items-center gap-2">
                  <div className="w-10 h-10 rounded-xl bg-emerald-400/10 border border-emerald-400/30 flex items-center justify-center">
                    <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
                      <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <p className="font-semibold text-emerald-300">{file.name}</p>
                  <p className="text-xs text-white/40">{fileSizeLabel} · Click to replace</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <div className="w-10 h-10 rounded-xl bg-white/[0.05] border border-white/[0.10] flex items-center justify-center">
                    <svg className="w-5 h-5 text-white/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
                      <path d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <p className="font-medium text-white/70">Drop your resume here</p>
                  <p className="text-sm text-white/35">or click to browse · PDF or DOCX</p>
                </div>
              )}
            </div>
          </div>

          {/* Locations */}
          <div className="bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-white mb-3">Target Locations</h2>
            <div className="flex flex-wrap gap-2 mb-3">
              {[...DEFAULT_LOCATIONS, ...locations.filter((l) => !DEFAULT_LOCATIONS.includes(l))].map((loc) => {
                const selected = locations.includes(loc);
                return (
                  <button
                    key={loc}
                    type="button"
                    onClick={() => toggleLocation(loc)}
                    className={`rounded-full px-3 py-1.5 text-sm font-medium border transition-all flex items-center gap-1.5 ${
                      selected
                        ? "bg-indigo-500/20 border-indigo-400/50 text-indigo-300"
                        : "bg-white/[0.04] border-white/[0.08] text-white/50 hover:border-white/20"
                    }`}
                  >
                    {selected && (
                      <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}>
                        <path d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                    {loc}
                  </button>
                );
              })}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={customLocation}
                onChange={(e) => setCustomLocation(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCustomLocation())}
                placeholder="Add custom location..."
                className="flex-1 bg-white/[0.05] border border-white/[0.10] rounded-xl focus:border-indigo-400/60 focus:outline-none focus:bg-white/[0.07] transition-all px-3 py-2 text-sm text-white placeholder-white/25"
              />
              <button
                type="button"
                onClick={addCustomLocation}
                className="bg-white/[0.06] border border-white/[0.10] hover:bg-white/[0.10] rounded-xl px-4 py-2 text-sm text-white/70 transition-all"
              >
                Add
              </button>
            </div>
          </div>

          {/* Settings */}
          <div className="bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-5 grid grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-semibold text-white mb-2">Top N Jobs</label>
              <input
                type="number"
                min={5}
                max={20}
                value={topN}
                onChange={(e) => setTopN(parseInt(e.target.value, 10) || 10)}
                className="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl focus:border-indigo-400/60 focus:outline-none focus:bg-white/[0.07] transition-all px-3 py-2 text-white"
              />
              <p className="mt-1.5 text-xs text-white/30">5 – 20 jobs</p>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-semibold text-white">Min Score</label>
                <span className="text-sm font-bold text-indigo-400 tabular-nums">{minScore}</span>
              </div>
              <input
                type="range"
                min={50}
                max={85}
                value={minScore}
                onChange={(e) => setMinScore(parseInt(e.target.value, 10))}
                className="w-full accent-indigo-500"
              />
              <div className="flex justify-between text-xs text-white/25 mt-1">
                <span>50 · More</span>
                <span>85 · Stricter</span>
              </div>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300 flex items-center gap-2">
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}>
                <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              {error}
            </div>
          )}

          {/* Submit button */}
          <button
            type="submit"
            disabled={loading || !file}
            className="w-full bg-gradient-to-r from-indigo-500 to-violet-500 hover:from-indigo-400 hover:to-violet-400 disabled:opacity-40 disabled:cursor-not-allowed py-4 rounded-2xl text-base font-semibold shadow-lg shadow-indigo-500/20 transition-all"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Starting pipeline...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                Run Job Agent
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
                  <path d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </span>
            )}
          </button>
        </form>
      </div>
    </main>
  );
}
