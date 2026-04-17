"""
inspect_lineage.py
------------------
Muestra un resumen legible de los eventos OpenLineage generados
en openlineage/events.ndjson tras ejecutar los scripts de examples/.

Uso:
    python inspect_lineage.py
    python inspect_lineage.py --file openlineage/events.ndjson
"""

import argparse
import json
import os
from collections import defaultdict


BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EVENTS = os.path.join(BASE_DIR, "openlineage", "events.ndjson")


def load_events(path: str) -> list[dict]:
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def summarize(events: list[dict]) -> None:
    by_run: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        run_id = ev.get("run", {}).get("runId", "unknown")
        by_run[run_id].append(ev)

    print(f"\n{'='*70}")
    print(f" OpenLineage events: {len(events)} total / {len(by_run)} runs")
    print(f"{'='*70}\n")

    for run_id, run_events in by_run.items():
        # último evento para el nombre del job
        last = run_events[-1]
        job  = last.get("job", {})
        job_name = f"{job.get('namespace', '?')}/{job.get('name', '?')}"

        print(f"Run: {run_id[:8]}…")
        print(f"  Job:    {job_name}")

        for ev in run_events:
            event_type = ev.get("eventType", "?")
            ts         = ev.get("eventTime", "?")
            inputs     = [
                d.get("name", "?")
                for d in ev.get("inputs", [])
            ]
            outputs    = [
                d.get("name", "?")
                for d in ev.get("outputs", [])
            ]
            facets     = list(ev.get("run", {}).get("facets", {}).keys())

            print(f"  [{event_type:12s}] {ts}")
            if inputs:
                print(f"    inputs  : {', '.join(inputs)}")
            if outputs:
                print(f"    outputs : {', '.join(outputs)}")
            if facets:
                print(f"    facets  : {', '.join(facets)}")

        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspecciona eventos OpenLineage")
    parser.add_argument(
        "--file", default=DEFAULT_EVENTS,
        help=f"Ruta al fichero .ndjson (default: {DEFAULT_EVENTS})"
    )
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"[!] No se encontró el fichero de eventos: {args.file}")
        print("    Ejecuta primero algún script de examples/")
        return

    events = load_events(args.file)
    summarize(events)


if __name__ == "__main__":
    main()
