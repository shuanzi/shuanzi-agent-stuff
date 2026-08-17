#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
XDG_CONFIG_HOME_VALUE="${XDG_CONFIG_HOME:-$HOME/.config}"
PRIVATE_DIR="$XDG_CONFIG_HOME_VALUE/codex-feishu"
TARGET_SCRIPT="$CODEX_HOME/hooks/codex_feishu_notify.py"
PRIVATE_CONFIG="$PRIVATE_DIR/config.json"
HOOKS_FILE="$CODEX_HOME/hooks.json"
HOOK_STATE="$PRIVATE_DIR/user-hook-state.json"

WEBHOOK_URL=""
SIGN_SECRET=""
INCLUDE_SUMMARY=true
INCLUDE_CWD=true
SUMMARY_MAX_CHARS=4000
TAG=""
SEND_TEST=false

usage() {
  cat <<'USAGE'
用法：./install.sh

安装器会以交互方式收集所有通知设置。
请不要传入参数，以避免凭证写入 shell history。

环境变量：
  CODEX_HOME, XDG_CONFIG_HOME
USAGE
}

if [[ $# -gt 0 ]]; then
  if [[ $# -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
    usage
    exit 0
  fi
  echo "install.sh 不接受命令行参数，请直接执行 ./install.sh。" >&2
  usage >&2
  exit 2
fi

read_value() {
  local prompt="$1"
  local value
  if ! read -r -p "$prompt" value; then
    echo "安装已取消。" >&2
    exit 2
  fi
  REPLY="$value"
}

read_yes_no() {
  local prompt="$1"
  local default="$2"
  local value

  while true; do
    read_value "$prompt"
    value="${REPLY:-$default}"
    case "$value" in
      y|Y) REPLY=true; return ;;
      n|N) REPLY=false; return ;;
      *) echo "请输入 y 或 n。" >&2 ;;
    esac
  done
}

while true; do
  read_value "飞书机器人 Webhook URL（必填）: "
  WEBHOOK_URL="$REPLY"
  if [[ "$WEBHOOK_URL" == https://* ]]; then
    break
  fi
  echo "Webhook URL 必须以 https:// 开头。" >&2
done

if ! read -r -s -p "飞书签名密钥（可选，直接回车跳过）: " SIGN_SECRET; then
  echo >&2
  echo "安装已取消。" >&2
  exit 2
fi
echo

read_yes_no "发送 Codex 最终回复摘要？[Y/n]: " y
INCLUDE_SUMMARY="$REPLY"
read_yes_no "发送绝对工作目录？[Y/n]: " y
INCLUDE_CWD="$REPLY"

while true; do
  read_value "摘要上限（0～4000，默认 4000）: "
  SUMMARY_MAX_CHARS="${REPLY:-4000}"
  if [[ "$SUMMARY_MAX_CHARS" =~ ^[0-9]+$ ]] && python3 - "$SUMMARY_MAX_CHARS" <<'PY'
import sys

raise SystemExit(0 if int(sys.argv[1]) <= 4000 else 1)
PY
  then
    break
  fi
  echo "摘要上限必须是 0～4000 的整数。" >&2
done

read_value "Hook 标签（可选，直接回车跳过）: "
TAG="$REPLY"
read_yes_no "安装后立即发送真实测试消息？[y/N]: " n
SEND_TEST="$REPLY"

# Validate the Hook file and any previously recorded managed state before
# writing runtime or private configuration files.
HOOKS_FILE="$HOOKS_FILE" HOOK_STATE="$HOOK_STATE" TARGET_SCRIPT="$TARGET_SCRIPT" python3 <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"codex-feishu-hook: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_json(path: Path, label: str, default: object) -> object:
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid {label}: {error}")


def managed_group(target_script: Path) -> dict[str, object]:
    command = f"python3 {shlex.quote(str(target_script))}"
    return {
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 5,
                "statusMessage": "Sending Feishu completion notification",
            }
        ]
    }


def stop_groups(value: object) -> list[object]:
    if not isinstance(value, dict):
        fail("hooks.json root must be a JSON object")
    hooks = value.get("hooks", {})
    if not isinstance(hooks, dict):
        fail("hooks.json hooks field must be a JSON object")
    groups = hooks.get("Stop", [])
    if not isinstance(groups, list):
        fail("hooks.Stop must be a JSON array")
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            fail("hooks.Stop entries must contain a hooks array")
    return groups


hooks_path = Path(os.environ["HOOKS_FILE"])
state_path = Path(os.environ["HOOK_STATE"])
group = managed_group(Path(os.environ["TARGET_SCRIPT"]))
hooks_value = load_json(hooks_path, "hooks JSON", {"hooks": {}})
groups = stop_groups(hooks_value)
state_value = load_json(state_path, "managed Hook state", None)

if state_value is not None:
    if not isinstance(state_value, dict) or state_value.get("hook_group") != group:
        fail("managed Hook state does not match this installation")
    if groups.count(group) != 1:
        fail("managed Feishu Stop Hook is missing or duplicated")
else:
    for existing_group in groups:
        for handler in existing_group["hooks"]:
            if isinstance(handler, dict) and handler.get("command") == group["hooks"][0]["command"]:
                fail("existing unmanaged Feishu Stop Hook found; remove or adopt it manually")
PY

mkdir -p "$CODEX_HOME/hooks" "$CODEX_HOME/log" "$PRIVATE_DIR"
chmod 700 "$CODEX_HOME/hooks" "$CODEX_HOME/log" "$PRIVATE_DIR"
install -m 755 "$PACKAGE_DIR/bin/codex_feishu_notify.py" "$TARGET_SCRIPT"

TEMP_CONFIG="$(mktemp "$PRIVATE_DIR/.config.json.XXXXXX")"
WEBHOOK_URL="$WEBHOOK_URL" \
SIGN_SECRET="$SIGN_SECRET" \
INCLUDE_SUMMARY="$INCLUDE_SUMMARY" \
INCLUDE_CWD="$INCLUDE_CWD" \
SUMMARY_MAX_CHARS="$SUMMARY_MAX_CHARS" \
TAG="$TAG" \
TEMP_CONFIG="$TEMP_CONFIG" \
python3 <<'PY'
import json
import os
from pathlib import Path

payload = {
    "enabled": True,
    "webhook_url": os.environ["WEBHOOK_URL"],
    "sign_secret": os.environ["SIGN_SECRET"],
    "tag": os.environ["TAG"],
    "include_summary": os.environ["INCLUDE_SUMMARY"].lower() == "true",
    "summary_max_chars": int(os.environ["SUMMARY_MAX_CHARS"]),
    "include_cwd": os.environ["INCLUDE_CWD"].lower() == "true",
}
Path(os.environ["TEMP_CONFIG"]).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
chmod 600 "$TEMP_CONFIG"
mv -f "$TEMP_CONFIG" "$PRIVATE_CONFIG"

HOOKS_FILE="$HOOKS_FILE" HOOK_STATE="$HOOK_STATE" TARGET_SCRIPT="$TARGET_SCRIPT" python3 <<'PY'
import json
import os
import shlex
import stat
import tempfile
from pathlib import Path


def fail(message: str) -> None:
    print(f"codex-feishu-hook: {message}", file=os.sys.stderr)
    raise SystemExit(2)


def load_json(path: Path, label: str, default: object) -> object:
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid {label}: {error}")


def write_json(path: Path, value: object, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
target_script = Path(os.environ["TARGET_SCRIPT"])
command = f"python3 {shlex.quote(str(target_script))}"
group = {
    "hooks": [
        {
            "type": "command",
            "command": command,
            "timeout": 5,
            "statusMessage": "Sending Feishu completion notification",
        }
    ]
}
hooks_value = load_json(hooks_path, "hooks JSON", {"hooks": {}})
if not isinstance(hooks_value, dict):
    fail("hooks.json root must be a JSON object")
hooks = hooks_value.setdefault("hooks", {})
if not isinstance(hooks, dict):
    fail("hooks.json hooks field must be a JSON object")
groups = hooks.setdefault("Stop", [])
if not isinstance(groups, list):
    fail("hooks.Stop must be a JSON array")
for existing_group in groups:
    if not isinstance(existing_group, dict) or not isinstance(existing_group.get("hooks"), list):
        fail("hooks.Stop entries must contain a hooks array")

state_value = load_json(state_path, "managed Hook state", None)
if state_value is not None:
    if not isinstance(state_value, dict) or state_value.get("hook_group") != group:
        fail("managed Hook state does not match this installation")
    if groups.count(group) != 1:
        fail("managed Feishu Stop Hook is missing or duplicated")
else:
    for existing_group in groups:
        for handler in existing_group["hooks"]:
            if isinstance(handler, dict) and handler.get("command") == command:
                fail("existing unmanaged Feishu Stop Hook found; remove or adopt it manually")
    groups.append(group)
    hooks_mode = stat.S_IMODE(hooks_path.stat().st_mode) if hooks_path.exists() else 0o600
    write_json(hooks_path, hooks_value, hooks_mode)
    write_json(state_path, {"version": 1, "hook_group": group}, 0o600)
PY

printf 'Installed notifier: %s\n' "$TARGET_SCRIPT"
printf 'Private config:    %s\n' "$PRIVATE_CONFIG"
printf 'User Hook config:  %s\n' "$HOOKS_FILE"
printf 'Restart Codex, then use /hooks to review and trust the new Stop Hook.\n'

if [[ "$SEND_TEST" == true ]]; then
  TEST_EVENT=$(printf '{"hook_event_name":"Stop","turn_id":"install-test","cwd":%s,"last_assistant_message":"Codex 飞书通知安装测试成功。"}' "$(python3 -c 'import json,os; print(json.dumps(os.getcwd()))')")
  printf '%s' "$TEST_EVENT" | CODEX_FEISHU_STRICT=1 CODEX_FEISHU_CONFIG="$PRIVATE_CONFIG" "$TARGET_SCRIPT"
  printf 'Test notification sent successfully.\n'
fi
