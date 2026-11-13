#!/usr/bin/env python3
"""在文章目录调用指定 Gemini，保存可恢复的运行证据；不代替内容验收。"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import time
import uuid


MODEL = "gemini-4-argon-high"
EFFORT = "high"


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def command(executable, prompt, conversation):
    args = [executable, "--model", MODEL, "--effort", EFFORT,
            "--mode", "accept-edits", "--disable-slash-commands",
            "--output-format", "stream-json"]
    if conversation:
        args.extend(["--conversation", conversation])
    return args + ["--print", prompt]


def stop_process(process):
    """终止本次本地进程组；远端会话是否停止仍需核对。"""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run(task_dir, prompt_file, conversation=None, timeout=900):
    task_dir = Path(task_dir).resolve(strict=True)
    prompt_file = Path(prompt_file).resolve(strict=True)
    if not task_dir.is_dir() or task_dir not in prompt_file.parents:
        raise ValueError("提示文件必须位于现有文章任务目录内")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout 必须是大于 0 的有限秒数")
    if conversation and (conversation.startswith("-") or any(c.isspace() for c in conversation)):
        raise ValueError("conversation 必须是明确的单个会话 ID")
    prompt = prompt_file.read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError("提示文件不能为空")
    runs = task_dir / ".runs"
    if runs.is_symlink():
        raise ValueError(".runs 不能是软链接")
    runs.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = runs / run_id
    run_dir.mkdir(mode=0o700)
    (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    executable = shutil.which("agy")
    request = {
        "run_id": run_id, "task_dir": str(task_dir), "prompt_file": str(prompt_file),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "requested_model": MODEL, "requested_effort": EFFORT, "mode": "accept-edits",
        "requested_conversation_id": conversation, "timeout_seconds": timeout,
        "executable": executable,
    }
    write_json(run_dir / "request.json", request)
    status = {
        "run_id": run_id, "run_dir": str(run_dir), "state": "running",
        "started_at": now(), "conversation_id": None, "observed_model": None,
        "observed_conversation_id": None,
        "observed_effort": None, "last_event": None, "last_output_at": None,
        "returncode": None, "error": None, "article_accepted": False,
    }
    result = None
    process = None
    buffer = b""
    protocol_errors = []
    started = time.monotonic()

    def save_status():
        status["updated_at"] = now()
        write_json(run_dir / "status.json", status)

    def receive(line):
        nonlocal result
        if not line.strip():
            return
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            protocol_errors.append("stdout 含非 JSON 事件，见 stdout.jsonl")
            return
        if not isinstance(event, dict):
            protocol_errors.append("stdout 事件不是 JSON 对象")
            return
        kind = event.get("event")
        status["last_event"] = kind
        if kind == "init":
            init = event.get("init")
            if not isinstance(init, dict):
                raise RuntimeError("CLI init 事件格式异常，见 stdout.jsonl")
            observed_id = event.get("conversation_id")
            status["observed_conversation_id"] = observed_id
            status["observed_model"] = init.get("model")
            status["observed_effort"] = init.get("effort")
            status["observed_permission_mode"] = init.get("permission_mode")
            if status["observed_model"] != MODEL:
                raise RuntimeError("CLI 回报的模型与指定模型不符，停止本次调用")
            if status["observed_effort"] not in (None, EFFORT):
                raise RuntimeError("CLI 回报的思考深度与 high 不符，停止本次调用")
            if not isinstance(observed_id, str) or not observed_id.strip():
                raise RuntimeError("CLI 初始化事件缺少会话 ID")
            if conversation and observed_id != conversation:
                raise RuntimeError("CLI 恢复了不同的会话，停止本次调用")
            if status["conversation_id"] and observed_id != status["conversation_id"]:
                raise RuntimeError("CLI 在同一运行中更换了会话，停止本次调用")
            status["conversation_id"] = observed_id
        elif kind == "result":
            result = event
            write_json(run_dir / "result.json", event)
        elif kind == "error":
            protocol_errors.append("CLI 返回 error 事件，见 stdout.jsonl")
        save_status()

    save_status()
    print(json.dumps(status, ensure_ascii=False), flush=True)
    try:
        if not executable:
            raise RuntimeError("PATH 中找不到 agy；请安装或配置 Antigravity CLI 后重试")
        with (run_dir / "stdout.jsonl").open("wb") as stdout_log, \
                (run_dir / "stderr.log").open("wb") as stderr_log, \
                selectors.DefaultSelector() as selector:
            process = subprocess.Popen(
                command(executable, prompt, conversation), cwd=task_dir,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,
            )
            status["pid"] = process.pid
            save_status()
            selector.register(process.stdout, selectors.EVENT_READ, stdout_log)
            selector.register(process.stderr, selectors.EVENT_READ, stderr_log)
            last_heartbeat = time.monotonic()
            while selector.get_map():
                if time.monotonic() - started >= timeout:
                    raise TimeoutError("达到本次调用时限；保留会话和产物，续办前核对会话状态")
                for key, _ in selector.select(timeout=min(1, max(0, timeout - (time.monotonic() - started)))):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    key.data.write(chunk)
                    key.data.flush()
                    status["last_output_at"] = now()
                    if key.fileobj is process.stdout:
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            receive(line)
                if time.monotonic() - last_heartbeat >= 30:
                    save_status()
                    print(json.dumps({"state": "running", "run_dir": str(run_dir),
                                      "conversation_id": status["conversation_id"],
                                      "last_event": status["last_event"]}, ensure_ascii=False), flush=True)
                    last_heartbeat = time.monotonic()
            if buffer.strip():
                receive(buffer)
                buffer = b""
            process.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
        status["returncode"] = process.returncode
        if process.returncode != 0:
            raise RuntimeError(f"agy 退出码为 {process.returncode}，见 stderr.log 与 stdout.jsonl")
        if protocol_errors:
            raise RuntimeError("；".join(dict.fromkeys(protocol_errors)))
        if not status["conversation_id"] or status["observed_model"] != MODEL:
            raise RuntimeError("缺少可核对模型与会话的 init 事件")
        if result is None:
            raise RuntimeError("CLI 未返回完成结果；不能仅凭退出码 0 认定完成")
        outcome = result.get("result")
        if not isinstance(outcome, dict) or outcome.get("status") != "SUCCESS":
            raise RuntimeError("CLI 终止结果不是 SUCCESS，见 result.json")
        if outcome.get("conversation_id") != status["conversation_id"]:
            raise RuntimeError("CLI 终止结果的会话 ID 与初始化不符")
        status["state"] = "completed"
    except (TimeoutError, subprocess.TimeoutExpired) as exc:
        status["state"] = "timed_out"
        status["error"] = str(exc)
    except KeyboardInterrupt:
        status["state"] = "interrupted"
        status["error"] = "本地调用已中断；续办前核对会话与已有产物"
    except (OSError, RuntimeError) as exc:
        status["state"] = "failed"
        status["error"] = str(exc)
    finally:
        if process is not None:
            if status["state"] != "completed":
                stop_process(process)
            status["returncode"] = process.returncode
            for pipe in (process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        status["finished_at"] = now()
        save_status()
    print(json.dumps(status, ensure_ascii=False), flush=True)
    return 0 if status["state"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--conversation", help="从该文章运行记录取得的明确会话 ID")
    parser.add_argument("--timeout", type=float, default=900, help="单次调用时限秒数，默认 900")
    args = parser.parse_args()
    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        return run(args.task_dir, args.prompt_file, args.conversation, args.timeout)
    except (OSError, ValueError) as exc:
        print(f"无法启动：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
