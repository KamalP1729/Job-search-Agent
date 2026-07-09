"""
main.py — FastAPI backend for the Job Agent UI.
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse

from runner import run_data, run_pipeline_async

app = FastAPI(title="Job Agent API", version="1.0.0")

# CORS — allow the Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth token store — persisted to disk so restarts don't lose the token
_TOKEN_FILE = Path(__file__).parent / ".gmail_tokens.json"

def _load_tokens() -> dict:
    try:
        return json.loads(_TOKEN_FILE.read_text())
    except Exception:
        return {}

def _save_tokens(tokens: dict) -> None:
    try:
        _TOKEN_FILE.write_text(json.dumps(tokens))
    except Exception:
        pass

_gmail_tokens: dict[str, dict] = _load_tokens()


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.post("/api/runs/start")
async def start_run(
    resume: UploadFile = File(...),
    locations: str = Form('["Remote","United States","Bangalore, India"]'),
    top_n: int = Form(10),
    min_score: int = Form(65),
    session_id: str = Form(""),
):
    """
    Accept resume upload + parameters, launch the pipeline, return a run_id.
    """
    run_id = str(uuid.uuid4())

    try:
        locations_list: list[str] = json.loads(locations)
    except (json.JSONDecodeError, ValueError):
        locations_list = ["Remote", "United States", "Bangalore, India"]

    resume_bytes = await resume.read()
    resume_name = resume.filename or "resume.pdf"

    # Initialize run state
    run_data[run_id] = {
        "status": "running",
        "session_id": session_id,
        "queue": None,
        "graph_obj": None,
        "graph_config": None,
        "state": {},
    }

    # Launch pipeline as a background async task
    asyncio.create_task(
        run_pipeline_async(
            run_id=run_id,
            resume_bytes=resume_bytes,
            resume_name=resume_name,
            locations=locations_list,
            top_n=top_n,
            min_score=min_score,
        )
    )

    return {"run_id": run_id}


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """
    SSE endpoint — yields events from the pipeline queue until done/error.
    """
    if run_id not in run_data:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        # Wait briefly for queue to be initialized by the background task
        for _ in range(50):
            if run_data[run_id].get("queue") is not None:
                break
            await asyncio.sleep(0.1)

        queue: asyncio.Queue = run_data[run_id].get("queue")
        if queue is None:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Queue not initialized'})}\n\n"
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                # Send a keepalive ping
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/runs/{run_id}/state")
async def get_run_state(run_id: str):
    """
    Return the current state dict for a run.
    """
    if run_id not in run_data:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_data[run_id].get("state", {})


@app.post("/api/runs/{run_id}/send")
async def send_approved(run_id: str, request: Request):
    """
    Send approved email drafts. Accepts JSON body:
    {"approved_indices": [0, 1, ...], "session_id": "...", "drafts": [...]}
    """
    if run_id not in run_data:
        raise HTTPException(status_code=404, detail="Run not found")

    body = await request.json()
    approved_indices: list[int] = body.get("approved_indices", [])
    session_id: str = body.get("session_id", "")
    # Frontend may send updated drafts (with subject/body edits)
    client_drafts: list[dict] = body.get("drafts", [])

    run_state = run_data[run_id]
    state = run_state.get("state", {})

    # Use client-provided drafts if available, else fall back to stored drafts
    all_drafts = client_drafts if client_drafts else state.get("email_drafts", [])

    if not all_drafts:
        raise HTTPException(status_code=400, detail="No email drafts found")

    # Filter to approved indices
    approved_drafts = [all_drafts[i] for i in approved_indices if 0 <= i < len(all_drafts)]

    if not approved_drafts:
        return {"sent": 0}

    # Try OAuth first, then SMTP fallback
    token_info = _gmail_tokens.get(session_id)
    sent_count = 0
    errors = []

    if token_info:
        from gmail_oauth import send_via_oauth
        for draft in approved_drafts:
            try:
                send_via_oauth(token_info, draft)
                sent_count += 1
            except Exception as e:
                errors.append(str(e))
    else:
        # SMTP fallback via email_agent.send_email
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from email_agent import send_email
        for draft in approved_drafts:
            try:
                send_email(draft)
                sent_count += 1
            except Exception as e:
                errors.append(str(e))

    if errors and sent_count == 0:
        raise HTTPException(status_code=500, detail=f"All sends failed: {errors[0]}")

    return {"sent": sent_count, "errors": errors}


@app.post("/api/runs/{run_id}/redraft")
async def redraft_emails(run_id: str):
    """
    Re-run email drafting using stored jobs + recruiters from a previous run.
    Skips job search and scoring entirely — only re-calls draft_outreach().
    """
    if run_id not in run_data:
        raise HTTPException(status_code=404, detail="Run not found")

    state = run_data[run_id].get("state", {})
    profile    = state.get("profile", {})
    jobs       = state.get("jobs", [])
    recruiters = state.get("recruiters", [])

    if not jobs:
        raise HTTPException(status_code=400, detail="No jobs in stored state — run the pipeline first")

    contact_map = {r["company"]: r["contacts"] for r in recruiters}

    from email_agent import draft_outreach
    drafts = []
    errors = []
    for job in jobs:
        contacts = contact_map.get(job["company"], [])
        if not contacts:
            continue
        contact = contacts[0]
        try:
            draft = await asyncio.to_thread(draft_outreach, profile, job, contact)
            drafts.append(draft)
        except Exception as e:
            errors.append(f"{job['company']}: {e}")

    # Store updated drafts back into state
    run_data[run_id]["state"]["email_drafts"] = drafts

    return {"drafts": drafts, "errors": errors}


@app.get("/api/auth/gmail")
async def gmail_auth(session_id: str = ""):
    """
    Redirect to Google OAuth authorization URL.
    """
    try:
        from auth import get_gmail_auth_url
        auth_url = get_gmail_auth_url(session_id)
        return RedirectResponse(url=auth_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/auth/gmail/callback")
async def gmail_callback(code: str = "", state: str = "", error: str = ""):
    """
    Handle OAuth callback, exchange code for token, store it.
    """
    if error:
        return RedirectResponse(url=f"http://localhost:3000?gmail=error&session={state}")

    try:
        from auth import exchange_gmail_code
        token_info = exchange_gmail_code(code=code, state=state)
        _gmail_tokens[state] = token_info
        _save_tokens(_gmail_tokens)
        return RedirectResponse(
            url=f"http://localhost:3000?gmail=connected&session={state}"
        )
    except Exception as e:
        return RedirectResponse(
            url=f"http://localhost:3000?gmail=error&session={state}&msg={str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
