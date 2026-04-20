"""
inspect_lineage.py
------------------
Prints a human-readable summary of the OpenLineage events generated
in openlineage/events.ndjson, or loaded directly from S3.

Usage:
    python inspect_lineage.py
    python inspect_lineage.py --file openlineage/events.ndjson
    python inspect_lineage.py --bucket my-bucket
    python inspect_lineage.py --bucket my-bucket --events-prefix openlineage/parsed/
"""

import argparse
import os
from collections import defaultdict

from rag.ingest import load_events as _load_local, load_events_s3


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EVENTS = os.path.join(BASE_DIR, "openlineage", "events.ndjson")


def load_events(path: str) -> list[dict]:
    return _load_local(path)


def filter_event(ev: dict) -> bool:
    job_name = ev.get("job", {}).get("name", "")
    if "execute_save_into_data_source_command" not in job_name:
        return False
    event_type = ev.get("eventType", "")
    if event_type not in ("COMPLETE"):
        return False
    if len(ev.get("outputs", [])) == 0:
        return False

    print(
        f"Matched event: job={job_name}, eventType={event_type}, "
        f"len(inputs)={len(ev.get('inputs', []))}, len(outputs)={len(ev.get('outputs', []))}"
    )
    return True


def summarize(events: list[dict]) -> None:
    by_run: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        run_id = ev.get("run", {}).get("runId", "unknown")
        by_run[run_id].append(ev)

    print(f"\n{'='*70}")
    print(f" OpenLineage events: {len(events)} total / {len(by_run)} runs")
    print(f"{'='*70}\n")

    for run_id, run_events in by_run.items():
        last = run_events[-1]
        job = last.get("job", {})
        job_name = f"{job.get('namespace', '?')}/{job.get('name', '?')}"

        print(f"Run: {run_id[:8]}…")
        print(f"  Job:    {job_name}")

        for ev in run_events:
            event_type = ev.get("eventType", "?")
            ts = ev.get("eventTime", "?")
            inputs = [d.get("name", "?") for d in ev.get("inputs", [])]
            outputs = [d.get("name", "?") for d in ev.get("outputs", [])]
            facets = list(ev.get("run", {}).get("facets", {}).keys())

            print(f"  [{event_type:12s}] {ts}")
            if inputs:
                print(f"    inputs  : {', '.join(inputs)}")
            if outputs:
                print(f"    outputs : {', '.join(outputs)}")
            if facets:
                print(f"    facets  : {', '.join(facets)}")

        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect OpenLineage events")
    parser.add_argument(
        "--file",
        default=DEFAULT_EVENTS,
        help=f"Path to the .ndjson file (default: {DEFAULT_EVENTS})",
    )
    parser.add_argument("--bucket", help="S3 bucket (enables S3 loading)")
    parser.add_argument(
        "--events-prefix",
        default="openlineage/parsed/",
        help="S3 events prefix (default: openlineage/parsed/)",
    )
    args = parser.parse_args()

    if args.bucket:
        print(f"[info] Loading from s3://{args.bucket}/{args.events_prefix} ...")
        events = load_events_s3(args.bucket, args.events_prefix)
        print(f"[info] {len(events)} events loaded from S3")
    else:
        if not os.path.exists(args.file):
            print(f"[!] Events file not found: {args.file}")
            print("    Run one of the examples/ scripts first, or use --bucket")
            return
        events = load_events(args.file)

    events = [ev for ev in events if filter_event(ev)]
    summarize(events)


if __name__ == "__main__":
    main()
