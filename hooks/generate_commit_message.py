#!/usr/bin/env python3
"""
Called by hooks/prepare-commit-msg.
Generates a commit message suggestion using Claude Haiku.
Errors are printed as warnings — never block the commit.
"""
import subprocess
import sys

MAX_DIFF_CHARS = 8_000


def staged_diff(project_root: str) -> str:
    stat = subprocess.check_output(
        ["git", "diff", "--cached", "--stat"], cwd=project_root, text=True
    )
    diff = subprocess.check_output(
        ["git", "diff", "--cached"], cwd=project_root, text=True
    )
    return (stat + "\n---\n" + diff)[:MAX_DIFF_CHARS]


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
        max_tokens=120,
        messages=[{
            "role": "user",
            "content": (
                "Given these staged git changes, write a commit message in conventional commits format "
                "(type(scope): description, max 72 chars). Reply with ONLY the commit message, nothing else.\n\n"
                f"Changes:\n{diff}"
            ),
        }],
    )

    block = next((b for b in resp.content if b.type == "text"), None)
    suggested_msg = block.text.strip() if block else ""
    if not suggested_msg:
        return

    with open(msg_file, "w") as f:
        if user_provided:
            f.write(existing.rstrip())
            f.write(f"\n# Claude suggestion: {suggested_msg}\n")
        else:
            f.write(suggested_msg + "\n")
            comments = "\n".join(l for l in existing.splitlines() if l.startswith("#"))
            if comments:
                f.write("\n" + comments)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[claude-hook] warning: {e}", file=sys.stderr)
