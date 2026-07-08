"""
runner.py — Async pipeline runner for the Job Agent backend.
Bridges the sync LangGraph pipeline with asyncio/SSE streaming.
"""

import sys
import asyncio
import tempfile
import os
from pathlib import Path

# Ensure the parent directory (job_agent root) is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Module-level store: run_id -> run state dict
run_data: dict[str, dict] = {}


async def run_pipeline_async(
    run_id: str,
    resume_bytes: bytes,
    resume_name: str,
    locations: list[str],
    top_n: int,
    min_score: int,
) -> None:
    """
    Async wrapper around the sync LangGraph pipeline.
    Pushes SSE-style events to a per-run asyncio.Queue.
    """
    queue: asyncio.Queue = asyncio.Queue()
    run_data[run_id]["queue"] = queue

    # Determine file suffix from resume name
    suffix = ".pdf"
    if resume_name.lower().endswith(".docx"):
        suffix = ".docx"

    # Write resume bytes to a temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(resume_bytes)
        tmp.flush()
        tmp.close()
        resume_path = tmp.name

        # Get the current event loop for thread-safe queue puts
        loop = asyncio.get_event_loop()

        def push(event: dict) -> None:
            """Thread-safe event push from sync thread to async queue."""
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def run_sync() -> None:
            """The blocking sync pipeline — runs in a thread pool."""
            try:
                from graph import build_graph

                push({"type": "log", "message": "Building pipeline graph..."})

                graph = build_graph()
                config = {"configurable": {"thread_id": run_id}}

                initial_state = {
                    "resume_path":     resume_path,
                    "locations":       locations,
                    "top_n":           top_n,
                    "min_score":       min_score,
                    "profile":         {},
                    "jobs":            [],
                    "recruiters":      [],
                    "email_drafts":    [],
                    "approved_emails": [],
                    "sent_emails":     [],
                    "errors":          [],
                    "status":          "starting",
                }

                push({"type": "log", "message": "Starting pipeline..."})

                # Stream graph execution until breakpoint
                prev_status = None
                for chunk in graph.stream(initial_state, config, stream_mode="values"):
                    status = chunk.get("status", "")

                    if status != prev_status:
                        prev_status = status

                        if status == "resume_parsed":
                            profile = chunk.get("profile", {})
                            push({
                                "type": "log",
                                "message": f"Resume parsed: {profile.get('name', 'Unknown')} | {profile.get('current_role', '')} | {profile.get('total_yoe', 0)} YOE",
                            })
                            push({
                                "type": "node_complete",
                                "node": "parse_resume",
                                "profile": profile,
                            })

                        elif status == "jobs_found":
                            jobs = chunk.get("jobs", [])
                            push({
                                "type": "log",
                                "message": f"Found {len(jobs)} jobs above threshold",
                            })
                            push({
                                "type": "node_complete",
                                "node": "search_jobs",
                                "jobs": jobs,
                            })

                        elif status == "recruiters_found":
                            recruiters = chunk.get("recruiters", [])
                            push({
                                "type": "log",
                                "message": f"Found contacts for {len(recruiters)} companies",
                            })
                            push({
                                "type": "node_complete",
                                "node": "find_recruiters",
                                "recruiters": recruiters,
                            })

                        elif status == "emails_drafted":
                            drafts = chunk.get("email_drafts", [])
                            push({
                                "type": "log",
                                "message": f"Drafted {len(drafts)} emails",
                            })
                            push({
                                "type": "node_complete",
                                "node": "draft_emails",
                                "drafts": drafts,
                            })

                        elif status == "failed":
                            errors = chunk.get("errors", [])
                            err_msg = errors[-1] if errors else "Pipeline failed"
                            push({"type": "error", "message": err_msg})
                            return

                # Check if we hit the human_review breakpoint
                state = graph.get_state(config)
                if state.next == ("human_review",):
                    drafts = state.values.get("email_drafts", [])
                    push({
                        "type": "log",
                        "message": f"Pipeline paused for human review — {len(drafts)} email drafts ready",
                    })
                    push({"type": "awaiting_review", "drafts": drafts})

                    # Store graph objects for the send endpoint
                    run_data[run_id]["graph_obj"] = graph
                    run_data[run_id]["graph_config"] = config
                    run_data[run_id]["state"] = state.values
                else:
                    # Pipeline completed without breakpoint (e.g. no drafts)
                    final = graph.get_state(config).values
                    run_data[run_id]["state"] = final
                    push({"type": "done"})

            except Exception as exc:
                import traceback
                tb = traceback.format_exc()
                push({"type": "error", "message": f"{exc}\n{tb}"})

        # Run sync pipeline in thread pool; push done when finished
        await asyncio.to_thread(run_sync)
        # Signal stream end (only if no error already pushed a done/error)
        queue.put_nowait({"type": "done"})

    finally:
        # Clean up temp resume file
        try:
            os.unlink(resume_path)
        except Exception:
            pass
