#!/usr/bin/env python3
"""
Split multi-entity knowledge markdown files into one file per ## section.

Run after each Excel export to keep knowledge/ clean:
    python scripts/split_knowledge.py --dry-run          # preview
    python scripts/split_knowledge.py                    # write files
    python scripts/split_knowledge.py --delete-originals # write + remove source

Only files that contain 2+ ## sections are split. Single-section files are left alone.
"""

import argparse
import os
import re
import sys


def slugify(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "_", s)
    return s.strip("_") or "section"


def split_md(content: str) -> list[tuple[str, str]]:
    """
    Split markdown by ## headings.
    Returns list of (slug, section_text) — skips minimal preambles.
    """
    parts = re.split(r"^## ", content, flags=re.MULTILINE)
    results = []

    for i, part in enumerate(parts):
        if i == 0:
            # Preamble: keep only if it has content beyond the # title and *italics* lines
            substantive = [
                l for l in part.strip().splitlines()
                if l.strip() and not l.startswith("#") and not re.match(r"^\*.*\*$", l.strip())
            ]
            if not substantive:
                continue
            first = part.strip().splitlines()[0]
            title = first.lstrip("# ").strip()
            results.append((slugify(title), part.strip()))
        else:
            first_line, _, body = part.partition("\n")
            title = first_line.strip()
            text = f"## {title}\n{body.rstrip()}"
            results.append((slugify(title), text))

    return results


def process_file(path: str, dry_run: bool, delete_original: bool) -> int:
    with open(path, encoding="utf-8") as f:
        content = f.read()

    sections = split_md(content)

    if len(sections) <= 1:
        print(f"  skip — only {len(sections)} substantive section(s)")
        return 0

    # Output into a subdirectory named after the source file to avoid collisions
    source_stem = slugify(os.path.splitext(os.path.basename(path))[0])
    out_dir = os.path.join(os.path.dirname(path), source_stem)
    source_abs = os.path.abspath(path)
    created = 0

    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)

    for slug, text in sections:
        out_path = os.path.join(out_dir, f"{slug}.md")
        if os.path.abspath(out_path) == source_abs:
            print(f"  skip {slug}.md — would overwrite source")
            continue
        if dry_run:
            lines = text.count("\n") + 1
            print(f"  [dry-run] {out_path}  ({lines} lines)")
        else:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            print(f"  wrote    {out_path}")
        created += 1

    if created > 0 and delete_original and not dry_run:
        os.remove(path)
        print(f"  deleted  {path}")

    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("knowledge_dir", nargs="?", default="knowledge", help="Path to knowledge/ dir (default: knowledge/)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing")
    parser.add_argument("--delete-originals", action="store_true", help="Remove source files after splitting")
    args = parser.parse_args()

    if not os.path.isdir(args.knowledge_dir):
        print(f"ERROR: {args.knowledge_dir!r} is not a directory", file=sys.stderr)
        sys.exit(1)

    total = 0
    for root, _, files in os.walk(args.knowledge_dir):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(root, fname)
            print(f"\n{path}")
            total += process_file(path, args.dry_run, args.delete_originals)

    verb = "would create" if args.dry_run else "created"
    print(f"\nDone — {verb} {total} file(s).")


if __name__ == "__main__":
    main()
