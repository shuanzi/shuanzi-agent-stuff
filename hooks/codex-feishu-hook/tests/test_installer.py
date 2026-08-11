from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
UNINSTALLER = ROOT / "uninstall.sh"
WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"


class InstallerTests(unittest.TestCase):
    def run_script(
        self,
        script: Path,
        home: Path,
        *args: str,
        input_text: str = "",
        expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["XDG_CONFIG_HOME"] = str(home / ".config")
        result = subprocess.run(
            ["bash", str(script), *args],
            cwd=ROOT,
            env=env,
            text=True,
            input=input_text,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    @staticmethod
    def install_answers(
        webhook: str = WEBHOOK,
        sign_secret: str = "",
        include_summary: str = "",
        include_cwd: str = "",
        summary_max_chars: str = "",
        tag: str = "",
        send_test: str = "",
    ) -> str:
        return "\n".join(
            [
                webhook,
                sign_secret,
                include_summary,
                include_cwd,
                summary_max_chars,
                tag,
                send_test,
            ]
        ) + "\n"

    @staticmethod
    def ottey_hooks() -> dict[str, object]:
        return {
            "hooks": {
                "Stop": [
                    {
                        "_otty": True,
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/Applications/Otty.app/Contents/Resources/otty-hook.sh idle",
                            }
                        ],
                    }
                ],
                "SessionStart": [
                    {
                        "_otty": True,
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/Applications/Otty.app/Contents/Resources/otty-hook.sh startup",
                            }
                        ],
                    }
                ],
            }
        }

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def feishu_stop_groups(hooks: dict[str, object]) -> list[dict[str, object]]:
        stop_groups = hooks["hooks"]["Stop"]
        return [
            group
            for group in stop_groups
            if any(
                "codex_feishu_notify.py" in handler.get("command", "")
                for handler in group.get("hooks", [])
            )
        ]

    def test_install_creates_private_config_and_user_stop_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_toml = home / ".codex" / "config.toml"
            hooks_json = home / ".codex" / "hooks.json"
            original_config = 'notify = ["/existing/notifier", "turn-ended"]\n'
            config_toml.parent.mkdir(parents=True)
            config_toml.write_text(original_config, encoding="utf-8")
            existing_hooks = self.ottey_hooks()
            self.write_json(hooks_json, existing_hooks)

            self.run_script(
                INSTALLER,
                home,
                input_text=self.install_answers(
                    sign_secret="test-secret",
                    include_summary="n",
                    include_cwd="y",
                    summary_max_chars="321",
                    tag=" P6 ",
                    send_test="n",
                ),
            )

            installed = home / ".codex" / "hooks" / "codex_feishu_notify.py"
            private_config = home / ".config" / "codex-feishu" / "config.json"
            hook_state = home / ".config" / "codex-feishu" / "user-hook-state.json"
            self.assertTrue(installed.exists())
            self.assertTrue(installed.stat().st_mode & stat.S_IXUSR)
            self.assertEqual(stat.S_IMODE(private_config.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(hook_state.stat().st_mode), 0o600)

            config = json.loads(private_config.read_text(encoding="utf-8"))
            self.assertEqual(config["webhook_url"], WEBHOOK)
            self.assertEqual(config["sign_secret"], "test-secret")
            self.assertFalse(config["include_summary"])
            self.assertTrue(config["include_cwd"])
            self.assertEqual(config["summary_max_chars"], 321)
            self.assertEqual(config["tag"], "P6")
            self.assertNotIn("title", config)
            self.assertNotIn("project_name", config)
            self.assertNotIn("timeout_seconds", config)

            self.assertEqual(config_toml.read_text(encoding="utf-8"), original_config)
            hooks = json.loads(hooks_json.read_text(encoding="utf-8"))
            self.assertEqual(hooks["hooks"]["Stop"][0], existing_hooks["hooks"]["Stop"][0])
            feishu_groups = self.feishu_stop_groups(hooks)
            self.assertEqual(len(feishu_groups), 1)
            handler = feishu_groups[0]["hooks"][0]
            self.assertEqual(handler["type"], "command")
            self.assertEqual(handler["timeout"], 5)
            self.assertIn(str(installed), handler["command"])

    def test_install_reprompts_invalid_interactive_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.run_script(
                INSTALLER,
                home,
                input_text="\n".join(
                    [
                        "http://invalid",
                        WEBHOOK,
                        "",
                        "maybe",
                        "n",
                        "maybe",
                        "n",
                        "4001",
                        "321",
                        "",
                        "maybe",
                        "n",
                    ]
                )
                + "\n",
            )

            config = json.loads(
                (home / ".config" / "codex-feishu" / "config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("Webhook URL 必须以 https:// 开头", result.stderr)
            self.assertEqual(result.stderr.count("请输入 y 或 n。"), 3)
            self.assertIn("摘要上限必须是 0～4000 的整数。", result.stderr)
            self.assertFalse(config["include_summary"])
            self.assertFalse(config["include_cwd"])
            self.assertEqual(config["summary_max_chars"], 321)

    def test_install_rejects_legacy_command_line_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.run_script(
                INSTALLER,
                home,
                "--webhook-url",
                WEBHOOK,
                expected=2,
            )

            self.assertIn("不接受命令行参数", result.stderr)
            self.assertFalse((home / ".config" / "codex-feishu").exists())

    def test_reinstall_is_idempotent_and_updates_private_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.run_script(INSTALLER, home, input_text=self.install_answers())
            installed = home / ".codex" / "hooks" / "codex_feishu_notify.py"
            installed.write_text("# old hook content\n", encoding="utf-8")
            installed.chmod(0o600)
            updated_webhook = WEBHOOK + "-updated"
            self.run_script(
                INSTALLER,
                home,
                input_text=self.install_answers(
                    webhook=updated_webhook,
                    tag=" P6 ",
                ),
            )

            hooks = json.loads(
                (home / ".codex" / "hooks.json").read_text(encoding="utf-8")
            )
            private_config = json.loads(
                (home / ".config" / "codex-feishu" / "config.json").read_text(
                    encoding="utf-8"
                )
            )
            feishu_groups = self.feishu_stop_groups(hooks)
            self.assertEqual(len(feishu_groups), 1)
            self.assertEqual(len(feishu_groups[0]["hooks"]), 1)
            self.assertEqual(
                installed.read_text(encoding="utf-8"),
                (ROOT / "bin" / "codex_feishu_notify.py").read_text(encoding="utf-8"),
            )
            self.assertTrue(installed.stat().st_mode & stat.S_IXUSR)
            self.assertEqual(private_config["webhook_url"], updated_webhook)
            self.assertEqual(private_config["tag"], "P6")
            self.assertTrue(private_config["include_cwd"])

    def test_install_ignores_existing_top_level_notify(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_toml = home / ".codex" / "config.toml"
            config_toml.parent.mkdir(parents=True)
            original = 'notify = ["bash", "/existing/notifier.sh"]\n[features]\nfoo = true\n'
            config_toml.write_text(original, encoding="utf-8")

            self.run_script(INSTALLER, home, input_text=self.install_answers())

            self.assertEqual(config_toml.read_text(encoding="utf-8"), original)
            self.assertTrue(
                (home / ".codex" / "hooks" / "codex_feishu_notify.py").exists()
            )
            self.assertTrue((home / ".codex" / "hooks.json").exists())

    def test_install_refuses_malformed_hooks_without_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            hooks_json = home / ".codex" / "hooks.json"
            hooks_json.parent.mkdir(parents=True)
            original = "{not valid json\n"
            hooks_json.write_text(original, encoding="utf-8")

            result = self.run_script(
                INSTALLER,
                home,
                input_text=self.install_answers(),
                expected=2,
            )

            self.assertIn("invalid hooks JSON", result.stderr)
            self.assertEqual(hooks_json.read_text(encoding="utf-8"), original)
            self.assertFalse(
                (home / ".codex" / "hooks" / "codex_feishu_notify.py").exists()
            )
            self.assertFalse((home / ".config" / "codex-feishu").exists())

    def test_install_refuses_unmanaged_matching_feishu_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            script_path = home / ".codex" / "hooks" / "codex_feishu_notify.py"
            hooks_json = home / ".codex" / "hooks.json"
            self.write_json(
                hooks_json,
                {
                    "hooks": {
                        "Stop": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": f"python3 {shlex.quote(str(script_path))}",
                                    }
                                ]
                            }
                        ]
                    }
                },
            )

            result = self.run_script(
                INSTALLER,
                home,
                input_text=self.install_answers(),
                expected=2,
            )

            self.assertIn("existing unmanaged Feishu Stop Hook", result.stderr)
            self.assertFalse((home / ".config" / "codex-feishu").exists())

    def test_uninstall_preserves_other_hooks_and_private_config_unless_purged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            hooks_json = home / ".codex" / "hooks.json"
            existing_hooks = self.ottey_hooks()
            self.write_json(hooks_json, existing_hooks)
            self.run_script(INSTALLER, home, input_text=self.install_answers())

            self.run_script(UNINSTALLER, home)
            self.assertFalse(
                (home / ".codex" / "hooks" / "codex_feishu_notify.py").exists()
            )
            self.assertFalse(
                (home / ".config" / "codex-feishu" / "user-hook-state.json").exists()
            )
            self.assertTrue(
                (home / ".config" / "codex-feishu" / "config.json").exists()
            )
            self.assertEqual(
                json.loads(hooks_json.read_text(encoding="utf-8")), existing_hooks
            )

            self.run_script(INSTALLER, home, input_text=self.install_answers())
            log_path = home / ".codex" / "log" / "feishu-notify.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("failure\n", encoding="utf-8")
            self.run_script(UNINSTALLER, home, "--purge")
            self.assertFalse((home / ".config" / "codex-feishu").exists())
            self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
