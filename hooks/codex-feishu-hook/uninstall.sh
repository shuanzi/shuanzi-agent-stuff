#!/usr/bin/env bash
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
XDG_CONFIG_HOME_VALUE="${XDG_CONFIG_HOME:-$HOME/.config}"
PRIVATE_DIR="$XDG_CONFIG_HOME_VALUE/codex-feishu"
TARGET_SCRIPT="$CODEX_HOME/hooks/codex_feishu_notify.py"
HOOKS_FILE="$CODEX_HOME/hooks.json"
HOOK_STATE="$PRIVATE_DIR/user-hook-state.json"
PURGE=false

case "${1:-}" in
  "") ;;
  --purge) PURGE=true ;;
  -h|--help)
    echo "Usage: ./uninstall.sh [--purge]"
    echo "Without --purge, the private webhook configuration is preserved."
    exit 0 ;;
  *)
    echo "unknown option: $1" >&2
    exit 2 ;;
esac

if [[ -f "$HOOK_STATE" ]]; then
  HOOKS_FILE="$HOOKS_FILE" HOOK_STATE="$HOOK_STATE" python3 <<'PY'
import json
import os
import stat
import sys
import tempfile
from pathlib import Path


def fail(message: str) -> None:
    print(f"codex-feishu-hook: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_json(path: Path, label: str) -> object:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid {label}: {error}")


def write_json(path: Path, value: object, mode: int) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


hooks_path = Path(os.environ["HOOKS_FILE"])
state_path = Path(os.environ["HOOK_STATE"])
state = load_json(state_path, "managed Hook state")
if not isinstance(state, dict) or not isinstance(state.get("hook_group"), dict):
    fail("managed Hook state is invalid")
if not hooks_path.exists():
    fail("user Hook config is missing; restore it before uninstalling")

hooks_value = load_json(hooks_path, "hooks JSON")
if not isinstance(hooks_value, dict):
    fail("hooks.json root must be a JSON object")
hooks = hooks_value.get("hooks")
if not isinstance(hooks, dict):
    fail("hooks.json hooks field must be a JSON object")
groups = hooks.get("Stop")
if not isinstance(groups, list):
    fail("hooks.Stop must be a JSON array")

group = state["hook_group"]
if groups.count(group) != 1:
    fail("managed Feishu Stop Hook is missing or duplicated")
groups.remove(group)
if not groups:
    hooks.pop("Stop")

write_json(hooks_path, hooks_value, stat.S_IMODE(hooks_path.stat().st_mode))
PY
fi

rm -f "$TARGET_SCRIPT" "$HOOK_STATE"

if [[ "$PURGE" == true ]]; then
  rm -rf "$PRIVATE_DIR"
  rm -f "$CODEX_HOME/log/feishu-notify.log" "$CODEX_HOME/log/feishu-notify.log.1"
  printf 'Removed notifier, managed Stop Hook, and private configuration.\n'
else
  printf 'Removed notifier and managed Stop Hook. Private configuration preserved at: %s\n' "$PRIVATE_DIR"
fi

rmdir "$CODEX_HOME/hooks" 2>/dev/null || true
rmdir "$CODEX_HOME/log" 2>/dev/null || true
