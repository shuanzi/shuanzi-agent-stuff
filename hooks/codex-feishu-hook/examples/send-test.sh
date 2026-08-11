#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${HOME:?HOME is required}"
CONFIG_PATH="${1:-${XDG_CONFIG_HOME:-$HOME_DIR/.config}/codex-feishu/config.json}"

CODEX_FEISHU_STRICT=1 \
CODEX_FEISHU_CONFIG="$CONFIG_PATH" \
python3 "$PACKAGE_DIR/bin/codex_feishu_notify.py" < "$PACKAGE_DIR/examples/stop-event.json"

echo "Test notification sent."
