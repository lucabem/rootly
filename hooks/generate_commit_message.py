#!/usr/bin/env python3
"""
Called by hooks/prepare-commit-msg.
Generates a commit message and CHANGELOG.md entry using Claude Haiku.
Errors are printed as warnings — never block the commit.
"""
import os
import re
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


def parse_response(text: str) -> tuple[str, str]:
    msg_match = re.search(r"COMMIT_MESSAGE:\s*(.+?)(?=CHANGELOG:|$)", text, re.DOTALL)
    log_match = re.search(r"CHANGELOG:\s*(.+?)$", text, re.DOTALL)
    msg = msg_match.group(1).strip() if msg_match else ""
    log = log_match.group(1).strip() if log_match else ""
    return msg, log


def update_changelog(project_root: str, commit_msg: str, entry: str) -> None:
    path = os.path.join(project_root, "CHANGELOG.md")
    today = date.today().isoformat()
    block = f"\n### {today}\n- **{commit_msg}** — {entry}\n"

    if os.path.exists(path):
        content = open(path).read()
        if "## Unreleased" in content:
            content = content.replace("## Unreleased\n", f"## Unreleased\n{block}", 1)
        else:
            content = block + content
    else:
        content = f"# Changelog\n\n## Unreleased\n{block}"

    with open(path, "w") as f:
        f.write(content)

    subprocess.run(["git", "add", "CHANGELOG.md"], cwd=project_root, check=True)


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

    suggested_msg, changelog_entry = parse_response(resp.content[0].text)
    if not suggested_msg:
        return

    with open(msg_file, "w") as f:
        if user_provided:
            # Keep user's message; append Claude's as a reference comment
            f.write(existing.rstrip())
            f.write(f"\n# Claude suggestion: {suggested_msg}\n")
        else:
            f.write(suggested_msg + "\n")
            comments = "\n".join(l for l in existing.splitlines() if l.startswith("#"))
            if comments:
                f.write("\n" + comments)

    if changelog_entry:
        update_changelog(project_root, suggested_msg, changelog_entry)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[claude-hook] warning: {e}", file=sys.stderr)
