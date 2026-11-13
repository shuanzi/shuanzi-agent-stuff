import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


class InstallSkillsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="install-skills-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.skills = self.repo / "skills"
        self.skills.mkdir(parents=True)
        self.installer = self.repo / "install.sh"
        shutil.copyfile(INSTALLER, self.installer)
        self.agents = self.root / "agents"
        self.target = self.agents / "skills"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        for command in ("claude", "codex"):
            detected = self.bin / command
            detected.touch(mode=0o755)

    def make_skill(self, path, content="new"):
        (path / "references").mkdir(parents=True)
        (path / "SKILL.md").write_text(content)
        (path / "references" / "notes.md").write_text("nested")
        (path / ".DS_Store").write_text("fixture")
        (path / "references" / ".DS_Store").write_text("fixture")
        return path

    def run_installer(self, agents=None, answers="3\n2\nall\ny\n"):
        return subprocess.run(
            ["bash", str(self.installer)],
            input=answers,
            env={**self.env, "AGENTS_HOME": str(agents or self.agents)},
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_installs_regular_and_linked_skills_and_skips_invalid_entries(self):
        self.make_skill(self.skills / "ordinary")
        source = self.make_skill(self.root / "shared" / "linked")
        (self.skills / "linked").symlink_to(source, target_is_directory=True)
        (self.skills / "broken").symlink_to(self.root / "missing")
        (self.skills / "not-a-skill").mkdir()
        old = self.make_skill(self.target / "linked", "old")
        (old / "obsolete.md").write_text("old")

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("跳过失效的技能链接", result.stderr)
        self.assertEqual({p.name for p in self.target.iterdir()}, {"linked", "ordinary"})
        for name in ("linked", "ordinary"):
            installed = self.target / name
            self.assertFalse(installed.is_symlink())
            self.assertEqual((installed / "SKILL.md").read_text(), "new")
            self.assertEqual((installed / "references/notes.md").read_text(), "nested")
            self.assertEqual(list(installed.rglob(".DS_Store")), [])
        self.assertFalse((old / "obsolete.md").exists())
        self.assertTrue((source / ".DS_Store").is_file())

    def test_reports_empty_menu_with_only_broken_link(self):
        (self.skills / "broken").symlink_to(self.root / "missing")
        result = self.run_installer(answers="3\n2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("跳过失效的技能链接", result.stderr)
        self.assertFalse(self.target.exists())

    def test_installs_skill_through_worktree_home_link(self):
        home = self.root / "共享 Home"
        self.make_skill(home / ".agents/skills/shared")
        (self.repo / ".home-repo").symlink_to(home, target_is_directory=True)
        (self.skills / "shared").symlink_to("../.home-repo/.agents/skills/shared")

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "shared/SKILL.md").read_text(), "new")
        self.assertEqual((self.target / "shared/references/notes.md").read_text(), "nested")

    def test_requires_home_link_before_installing_skills(self):
        self.make_skill(self.skills / "ordinary")
        (self.skills / "shared").symlink_to("../.home-repo/.agents/skills/shared")

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("共享技能入口不可用", result.stderr)
        self.assertIn("home_paths.py link --repo shuanzi-agent-stuff --checkout", result.stderr)
        self.assertFalse(self.target.exists())

    def test_installs_selected_regular_skill_without_home_link(self):
        self.make_skill(self.skills / "ordinary")
        (self.skills / "shared").symlink_to("../.home-repo/.agents/skills/shared")

        result = self.run_installer(answers="3\n2\n1\ny\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2) shared", result.stdout)
        self.assertEqual({entry.name for entry in self.target.iterdir()}, {"ordinary"})

    def test_same_source_and_destination_is_a_noop(self):
        source = self.make_skill(self.skills / "same")
        result = self.run_installer(agents=self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("已指向同一来源", result.stdout)
        self.assertTrue((source / ".DS_Store").is_file())

    def test_preserves_link_to_same_source_through_aliased_parent(self):
        source = self.make_skill(self.root / "shared" / "linked")
        (self.skills / "linked").symlink_to(source, target_is_directory=True)
        self.target.mkdir(parents=True)
        link = self.target / "linked"
        link.symlink_to(source, target_is_directory=True)
        alias = self.root / "aliased-agents"
        alias.symlink_to(self.agents, target_is_directory=True)
        result = self.run_installer(agents=alias)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), source.resolve())
        self.assertTrue((source / ".DS_Store").is_file())

    def test_preserves_link_to_same_source_with_case_alias(self):
        source = self.make_skill(self.root / "shared" / "linked")
        case_alias = source.with_name("LINKED")
        if not case_alias.is_dir() or not case_alias.samefile(source):
            self.skipTest("文件系统区分大小写")
        (self.skills / "linked").symlink_to(source, target_is_directory=True)
        self.target.mkdir(parents=True)
        link = self.target / "linked"
        link.symlink_to(case_alias, target_is_directory=True)
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.readlink(), case_alias)

    def test_rejects_destination_ancestor_of_source(self):
        dest = self.target / "linked"
        source = self.make_skill(dest / "inner")
        (self.skills / "linked").symlink_to(source, target_is_directory=True)
        result = self.run_installer()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("安装目标重叠", result.stderr)
        self.assertEqual((source / "SKILL.md").read_text(), "new")

    def test_rejects_destination_ancestor_with_case_alias(self):
        source = self.make_skill(self.target / "linked" / "inner")
        case_alias = self.agents.with_name("AGENTS")
        if not case_alias.is_dir() or not case_alias.samefile(self.agents):
            self.skipTest("文件系统区分大小写")
        (self.skills / "linked").symlink_to(source, target_is_directory=True)
        result = self.run_installer(agents=case_alias)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("安装目标重叠", result.stderr)
        self.assertEqual((source / "SKILL.md").read_text(), "new")

    def test_rejects_destination_inside_source_through_missing_parent(self):
        source = self.make_skill(self.skills / "inside")
        alias = self.root / "source-alias"
        alias.symlink_to(source, target_is_directory=True)
        result = self.run_installer(agents=alias / "missing")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("安装目标重叠", result.stderr)
        self.assertFalse((source / "missing").exists())

    def test_preserves_existing_destination_when_source_disappears(self):
        self.make_skill(self.skills / "linked")
        old = self.make_skill(self.target / "linked", "old")
        fake_basename = self.bin / "basename"
        fake_basename.write_text(
            '#!/usr/bin/env bash\nmv -- "$1" "$1-removed"\nexec /usr/bin/basename "$@"\n'
        )
        fake_basename.chmod(0o755)
        result = self.run_installer()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("技能来源不可用", result.stderr)
        self.assertEqual((old / "SKILL.md").read_text(), "old")

    def test_copy_failure_keeps_existing_skill(self):
        self.make_skill(self.skills / "ordinary")
        old = self.make_skill(self.target / "ordinary", "old")
        fake_cp = self.bin / "cp"
        fake_cp.write_text(
            '#!/usr/bin/env bash\nmkdir -p -- "$4"\nprintf partial > "$4/SKILL.md"\nexit 9\n'
        )
        fake_cp.chmod(0o755)
        result = self.run_installer()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("安装 skill 失败", result.stderr)
        self.assertEqual((old / "SKILL.md").read_text(), "old")
        self.assertEqual(list(self.target.iterdir()), [old])


if __name__ == "__main__":
    unittest.main()
