#!/usr/bin/env python3
"""
Called by hooks/prepare-commit-msg.
Generates a commit message and updates CHANGELOG.md in the same commit.
Errors are printed as warnings — never block the commit.
"""
import os
import subprocess
import sys
from datetime import date

MAX_DIFF_CHARS = 8_000


def staged_diff(project_root: str) -> str:
    stat = subprocess.check_output(
        ["git", "diff", "--cached", "--stat"], cwd=project_root, text=True
    )
    diff = subprocess.check_output(
        ["git", "diff", "--cached"], cwd=project_root, text=True
    )
    return (stat + "\n---\n" + diff)[:MAX_DIFF_CHARS]


def staged_files(project_root: str) -> list[str]:
    return subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], cwd=project_root, text=True
    ).strip().splitlines()


def update_changelog(project_root: str, commit_msg: str, entry: str) -> None:
    # Skip if CHANGELOG.md is already staged — respect the user's version
    # and avoid re-entering this logic on a changelog-only commit.
    if "CHANGELOG.md" in staged_files(project_root):
        return

    path = os.path.join(project_root, "CHANGELOG.md")
    today = date.today().isoformat()
    block = f"\n### {today}\n- **{commit_msg}** — {entry}\n"

    original = open(path).read() if os.path.exists(path) else None

    if original is not None:
        if "## Unreleased" in original:
            content = original.replace("## Unreleased\n", f"## Unreleased\n{block}", 1)
        else:
            content = block + original
    else:
        content = f"# Changelog\n\n## Unreleased\n{block}"

    pending = os.path.join(project_root, ".git", "CHANGELOG_PENDING")
    with open(pending, "w") as f:
        f.write(content)


def main() -> None:
    msg_file, commit_source, project_root = sys.argv[1], sys.argv[2], sys.argv[3]

    diff = staged_diff(project_root)
    if not diff.strip():
        return

    with open(msg_file) as f:
        existing = f.read()

    user_provided = commit_source == "message"

    import anthropic
    client = anthropic.Anthropic()

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                "Given these staged git changes, produce:\n"
                "1. A commit message (conventional commits: type(scope): description, max 72 chars)\n"
                "2. A one-line changelog entry (what changed and why, for a human reader)\n\n"
                f"Changes:\n{diff}\n\n"
                "Reply in exactly this format:\n"
                "COMMIT_MESSAGE:\n<message>\n\nCHANGELOG:\n<entry>"
            ),
        }],
    )

    block = next((b for b in resp.content if b.type == "text"), None)
    if not block:
        return
    text = block.text.strip()

    # Parse COMMIT_MESSAGE and CHANGELOG sections
    msg, entry = "", ""
    if "COMMIT_MESSAGE:" in text and "CHANGELOG:" in text:
        parts = text.split("CHANGELOG:", 1)
        msg = parts[0].replace("COMMIT_MESSAGE:", "").strip()
        entry = parts[1].strip()
    else:
        msg = text.splitlines()[0].strip()

    if not msg:
        return

    with open(msg_file, "w") as f:
        if user_provided:
            f.write(existing.rstrip())
            f.write(f"\n# Claude suggestion: {msg}\n")
        else:
            f.write(msg + "\n")
            comments = "\n".join(l for l in existing.splitlines() if l.startswith("#"))
            if comments:
                f.write("\n" + comments)

    if entry:
        update_changelog(project_root, msg, entry)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[claude-hook] warning: {e}", file=sys.stderr)
