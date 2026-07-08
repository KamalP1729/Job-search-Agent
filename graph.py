"""
graph.py — LangGraph multi-agent orchestration for the job search pipeline.

Graph flow:
  parse_resume → search_jobs → score_jobs → find_recruiters → draft_emails → human_review → send_emails

State is passed between nodes via JobAgentState (TypedDict).
human_review is a breakpoint — execution pauses for approval before sending.
"""

import json
import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver


# ── STATE ─────────────────────────────────────────────────────────────────────

class JobAgentState(TypedDict):
    # Inputs
    resume_path:    str
    locations:      list[str]
    top_n:          int
    min_score:      int

    # Populated by nodes
    profile:        dict                        # parsed resume profile
    jobs:           list[dict]                  # scored + ranked jobs
    recruiters:     list[dict]                  # contacts per company
    email_drafts:   list[dict]                  # drafted emails awaiting approval
    approved_emails: list[dict]                 # emails approved by human
    sent_emails:    list[dict]                  # successfully sent emails

    # Control
    errors:         Annotated[list[str], operator.add]  # accumulates errors
    status:         str                         # current pipeline status


# ── NODE: parse_resume ─────────────────────────────────────────────────────────

def node_parse_resume(state: JobAgentState) -> dict:
    print("\n[1/6] ParseResumeAgent — parsing resume...")
    from parser import parse_resume

    try:
        profile = parse_resume(state["resume_path"])
        print(f"  ✓ {profile['name']} | {profile['current_role']} | {profile['total_yoe']} YOE")
        return {"profile": profile, "status": "resume_parsed"}
    except Exception as e:
        return {"errors": [f"ParseResumeAgent: {e}"], "status": "failed"}


# ── NODE: search_jobs ─────────────────────────────────────────────────────────

def node_search_jobs(state: JobAgentState) -> dict:
    print("\n[2/6] JobSearchAgent — searching and scoring jobs (semantic + LLM hybrid)...")
    from semantic_job_search import search_and_rank_semantic

    try:
        jobs = search_and_rank_semantic(
            profile=state["profile"],
            locations=state.get("locations"),
            top_n=state.get("top_n", 10),
            min_score=state.get("min_score", 60),
        )
        print(f"  ✓ Found {len(jobs)} jobs above threshold")
        return {"jobs": jobs, "status": "jobs_found"}
    except Exception as e:
        return {"errors": [f"JobSearchAgent: {e}"], "status": "failed"}


# ── NODE: find_recruiters ──────────────────────────────────────────────────────

def node_find_recruiters(state: JobAgentState) -> dict:
    print("\n[3/6] RecruiterFinderAgent — finding contacts...")
    from recruiter_finder import find_contacts

    jobs      = state.get("jobs", [])
    companies = list({j["company"] for j in jobs})  # deduplicated
    recruiters = []

    for company in companies:
        print(f"  Searching: {company} ...", end=" ", flush=True)
        try:
            result = find_contacts(company)
            contacts = result.get("contacts", [])
            if contacts:
                recruiters.append({
                    "company":  company,
                    "contacts": contacts,
                    "pattern":  result.get("email_pattern"),
                })
                print(f"{len(contacts)} found")
            else:
                print("none found")
        except Exception as e:
            print(f"error: {e}")

    print(f"  ✓ Found contacts for {len(recruiters)}/{len(companies)} companies")
    return {"recruiters": recruiters, "status": "recruiters_found"}


# ── NODE: draft_emails ────────────────────────────────────────────────────────

def node_draft_emails(state: JobAgentState) -> dict:
    print("\n[4/6] EmailDraftAgent — drafting outreach emails...")
    from email_agent import draft_outreach

    profile    = state["profile"]
    jobs       = state.get("jobs", [])
    recruiters = state.get("recruiters", [])

    # Build a lookup: company → contacts
    contact_map = {r["company"]: r["contacts"] for r in recruiters}

    drafts = []
    for job in jobs:
        company  = job["company"]
        contacts = contact_map.get(company, [])
        if not contacts:
            continue

        # Draft one email per job, targeting the top contact
        contact = contacts[0]
        try:
            draft = draft_outreach(profile=profile, job=job, contact=contact)
            drafts.append(draft)
            print(f"  ✓ Drafted email → {contact['name']} at {company}")
        except Exception as e:
            print(f"  ✗ {company}: {e}")

    print(f"  ✓ {len(drafts)} emails drafted")
    return {"email_drafts": drafts, "status": "emails_drafted"}


# ── NODE: human_review ────────────────────────────────────────────────────────
# This is a BREAKPOINT node — the graph pauses here for human approval.
# Resume with: graph.invoke(state, config, command=Command(resume=approved_emails))

def node_human_review(state: JobAgentState) -> dict:
    """
    Pause for human approval. Prints all drafts and waits.
    In CLI mode, prompts the user to approve/reject each email.
    """
    print("\n[5/6] HumanReviewAgent — review email drafts before sending\n")
    drafts   = state.get("email_drafts", [])
    approved = []

    for i, draft in enumerate(drafts, 1):
        print(f"{'─'*60}")
        print(f"Email {i}/{len(drafts)}")
        print(f"To:      {draft['to_name']} <{draft['to_email']}>")
        print(f"Company: {draft['company']}")
        print(f"Role:    {draft['job_title']}")
        print(f"\nSubject: {draft['subject']}\n")
        print(draft['body'])
        print()

        choice = input("Send this email? [y/n/e(dit)]: ").strip().lower()
        if choice == "y":
            approved.append(draft)
            print("  ✓ Approved")
        elif choice == "e":
            new_body = input("Paste edited body (single line, use \\n for newlines): ")
            draft["body"] = new_body.replace("\\n", "\n")
            approved.append(draft)
            print("  ✓ Approved with edits")
        else:
            print("  ✗ Skipped")

    print(f"\n  {len(approved)}/{len(drafts)} emails approved")
    return {"approved_emails": approved, "status": "reviewed"}


# ── NODE: send_emails ─────────────────────────────────────────────────────────

def node_send_emails(state: JobAgentState) -> dict:
    print("\n[6/6] EmailSendAgent — sending approved emails...")
    from email_agent import send_email

    approved = state.get("approved_emails", [])
    sent     = []

    for draft in approved:
        try:
            send_email(draft)
            sent.append(draft)
            print(f"  ✓ Sent → {draft['to_email']}")
        except Exception as e:
            print(f"  ✗ Failed ({draft['to_email']}): {e}")

    print(f"\n  {len(sent)}/{len(approved)} emails sent")
    return {"sent_emails": sent, "status": "complete"}


# ── ROUTING ───────────────────────────────────────────────────────────────────

def route_after_parse(state: JobAgentState) -> str:
    return "failed" if state.get("status") == "failed" else "search_jobs"

def route_after_search(state: JobAgentState) -> str:
    if state.get("status") == "failed":
        return "failed"
    if not state.get("jobs"):
        print("  No jobs found above threshold — stopping.")
        return "failed"
    return "find_recruiters"

def route_after_recruiters(state: JobAgentState) -> str:
    recruiters = state.get("recruiters", [])
    if not recruiters:
        print("  No recruiter contacts found — stopping.")
        return "failed"
    return "draft_emails"

def route_after_drafts(state: JobAgentState) -> str:
    drafts = state.get("email_drafts", [])
    if not drafts:
        print("  No emails drafted — stopping.")
        return "failed"
    return "human_review"


# ── BUILD GRAPH ───────────────────────────────────────────────────────────────

def build_graph():
    builder = StateGraph(JobAgentState)

    # Add nodes
    builder.add_node("parse_resume",    node_parse_resume)
    builder.add_node("search_jobs",     node_search_jobs)
    builder.add_node("find_recruiters", node_find_recruiters)
    builder.add_node("draft_emails",    node_draft_emails)
    builder.add_node("human_review",    node_human_review)
    builder.add_node("send_emails",     node_send_emails)

    # Entry point
    builder.set_entry_point("parse_resume")

    # Conditional edges
    builder.add_conditional_edges("parse_resume",    route_after_parse,
                                  {"search_jobs": "search_jobs", "failed": END})
    builder.add_conditional_edges("search_jobs",     route_after_search,
                                  {"find_recruiters": "find_recruiters", "failed": END})
    builder.add_conditional_edges("find_recruiters", route_after_recruiters,
                                  {"draft_emails": "draft_emails", "failed": END})
    builder.add_conditional_edges("draft_emails",    route_after_drafts,
                                  {"human_review": "human_review", "failed": END})

    # Linear edges
    builder.add_edge("human_review", "send_emails")
    builder.add_edge("send_emails",  END)

    # MemorySaver enables checkpointing — graph state is saved at each node
    # so you can resume after the human_review breakpoint
    checkpointer = MemorySaver()
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],  # pause before sending
    )


# ── RUNNER ────────────────────────────────────────────────────────────────────

def run_pipeline(
    resume_path: str,
    locations:   list[str] | None = None,
    top_n:       int = 10,
    min_score:   int = 60,
    thread_id:   str = "job_agent_run_1",
):
    """
    Run the full job agent pipeline with human-in-the-loop email approval.
    """
    import warnings
    warnings.filterwarnings("ignore")

    graph  = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "resume_path":     resume_path,
        "locations":       locations or ["Remote", "United States", "Bangalore, India"],
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

    print("=" * 60)
    print("  JOB AGENT — LangGraph Pipeline")
    print("=" * 60)

    # Run until human_review breakpoint
    for chunk in graph.stream(initial_state, config, stream_mode="values"):
        pass  # state updates streamed — nodes print their own progress

    # Check if we hit the breakpoint
    state = graph.get_state(config)
    if state.next == ("human_review",):
        print("\n" + "=" * 60)
        print("  PAUSED — Human review required before sending emails")
        print("=" * 60)

        # Resume through human_review → send_emails
        for chunk in graph.stream(None, config, stream_mode="values"):
            pass

    # Final state
    final = graph.get_state(config).values
    print("\n" + "=" * 60)
    print(f"  Pipeline complete")
    print(f"  Jobs found    : {len(final.get('jobs', []))}")
    print(f"  Emails drafted: {len(final.get('email_drafts', []))}")
    print(f"  Emails sent   : {len(final.get('sent_emails', []))}")
    if final.get("errors"):
        print(f"  Errors        : {len(final['errors'])}")
        for e in final["errors"]:
            print(f"    - {e}")
    print("=" * 60)

    return final


if __name__ == "__main__":
    import sys
    resume = sys.argv[1] if len(sys.argv) > 1 else "kamal_ai_profile.json"
    run_pipeline(resume_path=resume)
