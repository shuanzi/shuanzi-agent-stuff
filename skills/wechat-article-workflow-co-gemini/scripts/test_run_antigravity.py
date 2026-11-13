"""对 Antigravity 调用器执行可控进程边界测试，不连接真实服务。"""

import contextlib
import io
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import run_antigravity as runner


CONVERSATION = "530fbfd5-c815-44b6-bf64-a8dd4067daa5"


def init_event(conversation=CONVERSATION, model="gemini-4-argon-high", effort=None):
    metadata = {"model": model, "permission_mode": "request-review"}
    if effort is not None:
        metadata["effort"] = effort
    return {"event": "init", "conversation_id": conversation, "init": metadata}


def result_event(success=True, conversation=CONVERSATION):
    # 与真实 CLI 烟测中观察到的终止事件保持一致。
    return {"event": "result", "result": {
        "conversation_id": conversation, "status": "SUCCESS" if success else "ERROR",
        "response": "已生成产物", "duration_seconds": 1.2, "num_turns": 1,
    }}


class AntigravityRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wechat-runner-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = self.root / "article"
        self.task.mkdir()
        self.prompt = self.task / "prompt.md"
        self.prompt.write_text("写一篇文章。", encoding="utf-8")
        self.fake = self.root / "agy"
        self.config = self.root / "fake-config.json"

        self.fake.write_text(
            "#!" + sys.executable + "\n" +
            """import json, os, pathlib, sys, time
config = json.loads(pathlib.Path(__file__).with_name('fake-config.json').read_text())
pathlib.Path('fake-invocation.json').write_text(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'pid': os.getpid()}))
for item in config.get('events', []):
    if isinstance(item, dict):
        print(json.dumps(item, ensure_ascii=False), flush=True)
    else:
        print(item, flush=True)
if config.get('partial_file'):
    pathlib.Path('partial.md').write_text('部分稿件', encoding='utf-8')
if config.get('stderr'):
    print(config['stderr'], file=sys.stderr, flush=True)
if config.get('sleep'):
    time.sleep(config['sleep'])
sys.exit(config.get('exit', 0))
""", encoding="utf-8")
        self.fake.chmod(0o700)

    def configure(self, events=None, **kwargs):
        self.config.write_text(json.dumps({"events": events or [], **kwargs}), encoding="utf-8")

    def invoke(self, conversation=None, timeout=3, cli=True):
        before = set((self.task / ".runs").iterdir()) if (self.task / ".runs").exists() else set()
        output = io.StringIO()
        with patch.object(runner.shutil, "which", return_value=str(self.fake) if cli else None), \
                contextlib.redirect_stdout(output):
            code = runner.run(self.task, self.prompt, conversation=conversation, timeout=timeout)
        created = set((self.task / ".runs").iterdir()) - before
        self.assertEqual(len(created), 1)
        run_dir = created.pop()
        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        return code, run_dir, status, output.getvalue()

    def observed_args(self):
        return json.loads((self.task / "fake-invocation.json").read_text())

    def test_success_passes_fixed_settings_and_does_not_interpret_prompt_as_shell(self):
        sentinel = self.root / "shell-was-executed"
        prompt = f"主题：$(touch {sentinel})；还有 `touch {sentinel}`。"
        self.prompt.write_text(prompt, encoding="utf-8")
        self.configure([init_event(), result_event()])

        code, run_dir, status, _ = self.invoke()

        self.assertEqual(code, 0)
        self.assertEqual(status["state"], "completed")
        self.assertFalse(status["article_accepted"])
        self.assertEqual(status["conversation_id"], CONVERSATION)
        self.assertEqual(status["observed_model"], "gemini-4-argon-high")
        self.assertFalse(sentinel.exists())
        observed = self.observed_args()
        args = observed["argv"]
        for option, value in (("--model", "gemini-4-argon-high"), ("--effort", "high"),
                              ("--mode", "accept-edits"), ("--output-format", "stream-json"),
                              ("--print", prompt)):
            self.assertEqual(args[args.index(option) + 1], value)
        self.assertNotIn("--dangerously-skip-permissions", args)
        self.assertEqual(Path(observed["cwd"]).resolve(), self.task.resolve())
        self.assertEqual((run_dir / "prompt.md").read_text(), prompt)
        self.assertEqual(json.loads((run_dir / "result.json").read_text()), result_event())

    def test_resume_uses_explicit_conversation_and_preserves_previous_run(self):
        self.configure([init_event(), result_event()])
        first_code, first_run, first_status, _ = self.invoke()
        original = {p.name: p.read_bytes() for p in first_run.iterdir()}
        self.prompt.write_text("按已经核验的意见修订。", encoding="utf-8")

        second_code, second_run, second_status, _ = self.invoke(conversation=CONVERSATION)

        self.assertEqual((first_code, second_code), (0, 0))
        self.assertNotEqual(first_run, second_run)
        self.assertEqual(first_status["conversation_id"], second_status["conversation_id"])
        args = self.observed_args()["argv"]
        self.assertEqual(args[args.index("--conversation") + 1], CONVERSATION)
        self.assertNotIn("--continue", args)
        self.assertEqual({p.name: p.read_bytes() for p in first_run.iterdir()}, original)
        request = json.loads((second_run / "request.json").read_text())
        self.assertEqual(request["requested_conversation_id"], CONVERSATION)

    def test_nonzero_exit_and_missing_or_error_result_are_failures(self):
        cases = [
            ([init_event(), result_event()], {"exit": 12, "stderr": "model unavailable"}),
            ([init_event()], {}),
            ([init_event(), result_event(success=False)], {}),
            ([init_event(), {"event": "result", "result": []}], {}),
            ([init_event(), {"event": "result"}], {}),
            ([init_event(), result_event(conversation="different-session")], {}),
        ]
        for events, options in cases:
            with self.subTest(events=events, options=options):
                self.configure(events, **options)
                code, run_dir, status, _ = self.invoke()
                self.assertNotEqual(code, 0)
                self.assertEqual(status["state"], "failed")
                self.assertTrue(status["error"])
                self.assertFalse(status["article_accepted"])
                if options.get("stderr"):
                    self.assertIn(options["stderr"], (run_dir / "stderr.log").read_text())

    def test_mismatched_model_effort_or_conversation_cannot_be_success(self):
        cases = [
            (init_event(model="some-other-model"), None),
            (init_event(effort="low"), None),
            (init_event(conversation="different-session"), CONVERSATION),
        ]
        for initial, requested in cases:
            with self.subTest(initial=initial, requested=requested):
                self.configure([initial, result_event()])
                code, _, status, _ = self.invoke(conversation=requested)
                self.assertNotEqual(code, 0)
                self.assertEqual(status["state"], "failed")
                self.assertTrue(status["error"])
                self.assertIsNone(status["conversation_id"])
                self.assertEqual(status["observed_conversation_id"], initial["conversation_id"])

    def test_missing_cli_records_failed_run(self):
        code, run_dir, status, _ = self.invoke(cli=False)
        self.assertNotEqual(code, 0)
        self.assertEqual(status["state"], "failed")
        self.assertIn("agy", status["error"])
        self.assertTrue((run_dir / "request.json").is_file())
        self.assertFalse(status["article_accepted"])

    def test_timeout_preserves_partial_file_and_observed_conversation(self):
        self.configure([init_event()], sleep=30, partial_file=True)
        code, run_dir, status, _ = self.invoke(timeout=0.5)
        self.assertNotEqual(code, 0)
        self.assertEqual(status["state"], "timed_out")
        self.assertEqual(status["conversation_id"], CONVERSATION)
        self.assertEqual((self.task / "partial.md").read_text(), "部分稿件")
        self.assertIn('"event": "init"', (run_dir / "stdout.jsonl").read_text())

    def test_malformed_protocol_is_failure_not_finished_running(self):
        for events in ([{"event": "init", "conversation_id": CONVERSATION, "init": "bad"}],
                       [init_event(), "not json", result_event()]):
            with self.subTest(events=events):
                self.configure(events)
                code, _, status, _ = self.invoke()
                self.assertNotEqual(code, 0)
                self.assertEqual(status["state"], "failed")
                self.assertTrue(status["finished_at"])

    def test_nonfinite_or_nonpositive_timeout_is_rejected(self):
        for timeout in (math.nan, math.inf, -math.inf, 0, -1):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    runner.run(self.task, self.prompt, timeout=timeout)
        self.assertFalse((self.task / ".runs").exists())

    def test_prompt_must_be_inside_task_directory(self):
        outside = self.root / "outside.md"
        outside.write_text("不应发送", encoding="utf-8")
        with self.assertRaises(ValueError):
            runner.run(self.task, outside)
        self.assertFalse((self.task / ".runs").exists())

    def test_sigterm_finalizes_status_and_stops_cli_process(self):
        self.configure([init_event()], sleep=30, partial_file=True)
        env = os.environ.copy()
        env["PATH"] = str(self.root) + os.pathsep + env.get("PATH", "")
        wrapper = subprocess.Popen(
            [sys.executable, str(Path(runner.__file__).resolve()), "--task-dir", str(self.task),
             "--prompt-file", str(self.prompt), "--timeout", "20"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )
        self.addCleanup(lambda: wrapper.poll() is None and wrapper.kill())
        deadline = time.monotonic() + 5
        state_path = None
        while time.monotonic() < deadline:
            states = list((self.task / ".runs").glob("*/status.json"))
            if states and (self.task / "partial.md").exists():
                candidate = json.loads(states[0].read_text())
                if candidate.get("conversation_id") == CONVERSATION:
                    state_path = states[0]
                    break
            if wrapper.poll() is not None:
                self.fail(f"包装器提前退出：{wrapper.communicate()}")
            time.sleep(0.02)
        self.assertIsNotNone(state_path, "假 CLI 未在时限内完成 init 和部分写入")
        fake_pid = self.observed_args()["pid"]
        self.addCleanup(self.kill_if_running, fake_pid)

        wrapper.send_signal(signal.SIGTERM)
        stdout, stderr = wrapper.communicate(timeout=8)

        self.assertNotEqual(wrapper.returncode, 0, (stdout, stderr))
        status = json.loads(state_path.read_text())
        self.assertEqual(status["state"], "interrupted")
        self.assertEqual(status["conversation_id"], CONVERSATION)
        self.assertEqual((self.task / "partial.md").read_text(), "部分稿件")
        with self.assertRaises(ProcessLookupError):
            os.kill(fake_pid, 0)

    @staticmethod
    def kill_if_running(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    unittest.main()
