#!/usr/bin/env python3
"""
Called by hooks/post-commit.
Appends the latest commit message to CHANGELOG.md.
Never stages the file — the user commits it manually.
"""
import os
import subprocess
import sys
from datetime import date


def main() -> None:
    project_root = sys.argv[1]

    commit_msg = subprocess.check_output(
        ["git", "log", "-1", "--format=%s"], cwd=project_root, text=True
    ).strip()

    # Skip changelog-only commits to avoid the entry referencing itself
    if not commit_msg or "changelog" in commit_msg.lower():
        return

    path = os.path.join(project_root, "CHANGELOG.md")
    today = date.today().isoformat()
    block = f"\n### {today}\n- {commit_msg}\n"

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


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[changelog] warning: {e}", file=sys.stderr)
