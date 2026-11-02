"""国内差旅表的合成数据回归测试；不使用真实个人或票据。"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.dom import minidom
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "差旅报销单.docx"
SPEC = importlib.util.spec_from_file_location("fill_domestic_form", HERE / "fill_domestic_form.py")
form = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(form)
NS = form.WORD_NS
KEYS = ("transport", "lodging", "misc", "meal", "local")


def data():
    return {
        "filled_on": "2026-04-02", "department": "测试部门", "group": "测试组",
        "route": "甲地→乙地", "start_date": "2026-03-30", "end_date": "2026-04-02",
        "purpose": "测试事务", "rows": [{"traveler": "测试甲", "transport_mode": "火车",
            "transport": "100.10", "lodging": "20.20", "misc": "0", "meal": "0", "local": "0"}],
        "payments": {"official_card": "120.30", "bank_card": "0", "company_transfer": "0", "cheque": "0", "cash": "0"},
    }


def doc(path):
    with ZipFile(path) as z:
        return minidom.parseString(z.read("word/document.xml"))


def cells(d):
    table = d.getElementsByTagNameNS(NS, "tbl")[0]
    return [form.children(row, "tc") for row in form.children(table, "tr")]


def texts(node):
    return form.plain_text(node)


def put_text(cell, value):
    paragraph = form.children(cell, "p")[0]
    run = cell.ownerDocument.createElementNS(NS, "w:r")
    text = cell.ownerDocument.createElementNS(NS, "w:t")
    text.appendChild(cell.ownerDocument.createTextNode(value))
    run.appendChild(text)
    paragraph.appendChild(run)


def masked(node):
    clone = node.cloneNode(deep=True)
    for t in clone.getElementsByTagNameNS(NS, "t"):
        while t.firstChild:
            t.removeChild(t.firstChild)
    return clone.toxml()


def transformed_template(path, transform):
    with ZipFile(TEMPLATE) as src:
        d = minidom.parseString(src.read("word/document.xml"))
        transform(d)
        with ZipFile(path, "w") as out:
            for item in src.infolist():
                out.writestr(item, d.toxml(encoding="UTF-8") if item.filename == "word/document.xml" else src.read(item.filename))


def split_runs(d):
    for row, col in ((1, 1), (1, 3), (8, 1)):
        for t in list(cells(d)[row][col].getElementsByTagNameNS(NS, "t")):
            if not t.firstChild or len(t.firstChild.data) < 2:
                continue
            value = t.firstChild.data
            cut = len(value) // 2
            t.firstChild.data = value[:cut]
            run = t.parentNode
            other = run.cloneNode(deep=True)
            other.getElementsByTagNameNS(NS, "t")[0].firstChild.data = value[cut:]
            run.parentNode.insertBefore(other, run.nextSibling)


class DomesticFormTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.output = self.root / "result.docx"

    def test_original_template_preserves_static_labels_and_format(self):
        before = TEMPLATE.read_bytes()
        form.fill(data(), self.output)
        original, result = doc(TEMPLATE), doc(self.output)
        old, new = cells(original), cells(result)
        for row, col in ((1, 0), (1, 1), (1, 2), (1, 3), (8, 0), (8, 1)):
            with self.subTest(cell=(row, col)):
                self.assertEqual(masked(old[row][col]), masked(new[row][col]))
        for label in ("自", "起经", "到"):
            self.assertIn(label, texts(new[1][1]))
        self.assertRegex(texts(new[1][1]), r"自\s*甲地\s*起经\s*到\s*乙地")
        self.assertRegex(texts(new[1][3]), r"自\s*3\s*月\s*30\s*日到\s*4\s*月\s*2\s*日，共\s*4\s*天")
        total = texts(new[8][1])
        for label in ("其中，", "公务卡", "银行卡", "公司汇款", "支票", "现金"):
            self.assertIn(label, total)
        self.assertIn("120.30", total)
        self.assertEqual([r.toxml() for r in original.getElementsByTagNameNS(NS, "trHeight")],
                         [r.toxml() for r in result.getElementsByTagNameNS(NS, "trHeight")])
        self.assertEqual(before, TEMPLATE.read_bytes())

    def test_split_runs_template_and_waypoint(self):
        custom = self.root / "custom.docx"
        transformed_template(custom, split_runs)
        before = hashlib.sha256(custom.read_bytes()).digest()
        values = data()
        values["route"] = "甲地→中地→乙地"
        form.fill(values, self.output, template=custom)
        old, new = cells(doc(custom)), cells(doc(self.output))
        for row, col in ((1, 1), (1, 3), (8, 1)):
            self.assertEqual(masked(old[row][col]), masked(new[row][col]))
        self.assertRegex(texts(new[1][1]), r"自\s*甲地\s*起经\s*中地\s*到\s*乙地")
        self.assertEqual(before, hashlib.sha256(custom.read_bytes()).digest())

    def test_rejects_ambiguous_routes(self):
        for index, route in enumerate(("甲地", "甲地→", "→乙地", "甲地→→乙地", "甲地→中地→乙地→丁地", "甲地乙地",
                                       "甲地/乙地→丙地", "甲地、乙地→丙地", "甲地,乙地→丙地", "甲地，乙地→丙地",
                                       "甲地->乙地→丙地")):
            with self.subTest(route=route):
                values = data()
                values["route"] = route
                output = self.root / f"invalid-{index}.docx"
                with self.assertRaises(ValueError):
                    form.fill(values, output)
                self.assertFalse(output.exists())

    def test_populated_template_overwrites_existing_values(self):
        custom = self.root / "populated.docx"
        def populate(d):
            c = cells(d)
            c[1][1].getElementsByTagNameNS(NS, "t")[0].firstChild.data = "自旧甲起经旧中到旧乙"
            date_nodes = c[1][3].getElementsByTagNameNS(NS, "t")
            date_nodes[0].firstChild.data = "自1月1日到1月2日，"
            date_nodes[2].firstChild.data = "2天"
            total_nodes = c[8][1].getElementsByTagNameNS(NS, "t")
            for node in total_nodes:
                if node.firstChild and node.firstChild.data == "      ":
                    node.firstChild.data = "9"
            put_text(c[4][0], "旧测试人")
            put_text(c[7][2], "旧备注")
        transformed_template(custom, populate)
        form.fill(data(), self.output, template=custom)
        old, new = cells(doc(custom)), cells(doc(self.output))
        for row, col in ((1, 1), (1, 3), (8, 1)):
            self.assertEqual(masked(old[row][col]), masked(new[row][col]))
        self.assertNotIn("旧", texts(new[1][1]))
        self.assertRegex(texts(new[1][1]), r"自\s*甲地\s*起经\s*到\s*乙地")
        self.assertRegex(texts(new[1][3]), r"自\s*3\s*月\s*30\s*日到\s*4\s*月\s*2\s*日，共\s*4\s*天")
        self.assertRegex(texts(new[8][1]), r"¥\s*120\.30\s*其中，\s*公务卡\s*¥\s*120\.30\s*银行卡\s*¥\s*0\s*公司汇款\s*¥\s*0\s*支票\s*¥\s*0\s*现金\s*¥\s*0\s*$")
        self.assertEqual(texts(new[4][0]), "测试甲")
        self.assertEqual(texts(new[7][2]), "")

    def test_notes_use_two_rows_and_keep_next_person(self):
        values = data()
        values["rows"][0]["payment_notes"] = {"transport": "测试付款\n第二行", "lodging": "单位结算"}
        values["rows"].append({"traveler": "测试乙", "transport_mode": "汽车", **dict.fromkeys(KEYS, "0")})
        form.fill(values, self.output)
        actual = cells(doc(self.output))
        self.assertIn("测试甲", texts(actual[4][0]))
        self.assertIn("测试付款", texts(actual[5][2]))
        self.assertIn("第二行", texts(actual[5][2]))
        self.assertTrue("\n" in texts(actual[5][2]) or actual[5][2].getElementsByTagNameNS(NS, "br"))
        self.assertIn("单位结算", texts(actual[5][3]))
        self.assertIn("测试乙", texts(actual[6][0]))

    def test_notes_over_capacity_rejected_without_output(self):
        values = data()
        values["rows"] = [copy.deepcopy(values["rows"][0]) for _ in range(3)]
        for row in values["rows"][:2]:
            row["payment_notes"] = {"transport": "备注"}
        with self.assertRaises(ValueError):
            form.fill(values, self.output)
        self.assertFalse(self.output.exists())

    def test_unit_settlement_needs_matching_total_and_note(self):
        values = data()
        values["payments"]["official_card"] = "20.30"
        values["payments"]["unit_settlement"] = "100"
        with self.assertRaises(ValueError):
            form.fill(values, self.output)
        self.assertFalse(self.output.exists())
        values["rows"][0]["payment_notes"] = {"transport": "单位结算"}
        form.fill(values, self.output)
        result = cells(doc(self.output))
        self.assertIn("单位结算", texts(result[5][2]))
        self.assertIn("120.30", texts(result[8][1]))
        self.assertNotIn("单位结算", texts(result[8][1]))

    def test_payment_schema_and_note_keys_are_strict(self):
        cases = []
        values = data()
        del values["payments"]["cash"]
        cases.append(values)
        values = data()
        values["payments"]["unit_settlement"] = None
        cases.append(values)
        values = data()
        values["payments"]["official_card"] = 120.3
        cases.append(values)
        values = data()
        values["rows"][0]["payment_notes"] = {"other": "备注"}
        cases.append(values)
        values = data()
        values["payments"]["unit_settlement"] = "1"
        values["rows"][0]["payment_notes"] = {"transport": "单位结算"}
        cases.append(values)
        for index, values in enumerate(cases):
            with self.subTest(case=index):
                output = self.root / f"invalid-payment-{index}.docx"
                with self.assertRaises(ValueError):
                    form.fill(values, output)
                self.assertFalse(output.exists())

    def test_whole_yuan_total_and_fee_precision(self):
        values = data()
        values["rows"][0]["transport"] = "100"
        values["rows"][0]["lodging"] = "20"
        values["payments"]["official_card"] = "120"
        form.fill(values, self.output)
        result = cells(doc(self.output))
        self.assertEqual(texts(result[4][2]), "100.00")
        self.assertEqual(texts(result[4][3]), "20.00")
        total = texts(result[8][1])
        self.assertRegex(total, r"¥\s*120\s*其中")

    def test_zero_values_preserve_fixed_labels(self):
        values = data()
        values["rows"][0].update(dict.fromkeys(KEYS, "0"))
        values["payments"] = dict.fromkeys(values["payments"], "0.00")
        form.fill(values, self.output)
        result = cells(doc(self.output))
        self.assertEqual([texts(cell) for cell in result[4][2:]], ["0.00"] * 6)
        self.assertRegex(texts(result[8][1]), r"¥\s*0\s*其中，\s*公务卡\s*¥\s*0\s*银行卡\s*¥\s*0\s*公司汇款\s*¥\s*0\s*支票\s*¥\s*0\s*现金\s*¥\s*0\s*$")

    def test_invalid_amounts_and_allocation_rejected_without_output(self):
        for invalid in (1.25, None, True):
            with self.subTest(amount=invalid):
                values = data()
                values["rows"][0]["transport"] = invalid
                with self.assertRaises(ValueError):
                    form.fill(values, self.output)
                self.assertFalse(self.output.exists())
        values = data()
        values["payments"]["official_card"] = "120.29"
        with self.assertRaises(ValueError):
            form.fill(values, self.output)
        self.assertFalse(self.output.exists())

    def test_incompatible_template_and_existing_output_rejected(self):
        custom = self.root / "bad.docx"
        def change_header(d):
            node = cells(d)[3][2].getElementsByTagNameNS(NS, "t")[0]
            node.firstChild.data = "错误列"
        transformed_template(custom, change_header)
        with self.assertRaises(ValueError):
            form.fill(data(), self.output, template=custom)
        self.assertFalse(self.output.exists())
        self.output.write_bytes(b"existing content")
        with self.assertRaises((ValueError, FileExistsError)):
            form.fill(data(), self.output)
        self.assertEqual(self.output.read_bytes(), b"existing content")

    def test_cli_template_option(self):
        custom = self.root / "custom.docx"
        transformed_template(custom, split_runs)
        input_file = self.root / "data.json"
        input_file.write_text(json.dumps(data(), ensure_ascii=False), encoding="utf-8")
        result = subprocess.run([sys.executable, str(HERE / "fill_domestic_form.py"), "--data", str(input_file),
                                 "--output", str(self.output), "--template", str(custom)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.output.exists())


if __name__ == "__main__":
    unittest.main()
