from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "codex_feishu_notify.py"
SPEC = importlib.util.spec_from_file_location("codex_feishu_notify", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
notifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notifier)


class FakeResponse:
    def __init__(self, body: Union[dict[str, Any], str], status: int = 200) -> None:
        self.status = status
        self._body = body if isinstance(body, str) else json.dumps(body)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode("utf-8")


class NotifierTests(unittest.TestCase):
    def test_normalize_summary_removes_blank_lines_and_truncates(self) -> None:
        value = "  first  \n\n second line \n"
        self.assertEqual(notifier.normalize_summary(value, 14), "first\nsecond …")
        self.assertEqual(notifier.normalize_summary(None, 20), "")

    def test_make_feishu_sign_matches_reference_algorithm(self) -> None:
        timestamp = 1_700_000_000
        secret = "test-secret"
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        expected = base64.b64encode(
            hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        self.assertEqual(notifier.make_feishu_sign(timestamp, secret), expected)

    def test_load_event_supports_notify_argv_and_stop_stdin(self) -> None:
        notify_event = notifier.load_event(
            argv=["notifier", '{"type":"agent-turn-complete","turn-id":"t1"}'],
            stdin=io.StringIO(""),
        )
        self.assertEqual(notify_event["turn-id"], "t1")

        stop_event = notifier.load_event(
            argv=["notifier"],
            stdin=io.StringIO('{"hook_event_name":"Stop","turn_id":"t2"}'),
        )
        self.assertEqual(stop_event["turn_id"], "t2")

    def test_build_message_for_notify_is_privacy_bounded(self) -> None:
        event = {
            "type": "agent-turn-complete",
            "thread-id": "thread-secret",
            "turn-id": "1234567890abcdef",
            "cwd": "/work/android-to-harmonyos",
            "input-messages": ["private user prompt must not be sent"],
            "last-assistant-message": "Completed migration tests.\n\n86 tests passed.",
        }
        config = {
            "include_summary": True,
            "summary_max_chars": 600,
            "include_turn_id": True,
            "include_cwd": False,
        }
        now = datetime(2026, 7, 22, 15, 30, tzinfo=timezone.utc)

        message = notifier.build_message(event, config, now=now)

        self.assertIn("✅ Codex 本轮已完成", message)
        self.assertIn("项目：android-to-harmonyos", message)
        self.assertNotIn("\nTurn：", message)
        self.assertIn("Completed migration tests.", message)
        self.assertNotIn("private user prompt", message)
        self.assertNotIn("thread-secret", message)
        self.assertNotIn("/work/android-to-harmonyos", message)

    def test_build_message_ignores_legacy_custom_title(self) -> None:
        message = notifier.build_message(
            {"type": "agent-turn-complete", "cwd": "/work/sample"},
            {"title": "自定义标题", "summary_max_chars": 0},
            now=datetime(2026, 7, 22, 15, 30, tzinfo=timezone.utc),
        )

        self.assertTrue(message.startswith("✅ Codex 本轮已完成\n"))
        self.assertNotIn("自定义标题", message)

    def test_build_message_supports_stop_hook_fields(self) -> None:
        event = {
            "hook_event_name": "Stop",
            "turn_id": "stop-turn-001",
            "cwd": "/work/sample",
            "last_assistant_message": "Done",
        }
        config = {
            "include_summary": False,
            "include_cwd": True,
            "project_name": "Custom Project",
        }
        now = datetime(2026, 7, 22, 15, 30, tzinfo=timezone.utc)

        message = notifier.build_message(event, config, now=now)

        self.assertIn("项目：Custom Project", message)
        self.assertIn("目录：/work/sample", message)
        self.assertNotIn("Done", message)

    def test_build_message_includes_cwd_when_option_is_omitted(self) -> None:
        message = notifier.build_message(
            {
                "type": "agent-turn-complete",
                "cwd": "/workspace/codex-feishu-hook",
            },
            {"summary_max_chars": 0},
            now=datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc),
        )

        self.assertIn("目录：/workspace/codex-feishu-hook", message)

    def test_build_message_orders_metadata_and_ignores_legacy_turn_config(self) -> None:
        event = {
            "type": "agent-turn-complete",
            "turn-id": "1234567890abcdef",
            "cwd": "/work/sample",
        }
        now = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)

        for include_turn_id in (True, False):
            with self.subTest(include_turn_id=include_turn_id):
                message = notifier.build_message(
                    event,
                    {
                        "tag": "  P6\r\nrelease  ",
                        "include_turn_id": include_turn_id,
                        "include_cwd": True,
                        "summary_max_chars": 0,
                    },
                    now=now,
                )

                lines = message.splitlines()
                self.assertEqual(lines[1], "标签：P6 release")
                self.assertEqual(lines[2], "项目：sample")
                self.assertEqual(lines[3], "目录：/work/sample")
                self.assertTrue(lines[4].startswith("时间："))
                self.assertNotIn("\nTurn：", message)
                self.assertEqual(len(lines), 5)

    def test_build_message_omits_missing_or_blank_tag(self) -> None:
        event = {"type": "agent-turn-complete", "cwd": "/work/sample"}
        now = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)

        for config in ({}, {"tag": ""}, {"tag": " \t\n "}):
            with self.subTest(config=config):
                message = notifier.build_message(event, config, now=now)
                self.assertNotIn("标签：", message)

    def test_build_card_payload_adds_signature_when_configured(self) -> None:
        event = {
            "type": "agent-turn-complete",
            "turn-id": "turn-1",
            "cwd": "/work/sample",
            "last-assistant-message": "Done",
        }
        config = {
            "sign_secret": "secret",
            "tag": "P6",
            "include_summary": True,
            "summary_max_chars": 100,
            "include_turn_id": True,
        }
        now = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)

        payload = notifier.build_feishu_payload(event, config, now=now)

        self.assertEqual(payload["msg_type"], "interactive")
        self.assertEqual(payload["timestamp"], 1_700_000_000)
        self.assertEqual(
            payload["sign"], notifier.make_feishu_sign(1_700_000_000, "secret")
        )
        self.assertNotIn("content", payload)

        card = payload["card"]
        self.assertEqual(card["config"], {"wide_screen_mode": True})
        self.assertEqual(
            card["header"],
            {
                "title": {"tag": "plain_text", "content": "✅ Codex 本轮已完成"},
                "template": "green",
            },
        )
        self.assertEqual(
            [element["tag"] for element in card["elements"]],
            ["div", "hr", "div"],
        )
        metadata_lines = card["elements"][0]["text"]["content"].splitlines()
        self.assertEqual(metadata_lines[0], "**标签：** P6")
        self.assertEqual(metadata_lines[1], "**项目：** sample")
        self.assertEqual(metadata_lines[2], "**目录：** /work/sample")
        self.assertTrue(metadata_lines[3].startswith("**时间：** "))
        self.assertNotIn("Turn", card["elements"][0]["text"]["content"])
        self.assertIn("**结果摘要：**\nDone", card["elements"][2]["text"]["content"])

    def test_build_card_payload_omits_disabled_optional_fields(self) -> None:
        payload = notifier.build_feishu_payload(
            {
                "type": "agent-turn-complete",
                "turn-id": "turn-1",
                "cwd": "/work/sample",
                "last-assistant-message": "Done",
            },
            {
                "include_turn_id": False,
                "include_cwd": False,
                "include_summary": False,
            },
            now=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        )

        elements = payload["card"]["elements"]
        self.assertEqual([element["tag"] for element in elements], ["div"])
        content = elements[0]["text"]["content"]
        self.assertIn("**项目：** sample", content)
        self.assertNotIn("Turn", content)
        self.assertNotIn("目录", content)
        self.assertNotIn("Done", content)

    def test_build_card_payload_escapes_dynamic_lark_markdown(self) -> None:
        payload = notifier.build_feishu_payload(
            {
                "type": "agent-turn-complete",
                "cwd": "/work/project_[card]",
                "last-assistant-message": (
                    "<at id=all></at> **Done**\n"
                    "- [details](https://example.invalid)\n"
                    "1. First item"
                ),
            },
            {"include_cwd": True, "include_summary": True},
            now=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        )

        elements = payload["card"]["elements"]
        metadata = elements[0]["text"]["content"]
        summary = elements[2]["text"]["content"]
        self.assertIn(r"**项目：** project\_\[card\]", metadata)
        self.assertIn(r"**目录：** /work/project\_\[card\]", metadata)
        self.assertIn("&lt;at id=all&gt;&lt;/at&gt;", summary)
        self.assertIn(r"\*\*Done\*\*", summary)
        self.assertIn(r"\- \[details\]\(https://example.invalid\)", summary)
        self.assertIn(r"1\. First item", summary)
        self.assertNotIn("<at id=all>", summary)

    def test_build_card_payload_normalizes_and_escapes_tag_lark_markdown(self) -> None:
        payload = notifier.build_feishu_payload(
            {"type": "agent-turn-complete", "cwd": "/work/sample"},
            {
                "tag": "  <at id=all></at> **P6**\r\nTurn：forged\t[release]  ",
                "include_cwd": False,
            },
            now=datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc),
        )

        metadata = payload["card"]["elements"][0]["text"]["content"]
        lines = metadata.splitlines()
        self.assertEqual(
            lines[0],
            r"**标签：** &lt;at id=all&gt;&lt;/at&gt; \*\*P6\*\* Turn：forged \[release\]",
        )
        self.assertEqual(lines[1], "**项目：** sample")
        self.assertTrue(lines[2].startswith("**时间：** "))
        self.assertEqual(len(lines), 3)

    def test_post_feishu_accepts_new_and_legacy_success_responses(self) -> None:
        requests: list[Any] = []

        def opener(request: Any, timeout: float) -> FakeResponse:
            requests.append((request, timeout))
            return FakeResponse({"code": 0, "msg": "success"})

        result = notifier.post_feishu(
            "https://example.invalid/hook",
            {"msg_type": "text", "content": {"text": "hello"}},
            timeout=4,
            opener=opener,
        )
        self.assertEqual(result["code"], 0)
        self.assertEqual(requests[0][1], 4)
        self.assertEqual(requests[0][0].get_method(), "POST")

        legacy = notifier.post_feishu(
            "https://example.invalid/hook",
            {"msg_type": "text", "content": {"text": "hello"}},
            timeout=4,
            opener=lambda request, timeout: FakeResponse(
                {"StatusCode": 0, "StatusMessage": "success"}
            ),
        )
        self.assertEqual(legacy["StatusCode"], 0)

    def test_post_feishu_rejects_application_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Feishu rejected notification"):
            notifier.post_feishu(
                "https://example.invalid/hook",
                {"msg_type": "text", "content": {"text": "hello"}},
                timeout=4,
                opener=lambda request, timeout: FakeResponse(
                    {"code": 19021, "msg": "sign match fail or timestamp is not within one hour"}
                ),
            )

    def test_main_respects_xdg_config_home_and_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {
                "HOME": str(root / "home"),
                "XDG_CONFIG_HOME": str(root / "xdg"),
                "CODEX_HOME": str(root / "codex"),
            }
            with patch.object(notifier, "run", return_value="disabled") as mocked_run:
                result = notifier.main(
                    argv=["notifier", '{"type":"agent-turn-complete"}'],
                    stdin=io.StringIO(""),
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                    environ=env,
                )

            self.assertEqual(result, 0)
            expected = root / "xdg" / "codex-feishu" / "config.json"
            self.assertEqual(mocked_run.call_args.kwargs["config_path"], expected)

    def test_main_logs_failure_but_returns_zero_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "missing.json"
            log_path = Path(directory) / "notify.log"
            env = {
                "CODEX_FEISHU_CONFIG": str(config_path),
                "CODEX_FEISHU_LOG": str(log_path),
            }
            stderr = io.StringIO()
            result = notifier.main(
                argv=["notifier", '{"type":"agent-turn-complete"}'],
                stdin=io.StringIO(""),
                stdout=io.StringIO(),
                stderr=stderr,
                environ=env,
            )

            self.assertEqual(result, 0)
            self.assertTrue(log_path.exists())
            self.assertIn("FileNotFoundError", log_path.read_text(encoding="utf-8"))

    def test_main_strict_mode_returns_nonzero_and_stop_outputs_continue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "CODEX_FEISHU_CONFIG": str(Path(directory) / "missing.json"),
                "CODEX_FEISHU_LOG": str(Path(directory) / "notify.log"),
                "CODEX_FEISHU_STRICT": "1",
            }
            stdout = io.StringIO()
            result = notifier.main(
                argv=["notifier"],
                stdin=io.StringIO('{"hook_event_name":"Stop"}'),
                stdout=stdout,
                stderr=io.StringIO(),
                environ=env,
            )

            self.assertEqual(result, 1)
            self.assertEqual(json.loads(stdout.getvalue()), {"continue": True})

    def test_run_skips_disabled_and_unknown_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps({"enabled": False, "webhook_url": "https://invalid"}),
                encoding="utf-8",
            )
            sent: list[object] = []
            result = notifier.run(
                {"type": "agent-turn-complete"},
                config_path=config_path,
                opener=lambda *args, **kwargs: sent.append(args),
            )
            self.assertEqual(result, "disabled")
            self.assertEqual(sent, [])

            result = notifier.run(
                {"type": "other-event"},
                config_path=config_path,
                opener=lambda *args, **kwargs: sent.append(args),
            )
            self.assertEqual(result, "ignored")
            self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
