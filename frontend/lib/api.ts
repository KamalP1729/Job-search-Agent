const BASE = "http://localhost:8000";

export async function startRun(
  formData: FormData
): Promise<{ run_id: string }> {
  const res = await fetch(`${BASE}/api/runs/start`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function streamRun(runId: string, onEvent: (event: any) => void): () => void {
  const es = new EventSource(`${BASE}/api/runs/${runId}/stream`);
  es.onmessage = (e) => onEvent(JSON.parse(e.data));
  es.onerror = () => es.close();
  return () => es.close();
}

export async function sendApproved(
  runId: string,
  approvedIndices: number[],
  sessionId: string,
  drafts?: object[]
): Promise<{ sent: number }> {
  const res = await fetch(`${BASE}/api/runs/${runId}/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      approved_indices: approvedIndices,
      session_id: sessionId,
      drafts: drafts ?? [],
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function getGmailAuthUrl(sessionId: string): string {
  return `${BASE}/api/auth/gmail?session_id=${sessionId}`;
}
