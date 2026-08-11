from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "codex_feishu_notify.py"


class CaptureHandler(BaseHTTPRequestHandler):
    payloads: ClassVar[list[dict[str, object]]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        self.__class__.payloads.append(json.loads(body))
        response = json.dumps({"code": 0, "msg": "success"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        return


class HttpIntegrationTests(unittest.TestCase):
    def test_cli_posts_one_privacy_bounded_message_to_http_server(self) -> None:
        CaptureHandler.payloads = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            with tempfile.TemporaryDirectory() as directory:
                config_path = Path(directory) / "config.json"
                config_path.write_text(
                    json.dumps(
                        {
                            "enabled": True,
                            "webhook_url": (
                                f"http://127.0.0.1:{server.server_port}/hook"
                            ),
                            "include_summary": True,
                            "summary_max_chars": 200,
                            "include_cwd": False,
                            "timeout_seconds": 2,
                        }
                    ),
                    encoding="utf-8",
                )
                event = json.dumps(
                    {
                        "type": "agent-turn-complete",
                        "turn-id": "integration-turn",
                        "cwd": "/tmp/integration-project",
                        "input-messages": ["private prompt"],
                        "last-assistant-message": "All integration checks passed.",
                    }
                )
                env = os.environ.copy()
                env["CODEX_FEISHU_CONFIG"] = str(config_path)
                env["CODEX_FEISHU_STRICT"] = "1"
                result = subprocess.run(
                    ["python3", str(SCRIPT), event],
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(CaptureHandler.payloads), 1)
            payload = CaptureHandler.payloads[0]
            self.assertEqual(payload["msg_type"], "interactive")
            card = payload["card"]  # type: ignore[assignment]
            elements = card["elements"]  # type: ignore[index]
            text = "\n".join(
                element.get("text", {}).get("content", "") for element in elements
            )
            self.assertIn("**项目：** integration-project", text)
            self.assertIn("All integration checks passed.", text)
            self.assertNotIn("Turn", text)
            self.assertNotIn("private prompt", text)
            self.assertNotIn("/tmp/integration-project", text)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
