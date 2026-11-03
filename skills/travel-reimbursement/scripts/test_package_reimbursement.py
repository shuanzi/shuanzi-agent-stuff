"""差旅 ZIP 的合成数据测试；所有生成物限于临时目录。"""

import base64
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.dom import minidom
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("package_reimbursement", HERE / "package_reimbursement.py")
pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pack)
FORM_SPEC = importlib.util.spec_from_file_location("fill_domestic_form", HERE / "fill_domestic_form.py")
form = importlib.util.module_from_spec(FORM_SPEC)
FORM_SPEC.loader.exec_module(form)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=")


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.work = self.root / "work"
        self.work.mkdir()
        self.manifest_path = self.work / "组秘包清单.json"
        self.output_dir = self.root / "output"
        self.form_path = self.work / "差旅报销单_草稿.docx"
        form.fill({
            "filled_on": "2026-11-03", "department": "测试部门", "group": "测试课题组",
            "route": "北京→上海市黄浦区→北京", "start_date": "2026-10-28",
            "end_date": "2026-10-30", "purpose": "测试人员参加技术交流", "account": "",
            "rows": [{"traveler": "测试甲", "transport_mode": "高铁", "transport": "100.10",
                      "lodging": "0", "misc": "0", "meal": "0", "local": "0"}],
            "payments": {"official_card": "100.10", "bank_card": "0", "company_transfer": "0",
                         "cheque": "0", "cash": "0"},
        }, self.form_path)
        self.payment = self.root / "去程付款.png"
        self.payment.write_bytes(PNG)
        self.manifest = {
            "title": "测试甲申请上海出差（20261028-20261030）技术交流", "blockers": [],
            "files": [
                {"source": self.form_path.name, "name": self.form_path.name, "role": "form"},
                {"source": "../去程付款.png", "name": "测试甲_去程_支付截图.png", "role": "attachment"},
            ],
        }

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")
        return self.manifest_path

    def test_chinese_files_round_trip_and_filled_word_amount(self):
        before = {self.form_path: self.form_path.read_bytes(), self.payment: self.payment.read_bytes()}
        output = pack.package(self.write_manifest(), self.output_dir)
        self.assertEqual(output, self.output_dir / f"{self.manifest['title']}.zip")
        with ZipFile(output) as archive:
            expected = [f"{self.manifest['title']}/{item['name']}" for item in self.manifest["files"]]
            self.assertEqual(archive.namelist(), expected)
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read(expected[1]), PNG)
            with ZipFile(io.BytesIO(archive.read(expected[0]))) as word:
                doc = minidom.parseString(word.read("word/document.xml"))
                text = form.plain_text(doc)
                self.assertIn("测试甲", text)
                self.assertIn("100.10", text)
        for source, content in before.items():
            self.assertEqual(source.read_bytes(), content)

    def test_missing_file_can_be_supplied_and_retried(self):
        self.manifest["files"].append({"source": "../回程付款.png", "name": "测试甲_回程_支付截图.png",
                                       "role": "attachment"})
        with self.assertRaises(FileNotFoundError):
            pack.package(self.write_manifest(), self.output_dir)
        self.assertFalse(self.output_dir.exists())
        (self.root / "回程付款.png").write_bytes(PNG)
        output = pack.package(self.manifest_path, self.output_dir)
        with ZipFile(output) as archive:
            self.assertEqual(len(archive.infolist()), 3)

    def test_blockers_refuse_package_until_resolved(self):
        self.manifest["blockers"] = ["回程付款截图疑似属于另一趟行程"]
        with self.assertRaisesRegex(ValueError, "仍有缺件或冲突"):
            pack.package(self.write_manifest(), self.output_dir)
        self.assertFalse(self.output_dir.exists())
        self.manifest["blockers"] = []
        self.assertTrue(pack.package(self.write_manifest(), self.output_dir).is_file())

    def test_duplicate_names_include_unicode_and_case_aliases(self):
        for names in (("凭证.png", "凭证.png"), ("PAY.png", "pay.png"), ("café.png", "cafe\u0301.png")):
            with self.subTest(names=names):
                self.manifest["files"][0]["name"], self.manifest["files"][1]["name"] = names
                with self.assertRaisesRegex(ValueError, "重复"):
                    pack.package(self.write_manifest(), self.output_dir)
                self.assertFalse(self.output_dir.exists())

    def test_invalid_archive_names_and_title(self):
        original = copy.deepcopy(self.manifest)
        for value in ("../外部.png", "sub/file.png", "sub\\file.png", "", ".", "..", "x\n.png",
                      "x\x7f.png", "x:1.png", "x?.png", "CON", "LPT9.txt", "尾点.", "尾空 "):
            for field in ("title", "name"):
                with self.subTest(value=value, field=field):
                    self.manifest = copy.deepcopy(original)
                    if field == "title":
                        self.manifest["title"] = value
                    else:
                        self.manifest["files"][1]["name"] = value
                    with self.assertRaises(ValueError):
                        pack.package(self.write_manifest(), self.output_dir)
                    self.assertFalse(self.output_dir.exists())

    def test_empty_file_and_directory_are_rejected(self):
        for source in (self.root / "empty.pdf", self.root / "folder"):
            with self.subTest(source=source.name):
                if source.suffix:
                    source.touch()
                else:
                    source.mkdir()
                self.manifest["files"][1]["source"] = str(source)
                with self.assertRaises(ValueError):
                    pack.package(self.write_manifest(), self.output_dir)
                self.assertFalse(self.output_dir.exists())

    def test_existing_zip_is_preserved(self):
        output = pack.package(self.write_manifest(), self.output_dir)
        before = output.read_bytes()
        with self.assertRaises(FileExistsError):
            pack.package(self.manifest_path, self.output_dir)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(list(self.output_dir.iterdir()), [output])

    def test_concurrent_publication_preserves_winner_and_cleans_temporary(self):
        output = self.output_dir / f"{self.manifest['title']}.zip"

        def rival_wins(source, destination):
            destination.write_bytes(b"rival result")
            raise FileExistsError("concurrent result exists")

        with patch.object(pack.os, "link", side_effect=rival_wins):
            with self.assertRaises(FileExistsError):
                pack.package(self.write_manifest(), self.output_dir)
        self.assertEqual(output.read_bytes(), b"rival result")
        self.assertEqual(list(self.output_dir.iterdir()), [output])

    def test_zip_verification_failure_leaves_no_output(self):
        with patch.object(pack.ZipFile, "testzip", return_value="corrupt.png"):
            with self.assertRaisesRegex(ValueError, "CRC"):
                pack.package(self.write_manifest(), self.output_dir)
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_manifest_requires_explicit_blockers_and_form(self):
        original = copy.deepcopy(self.manifest)
        for change in ({"blockers": None}, {"files": []}, {"files": [original["files"][1]]},
                       {"files": [{**original["files"][0], "role": "unknown"}]}, {"extra": True}):
            with self.subTest(change=change):
                self.manifest = {**original, **change}
                with self.assertRaises(ValueError):
                    pack.package(self.write_manifest(), self.output_dir)
                self.assertFalse(self.output_dir.exists())
        self.manifest = copy.deepcopy(original)
        del self.manifest["blockers"]
        with self.assertRaises(ValueError):
            pack.package(self.write_manifest(), self.output_dir)

    def test_cli_handles_success_and_blockers(self):
        command = [sys.executable, str(HERE / "package_reimbursement.py"), "--manifest",
                   str(self.write_manifest()), "--output-dir", str(self.output_dir)]
        success = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertTrue(Path(json.loads(success.stdout)["文件"]).is_file())
        self.manifest["blockers"] = ["缺回程截图"]
        self.write_manifest()
        blocked = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("仍有缺件或冲突", blocked.stderr)


if __name__ == "__main__":
    unittest.main()
