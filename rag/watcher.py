"""
rag/watcher.py
--------------
Two near real-time modes:

  start_watching()       - local: watches events.ndjson with watchdog
  start_watching_s3()    - production: S3 polling for new events
"""

import os
import time

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from rag.ingest import (
    EVENTS_PATH,
    build_graph,
    enrich_graph_with_code,
    load_events,
    load_events_s3,
    load_job_code_s3,
)
from rag.vectorize import build_index


class _LineageHandler(FileSystemEventHandler):
    def __init__(self, events_path: str) -> None:
        self._path = events_path
        self._last_pos = 0
        self._initial_sync()

    def on_modified(self, event: FileModifiedEvent) -> None:
        if os.path.abspath(event.src_path) != os.path.abspath(self._path):
            return
        self._incremental_sync()

    # ── sync helpers ─────────────────────────────────────────────────────────

    def _initial_sync(self) -> None:
        if not os.path.exists(self._path):
            print(f"[watch] {self._path} does not exist yet. Waiting...")
            return
        self._last_pos = 0
        self._incremental_sync()

    def _incremental_sync(self) -> None:
        new_lines = self._read_new_lines()
        if not new_lines:
            return

        print(f"[watch] {len(new_lines)} new lines detected - re-indexing...")
        # Rebuild full graph (the file grows, it is not replaced)
        events = load_events(self._path)
        G = build_graph(events)
        collection = build_index(G)
        print(
            f"[watch] Index updated: {collection.count()} documents in ChromaDB"
        )

    def _read_new_lines(self) -> list[str]:
        if not os.path.exists(self._path):
            return []
        with open(self._path) as f:
            f.seek(self._last_pos)
            lines = [l for l in f.readlines() if l.strip()]
            self._last_pos = f.tell()
        return lines


def start_watching_s3(
    bucket: str,
    events_prefix: str = "openlineage/",
    jobs_prefix: str = "glue/code/jobs/",
    interval: int = 30,
) -> None:
    """S3 polling: re-indexes when new objects appear under the events prefix."""
    import boto3

    s3 = boto3.client("s3")

    def _etags(prefix: str) -> dict[str, str]:
        etags: dict[str, str] = {}
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                etags[obj["Key"]] = obj["ETag"]
        return etags

    def _sync() -> None:
        print(f"[watch-s3] Syncing s3://{bucket}/{events_prefix} ...")
        events = load_events_s3(bucket, events_prefix)
        G = build_graph(events)
        collection = build_index(G)
        print(f"[watch-s3] Index updated: {collection.count()} documents")

    known_etags = _etags(events_prefix)
    _sync()

    print(f"[watch-s3] Polling every {interval}s - Ctrl+C to stop\n")
    try:
        while True:
            time.sleep(interval)
            current_etags = _etags(events_prefix)
            if current_etags != known_etags:
                new_keys = set(current_etags) - set(known_etags)
                changed = {
                    k for k, e in current_etags.items() if known_etags.get(k) != e
                }
                print(
                    f"[watch-s3] Changes detected: {len(new_keys)} new, {len(changed - new_keys)} modified"
                )
                known_etags = current_etags
                _sync()
    except KeyboardInterrupt:
        print("\n[watch-s3] Stopped.")


def start_watching(events_path: str = EVENTS_PATH) -> None:
    watch_dir = os.path.dirname(os.path.abspath(events_path))
    handler = _LineageHandler(events_path)

    observer = Observer()
    observer.schedule(handler, path=watch_dir, recursive=False)
    observer.start()

    print(f"[watch] Watching {events_path}")
    print("[watch] Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        print("\n[watch] Stopped.")
