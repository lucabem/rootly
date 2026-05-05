#!/usr/bin/env bash
# Run once after cloning: bash hooks/install.sh
set -euo pipefail
git config core.hooksPath hooks
chmod +x hooks/prepare-commit-msg
echo "Git hooks installed. Claude will generate commit messages and changelog entries on each commit."
