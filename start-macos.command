#!/bin/zsh
set -e
cd "${0:A:h}"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.10+ and run this file again."
  echo "For Homebrew users: brew install python"
  read "?Press Return to close..."
  exit 1
fi
exec python3 ./codex_usage_widget.py
