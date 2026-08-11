#!/usr/bin/env python3
"""Codex Stop Hook notifier for Feishu custom bots.

The installed Hook reads its event JSON from stdin. Runtime failures are logged
and are non-blocking by default so a notification outage cannot fail a Codex turn.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, IO, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_CONFIG_PATH = Path("~/.config/codex-feishu/config.json").expanduser()
DEFAULT_LOG_PATH = Path("~/.codex/log/feishu-notify.log").expanduser()
SUPPORTED_EVENTS = {"agent-turn-complete", "Stop"}


def normalize_summary(value: Any, max_chars: int) -> str:
    """Normalize assistant output while enforcing a hard character limit."""
    if not isinstance(value, str) or max_chars <= 0:
        return ""

    lines = [line.strip() for line in value.splitlines()]
    summary = "\n".join(line for line in lines if line)
    if len(summary) <= max_chars:
        return summary

    if max_chars == 1:
        return "…"

    prefix = summary[: max_chars - 1]
    if prefix and prefix[-1].isspace():
        return prefix.rstrip() + " …"
    return prefix.rstrip() + "…"


def escape_lark_markdown(value: str) -> str:
    """Render dynamic content literally inside a Feishu ``lark_md`` field."""
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for character in "\\`*_{}[]()!|~":
        escaped = escaped.replace(character, f"\\{character}")
    escaped = re.sub(
        r"(?m)^(\s{0,3})([#>+\-])\s",
        r"\1\\\2 ",
        escaped,
    )
    return re.sub(
        r"(?m)^(\s{0,3})(\d+)\.\s",
        r"\g<1>\g<2>\\. ",
        escaped,
    )


def make_feishu_sign(timestamp: int, secret: str) -> str:
    """Create the signature expected by a signed Feishu custom bot."""
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def load_event(argv: Optional[list[str]] = None, stdin: Optional[IO[str]] = None) -> Dict[str, Any]:
    """Load a Codex event from argv or stdin for Hook and test compatibility."""
    args = list(sys.argv if argv is None else argv)
    input_stream = sys.stdin if stdin is None else stdin

    raw = args[1] if len(args) > 1 else input_stream.read()
    if not raw or not raw.strip():
        raise ValueError("Codex event payload is empty")

    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Codex event payload must be a JSON object")
    return value


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def event_kind(event: Mapping[str, Any]) -> str:
    value = event.get("type") or event.get("hook_event_name") or ""
    return str(value)


def event_field(
    event: Mapping[str, Any],
    notify_name: str,
    stop_name: str,
    default: Any = "",
) -> Any:
    value = event.get(notify_name)
    if value is None:
        value = event.get(stop_name)
    return default if value is None else value


def _current_time(now: Optional[datetime]) -> datetime:
    if now is not None:
        return now.astimezone()
    return datetime.now().astimezone()


def _message_parts(
    event: Mapping[str, Any],
    config: Mapping[str, Any],
    current: datetime,
) -> tuple[str, list[tuple[str, str]], str]:
    """Build shared notification content for text and card renderers."""
    cwd = str(event.get("cwd") or "")
    configured_project = str(config.get("project_name") or "").strip()
    project = configured_project or (Path(cwd).name if cwd else "Unknown project")
    tag = " ".join(str(config.get("tag") or "").split())

    assistant_message = event_field(
        event,
        "last-assistant-message",
        "last_assistant_message",
        "",
    )

    try:
        max_chars = int(config.get("summary_max_chars", 600))
    except (TypeError, ValueError) as error:
        raise ValueError("summary_max_chars must be an integer") from error
    if not 0 <= max_chars <= 4000:
        raise ValueError("summary_max_chars must be between 0 and 4000")

    summary = normalize_summary(assistant_message, max_chars)
    if not bool(config.get("include_summary", True)):
        summary = ""

    title = "✅ Codex 本轮已完成"
    fields = []
    if tag:
        fields.append(("标签", tag))

    fields.append(("项目", project))

    if cwd and bool(config.get("include_cwd", True)):
        fields.append(("目录", cwd))

    fields.append(("时间", current.strftime("%Y-%m-%d %H:%M:%S %Z")))

    return title, fields, summary


def build_message(
    event: Mapping[str, Any],
    config: Mapping[str, Any],
    now: Optional[datetime] = None,
) -> str:
    """Render a text message without including user prompts or transcripts."""
    current = _current_time(now)
    title, fields, summary = _message_parts(event, config, current)
    lines = [title, *(f"{label}：{value}" for label, value in fields)]

    if summary:
        lines.extend(["", "结果摘要：", summary])

    return "\n".join(lines)


def build_feishu_payload(
    event: Mapping[str, Any],
    config: Mapping[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    current = _current_time(now)
    title, fields, summary = _message_parts(event, config, current)
    elements: list[Dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(
                    f"**{label}：** {escape_lark_markdown(value)}"
                    for label, value in fields
                ),
            },
        }
    ]
    if summary:
        elements.extend(
            [
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**结果摘要：**\n{escape_lark_markdown(summary)}"
                        ),
                    },
                },
            ]
        )

    payload: Dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "green",
            },
            "elements": elements,
        },
    }

    sign_secret = str(config.get("sign_secret") or "")
    if sign_secret:
        timestamp = int(current.timestamp())
        payload["timestamp"] = timestamp
        payload["sign"] = make_feishu_sign(timestamp, sign_secret)

    return payload


def _validate_feishu_result(result: Mapping[str, Any]) -> None:
    code = result.get("code")
    if code is None:
        code = result.get("StatusCode", 0)
    if code not in (0, "0", None):
        message = result.get("msg") or result.get("StatusMessage") or result
        raise RuntimeError(f"Feishu rejected notification: {code}: {message}")


def post_feishu(
    webhook_url: str,
    payload: Mapping[str, Any],
    timeout: float,
    opener: Callable[..., Any] = urlopen,
) -> Dict[str, Any]:
    """POST one message and validate both current and legacy Feishu replies."""
    if not webhook_url.startswith(("https://", "http://")):
        raise ValueError("webhook_url must start with https:// or http://")
    if not 0 < timeout <= 30:
        raise ValueError("timeout_seconds must be greater than 0 and at most 30")

    request = Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "codex-feishu-hook/1.0",
        },
        method="POST",
    )

    try:
        with opener(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Feishu HTTP error {error.code}: {body}") from error
    except URLError as error:
        raise RuntimeError(f"Feishu connection error: {error}") from error

    if not response_body.strip():
        return {}

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Feishu returned non-JSON content: {response_body[:300]}"
        ) from error
    if not isinstance(result, dict):
        raise RuntimeError("Feishu returned a non-object JSON response")

    _validate_feishu_result(result)
    return result


def run(
    event: Mapping[str, Any],
    config_path: Optional[Path] = None,
    opener: Callable[..., Any] = urlopen,
    now: Optional[datetime] = None,
) -> str:
    """Process one event. Exceptions are handled by ``main``."""
    if event_kind(event) not in SUPPORTED_EVENTS:
        return "ignored"

    path = DEFAULT_CONFIG_PATH if config_path is None else config_path
    config = load_config(path)
    if not bool(config.get("enabled", True)):
        return "disabled"

    webhook_url = str(config.get("webhook_url") or "").strip()
    if not webhook_url:
        raise ValueError("webhook_url is missing")

    try:
        timeout = float(config.get("timeout_seconds", 4))
    except (TypeError, ValueError) as error:
        raise ValueError("timeout_seconds must be numeric") from error

    payload = build_feishu_payload(event, config, now=now)
    post_feishu(webhook_url, payload, timeout=timeout, opener=opener)
    return "sent"


def log_error(error: BaseException, path: Path) -> None:
    """Best-effort local logging with a small single-file rotation."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 1_000_000:
            rotated = path.with_name(path.name + ".1")
            try:
                rotated.unlink()
            except FileNotFoundError:
                pass
            path.replace(rotated)

        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as file:
            file.write(f"{timestamp} {type(error).__name__}: {error}\n")
    except OSError:
        pass


def _env_path(environ: Mapping[str, str], key: str, default: Path) -> Path:
    raw = environ.get(key)
    return Path(raw).expanduser() if raw else default


def _default_paths(environ: Mapping[str, str]) -> tuple[Path, Path]:
    home = Path(environ.get("HOME") or str(Path.home())).expanduser()
    xdg_config_home = Path(
        environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    ).expanduser()
    codex_home = Path(environ.get("CODEX_HOME") or str(home / ".codex")).expanduser()
    return (
        xdg_config_home / "codex-feishu" / "config.json",
        codex_home / "log" / "feishu-notify.log",
    )


def main(
    argv: Optional[list[str]] = None,
    stdin: Optional[IO[str]] = None,
    stdout: Optional[IO[str]] = None,
    stderr: Optional[IO[str]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    """CLI entry point; non-blocking by default, strict when explicitly asked."""
    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
    environment = os.environ if environ is None else environ
    strict = environment.get("CODEX_FEISHU_STRICT", "").lower() in {
        "1",
        "true",
        "yes",
    }
    event: Dict[str, Any] = {}
    result = 0

    try:
        event = load_event(argv=argv, stdin=stdin)
        default_config_path, default_log_path = _default_paths(environment)
        config_path = _env_path(
            environment, "CODEX_FEISHU_CONFIG", default_config_path
        )
        run(event, config_path=config_path)
    except Exception as error:  # The notification path must not block Codex.
        _, default_log_path = _default_paths(environment)
        log_path = _env_path(environment, "CODEX_FEISHU_LOG", default_log_path)
        log_error(error, log_path)
        if strict:
            print(f"codex-feishu-hook: {type(error).__name__}: {error}", file=error_output)
            result = 1
    finally:
        if event_kind(event) == "Stop":
            json.dump({"continue": True}, output, ensure_ascii=False)
            output.write("\n")

    return result


if __name__ == "__main__":
    raise SystemExit(main())
