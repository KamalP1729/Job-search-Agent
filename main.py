"""
main.py — CLI entry point for the resume parser and job scorer.

Usage:
  python main.py parse <resume_file>
  python main.py score <resume_file> --jd "paste job description here"
  python main.py score <resume_file> --jd-file path/to/jd.txt
  python main.py batch-score <resume_file> --jd-dir path/to/jds/
  python main.py batch-score <resume_file> --jd-files jd1.txt jd2.txt jd3.txt
  python main.py search <profile.json> --locations "Bangalore, India" "Remote"
"""

import argparse
import json
import sys
from pathlib import Path
from parser import parse_resume
from scorer import score_job


def cmd_parse(args):
    print(f"Parsing resume: {args.resume}\n")
    profile = parse_resume(args.resume)
    print(json.dumps(profile, indent=2))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(profile, f, indent=2)
        print(f"\nProfile saved to: {args.output}")


def cmd_score(args):
    # Load JD text
    if args.jd:
        jd_text = args.jd
    elif args.jd_file:
        with open(args.jd_file, "r") as f:
            jd_text = f.read()
    else:
        print("Error: provide --jd or --jd-file")
        sys.exit(1)

    # Load profile: either parse from resume file or read pre-parsed JSON
    if args.resume.endswith(".json"):
        with open(args.resume, "r") as f:
            profile = json.load(f)
    else:
        print(f"Parsing resume: {args.resume}")
        profile = parse_resume(args.resume)

    print(f"\nScoring against job description...\n")
    result = score_job(profile, jd_text)

    # Pretty print result
    print(f"Overall Score : {result['overall_score']} / 100")
    print(f"Verdict       : {result['verdict']}")
    print(f"YOE Assessment: {result['yoe_assessment']}")
    print()
    print("Breakdown:")
    for k, v in result["breakdown"].items():
        print(f"  {k:<22} {v}/100")
    print()
    print(f"Matched Skills : {', '.join(result['matched_skills']) or 'none'}")
    print(f"Missing Skills : {', '.join(result['missing_skills']) or 'none'}")
    print()
    print(f"Recommendation:\n  {result['recommendation']}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nFull result saved to: {args.output}")


def cmd_batch_score(args):
    # Load or parse profile
    if args.resume.endswith(".json"):
        with open(args.resume, "r") as f:
            profile = json.load(f)
    else:
        print(f"Parsing resume: {args.resume}")
        profile = parse_resume(args.resume)
        if args.save_profile:
            with open(args.save_profile, "w") as f:
                json.dump(profile, f, indent=2)
            print(f"Profile saved to: {args.save_profile}\n")

    # Collect JD files
    jd_files: list[Path] = []
    if args.jd_dir:
        jd_files = sorted(Path(args.jd_dir).glob("*.txt"))
        if not jd_files:
            print(f"No .txt files found in {args.jd_dir}")
            sys.exit(1)
    elif args.jd_files:
        jd_files = [Path(p) for p in args.jd_files]

    if not jd_files:
        print("Error: provide --jd-dir or --jd-files")
        sys.exit(1)

    print(f"Scoring against {len(jd_files)} job description(s)...\n")

    results = []
    for jd_path in jd_files:
        jd_text = jd_path.read_text()
        label = jd_path.stem
        print(f"  Scoring: {label} ...", end=" ", flush=True)
        result = score_job(profile, jd_text)
        result["jd_file"] = str(jd_path)
        result["jd_label"] = label
        results.append(result)
        print(f"{result['overall_score']}/100  [{result['verdict']}]")

    # Sort by score descending
    results.sort(key=lambda r: r["overall_score"], reverse=True)

    print("\n" + "=" * 60)
    print(f"{'RANK':<5} {'SCORE':<7} {'VERDICT':<16} JD")
    print("=" * 60)
    for i, r in enumerate(results, 1):
        print(f"{i:<5} {r['overall_score']:<7} {r['verdict']:<16} {r['jd_label']}")

    print()
    print("Top match recommendation:")
    print(f"  {results[0]['recommendation']}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nFull results saved to: {args.output}")


def cmd_run(args):
    from graph import run_pipeline
    run_pipeline(
        resume_path=args.resume,
        locations=args.locations,
        top_n=args.top_n,
        min_score=args.min_score,
    )


def cmd_find_recruiters(args):
    from recruiter_finder import find_all, print_results

    print(f"Finding contacts for {len(args.companies)} companies...\n")
    results = find_all(args.companies)
    print_results(results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved to: {args.output}")


def cmd_search(args):
    from job_search import search_and_rank

    # Load profile
    with open(args.profile, "r") as f:
        profile = json.load(f)

    locations = args.locations or ["Bangalore, India", "Remote"]
    print(f"Searching jobs for: {profile.get('current_role')} | {profile.get('total_yoe')} YOE")
    print(f"Locations: {', '.join(locations)}\n")

    results = search_and_rank(profile, locations=locations, top_n=args.top_n)

    if not results:
        print("No results above the minimum score threshold.")
        return

    print("\n" + "=" * 85)
    print(f"{'RANK':<5} {'SCORE':<7} {'VERDICT':<16} {'COMPANY':<22} {'LOCATION':<18} TITLE")
    print("=" * 85)
    for i, r in enumerate(results, 1):
        loc = r.get("location", "")[:17]
        print(f"{i:<5} {r['score']:<7} {r['verdict']:<16} {r['company']:<22} {loc:<18} {r['title']}")

    # Flag remote jobs in output
    remote_count = sum(1 for r in results if "remote" in r.get("location", "").lower())
    bangalore_count = sum(1 for r in results if "bangalore" in r.get("location", "").lower())
    print(f"\nRemote: {remote_count}  |  Bangalore: {bangalore_count}  |  Other: {len(results)-remote_count-bangalore_count}")

    print(f"\nTop pick: {results[0]['company']} — {results[0]['title']}")
    print(f"Location: {results[0].get('location', 'N/A')}")
    print(f"Apply:    {results[0]['apply_link'] or 'see job board'}")
    print(f"\nRecommendation:\n  {results[0]['recommendation']}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nFull results saved to: {args.output}")


def main():
    parser = argparse.ArgumentParser(description="Job Agent — Resume Parser & Scorer")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- parse subcommand ---
    p_parse = sub.add_parser("parse", help="Parse a resume into a structured profile")
    p_parse.add_argument("resume", help="Path to resume PDF or DOCX")
    p_parse.add_argument("--output", "-o", help="Save profile JSON to this file")

    # --- score subcommand ---
    p_score = sub.add_parser("score", help="Score a resume against a job description")
    p_score.add_argument("resume", help="Path to resume PDF, DOCX, or pre-parsed profile JSON")
    p_score.add_argument("--jd", help="Job description text (inline)")
    p_score.add_argument("--jd-file", help="Path to a .txt file containing the job description")
    p_score.add_argument("--output", "-o", help="Save score JSON to this file")

    # --- batch-score subcommand ---
    p_batch = sub.add_parser("batch-score", help="Score a resume against multiple JDs, ranked")
    p_batch.add_argument("resume", help="Path to resume PDF, DOCX, or pre-parsed profile JSON")
    p_batch.add_argument("--jd-dir", help="Directory containing .txt JD files")
    p_batch.add_argument("--jd-files", nargs="+", help="One or more .txt JD file paths")
    p_batch.add_argument("--save-profile", help="Save parsed profile JSON to this file")
    p_batch.add_argument("--output", "-o", help="Save ranked results JSON to this file")

    # --- run subcommand (full LangGraph pipeline) ---
    p_run = sub.add_parser("run", help="Run the full LangGraph pipeline end-to-end")
    p_run.add_argument("resume", help="Path to resume PDF, DOCX, or pre-parsed profile JSON")
    p_run.add_argument("--locations", nargs="+", help="Locations to search")
    p_run.add_argument("--top-n", type=int, default=10, help="Top N jobs to process (default: 10)")
    p_run.add_argument("--min-score", type=int, default=60, help="Minimum score threshold (default: 60)")

    # --- find-recruiters subcommand ---
    p_rec = sub.add_parser("find-recruiters", help="Find recruiter/founder emails via Hunter.io")
    p_rec.add_argument("companies", nargs="+", help="Company names to search")
    p_rec.add_argument("--output", "-o", help="Save results JSON to this file")

    # --- search subcommand ---
    p_search = sub.add_parser("search", help="Search Google Jobs, score results, return ranked list")
    p_search.add_argument("profile", help="Path to pre-parsed profile JSON")
    p_search.add_argument("--locations", nargs="+", help="Locations to search (default: Bangalore + Remote)")
    p_search.add_argument("--top-n", type=int, default=10, help="Return top N results (default: 10)")
    p_search.add_argument("--output", "-o", help="Save ranked results JSON to this file")

    args = parser.parse_args()

    if args.command == "parse":
        cmd_parse(args)
    elif args.command == "score":
        cmd_score(args)
    elif args.command == "batch-score":
        cmd_batch_score(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "find-recruiters":
        cmd_find_recruiters(args)
    elif args.command == "run":
        cmd_run(args)


if __name__ == "__main__":
    main()
