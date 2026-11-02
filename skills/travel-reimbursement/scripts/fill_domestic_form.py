#!/usr/bin/env python3
"""将已核实的国内差旅金额写入原表副本；只使用 Python 标准库。"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from xml.dom import minidom
from zipfile import ZipFile


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MONEY_KEYS = ("transport", "lodging", "misc", "meal", "local")
PAYMENT_LABELS = {
    "official_card": "公务卡",
    "bank_card": "银行卡",
    "company_transfer": "公司汇款",
    "cheque": "支票",
    "cash": "现金",
}


def require_keys(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError("填写数据及各行必须为 JSON 对象")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"字段不符：缺少 {sorted(missing)}；多余 {sorted(extra)}")


def text_field(value, label, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} 必须为{'可为空的' if allow_empty else '非空'}文本")
    if any(ord(char) < 32 and char not in "\n\t\r" for char in value):
        raise ValueError(f"{label} 含有无效控制字符")
    return value.strip()


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("日期必须为 YYYY-MM-DD")
    return date.fromisoformat(value)


def cents(value):
    # 用整数分精确求和，禁止把浮点数转换为看似精确的金额。
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("金额必须为字符串或整数，未知金额不能填零")
    value = str(value)
    if not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d{1,2})?", value):
        raise ValueError("金额须非负、有限且最多两位小数")
    whole, _, fraction = value.partition(".")
    return int(whole) * 100 + int(fraction.ljust(2, "0"))


def money(value):
    return f"{value // 100}.{value % 100:02d}"


def inline_money(value):
    return str(value // 100) if value % 100 == 0 else money(value)


def children(node, local_name):
    return [child for child in node.childNodes
            if child.nodeType == child.ELEMENT_NODE
            and child.namespaceURI == WORD_NS and child.localName == local_name]


def plain_text(node):
    return "".join(child.data for text in node.getElementsByTagNameNS(WORD_NS, "t")
                   for child in text.childNodes if child.nodeType == child.TEXT_NODE)


def replace_text(container, value):
    """仅替换目标单元格/段落文字，保留单元格及段落格式。"""
    doc = container.ownerDocument
    paragraphs = children(container, "p")
    paragraph = paragraphs[0] if paragraphs else container
    if paragraph is container and container.localName != "p":
        paragraph = doc.createElementNS(WORD_NS, "w:p")
        container.appendChild(paragraph)
    properties = paragraph.getElementsByTagNameNS(WORD_NS, "rPr")
    run_properties = properties[0].cloneNode(deep=True) if properties else None
    for other in paragraphs[1:]:
        container.removeChild(other)
    for child in list(paragraph.childNodes):
        if child.nodeType == child.ELEMENT_NODE and child.localName == "pPr":
            continue
        paragraph.removeChild(child)
    run = doc.createElementNS(WORD_NS, "w:r")
    if run_properties is not None:
        run.appendChild(run_properties)
    for index, line in enumerate(value.split("\n")):
        if index:
            run.appendChild(doc.createElementNS(WORD_NS, "w:br"))
        text = doc.createElementNS(WORD_NS, "w:t")
        text.setAttributeNS("http://www.w3.org/XML/1998/namespace", "xml:space", "preserve")
        text.appendChild(doc.createTextNode(line))
        run.appendChild(text)
    paragraph.appendChild(run)


def replace_span(container, start, end, value):
    """仅改目标区间的 w:t 内容，保留所有 run、段落和格式节点。"""
    nodes = list(container.getElementsByTagNameNS(WORD_NS, "t"))
    values = ["".join(child.data for child in node.childNodes
                      if child.nodeType == child.TEXT_NODE) for node in nodes]
    length = sum(map(len, values))
    if not nodes or not 0 <= start <= end <= length:
        raise ValueError("模板填空区间无效")
    offsets = []
    cursor = 0
    for text in values:
        offsets.append(cursor)
        cursor += len(text)
    first = next((i for i, text in enumerate(values)
                  if offsets[i] <= start < offsets[i] + len(text)), len(nodes) - 1)
    last = first if start == end else next(
        i for i, text in enumerate(values) if offsets[i] < end <= offsets[i] + len(text))
    for i in range(first, last + 1):
        prefix = values[i][:start - offsets[i]] if i == first else ""
        suffix = values[i][end - offsets[i]:] if i == last else ""
        updated = prefix + (value if i == first else "") + suffix
        for child in list(nodes[i].childNodes):
            if child.nodeType == child.TEXT_NODE:
                nodes[i].removeChild(child)
        nodes[i].appendChild(nodes[i].ownerDocument.createTextNode(updated))


def fill_slots(container, pattern, values):
    """固定词识别空位，倒序替换以维持原始文本偏移。"""
    original = plain_text(container)
    match = re.fullmatch(pattern, original, re.DOTALL)
    if match is None:
        raise ValueError("模板地点、时间或合计的固定文字变化，请先核对模板")
    edits = []
    for name, value in values.items():
        start, end = match.span(name)
        old = original[start:end]
        if old.strip():
            leading = len(old) - len(old.lstrip())
            trailing = len(old) - len(old.rstrip())
            edits.append((start + leading, end - trailing, value))
        elif value:
            edits.append((start, end, value))
    for start, end, value in sorted(edits, reverse=True):
        replace_span(container, start, end, value)


ROUTE_PATTERN = r"自(?P<departure>.*?)起经(?P<via>.*?)到(?P<destination>.*?)"
DATE_PATTERN = (r"自(?P<start_month>.*?)月(?P<start_day>.*?)日到"
                r"(?P<end_month>.*?)月(?P<end_day>.*?)日，\s*共(?P<days>.*?)天")
TOTAL_PATTERN = (r"¥(?P<total>.*?)其中，\s*公务卡\s*¥(?P<official_card>.*?)"
                 r"银行卡\s*¥(?P<bank_card>.*?)公司汇款\s*¥(?P<company_transfer>.*?)"
                 r"支票\s*¥(?P<cheque>.*?)现金\s*¥(?P<cash>.*?)")


def route_parts(value):
    value = text_field(value, "route")
    parts = [part.strip() for part in value.split("→")]
    if (len(parts) not in (2, 3) or not all(parts)
            or any(re.search(r"[/、,，\r\n\t]|->", part) for part in parts)):
        raise ValueError("route 须为起点→终点或起点→途经地→终点，不能猜测地点")
    if len(parts) == 2:
        parts.insert(1, "")
    return dict(zip(("departure", "via", "destination"), parts))


def fill(data, output, template=None):
    require_keys(data, ("filled_on", "department", "group", "route", "start_date",
                        "end_date", "purpose", "rows", "payments"), ("account",))
    filled_on = parse_date(data["filled_on"])
    start = parse_date(data["start_date"])
    end = parse_date(data["end_date"])
    days = (end - start).days + 1
    if not 1 <= days <= 6:
        raise ValueError("国内单张实际行程须为 1–6 天；连续累计和申请覆盖需另行核验")
    fields = {key: text_field(data[key], key)
              for key in ("department", "group", "route", "purpose")}
    route = route_parts(fields["route"])
    account = text_field(data.get("account", ""), "account", allow_empty=True)
    if not isinstance(data["rows"], list) or not 1 <= len(data["rows"]) <= 4:
        raise ValueError("原表只支持 1–4 个费用行，超过时按实际情况分表")
    rows = []
    slots_needed = 0
    total = 0
    for row in data["rows"]:
        require_keys(row, ("traveler", "transport_mode", *MONEY_KEYS), ("payment_notes",))
        amounts = [cents(row[key]) for key in MONEY_KEYS]
        subtotal = sum(amounts)
        notes = row.get("payment_notes", {})
        require_keys(notes, (), MONEY_KEYS)
        notes = {key: text_field(value, f"payment_notes.{key}", allow_empty=True)
                 for key, value in notes.items()}
        notes = {key: value for key, value in notes.items() if value}
        rows.append(([text_field(row["traveler"], "traveler"),
                      text_field(row["transport_mode"], "transport_mode"),
                      *(money(amount) for amount in amounts), money(subtotal)], notes))
        slots_needed += 1 + bool(notes)
        total += subtotal
    if slots_needed > 4:
        raise ValueError("费用行及下方付款备注行超过原表4行容量，请分表")
    require_keys(data["payments"], PAYMENT_LABELS, ("unit_settlement",))
    payments = {key: cents(data["payments"][key]) for key in PAYMENT_LABELS}
    unit_settlement = cents(data["payments"].get("unit_settlement", "0"))
    allocated = sum(payments.values()) + unit_settlement
    if allocated != total:
        raise ValueError(f"付款分配及单位结算合计 {money(allocated)} 与费用合计 {money(total)} 不一致")
    if unit_settlement and not any("单位结算" in note for _, notes in rows for note in notes.values()):
        raise ValueError("单位结算须在对应费用下方提供包含“单位结算”的 payment_notes")
    template = Path(template) if template is not None else Path(__file__).resolve().parents[1] / "assets" / "差旅报销单.docx"
    output = Path(output)
    if output.suffix.lower() != ".docx":
        raise ValueError("输出必须是 .docx 文件")
    if output.exists():
        raise ValueError("输出已存在，未覆盖；请选择新的文件名")
    with ZipFile(template) as source:
        doc = minidom.parseString(source.read("word/document.xml"))
        tables = doc.getElementsByTagNameNS(WORD_NS, "tbl")
        if len(tables) != 1:
            raise ValueError("原模板表格结构变化，请先核对模板")
        tr = children(tables[0], "tr")
        cells = [children(row, "tc") for row in tr]
        expected = [4, 4, 2, 8, 8, 8, 8, 8, 2, 2, 1, 1]
        if [len(row) for row in cells] != expected:
            raise ValueError("原模板行列结构变化，请先核对模板")
        if [plain_text(cell) for cell in cells[3]] != ["出差人", "交通工具", "交通费", "住宿费", "杂费", "伙食补", "交通补", "小计"]:
            raise ValueError("原模板费用列变化，请先核对模板")
        if (not plain_text(cells[1][0]).startswith("出差地点")
                or not plain_text(cells[1][2]).startswith("出差时间")
                or plain_text(cells[8][0]) != "合计"
                or plain_text(cells[9][0]) != "核算账号"):
            raise ValueError("原模板字段标签变化，请先核对模板")
        fill_slots(cells[1][1], ROUTE_PATTERN, route)
        fill_slots(cells[1][3], DATE_PATTERN, {
            "start_month": str(start.month), "start_day": str(start.day),
            "end_month": str(end.month), "end_day": str(end.day), "days": str(days),
        })
        fill_slots(cells[8][1], TOTAL_PATTERN, {
            "total": inline_money(total), **{key: inline_money(amount) for key, amount in payments.items()},
        })
        for row, column, value in (
            (0, 1, fields["department"]), (0, 3, fields["group"]),
            (2, 1, fields["purpose"]), (9, 1, account),
        ):
            replace_text(cells[row][column], value)
        for row in cells[4:8]:
            for cell in row:
                replace_text(cell, "")
        expense_rows = []
        index = 4
        for values, notes in rows:
            expense_rows.append((index, values))
            for cell, value in zip(cells[index], values):
                replace_text(cell, value)
            index += 1
            if notes:
                for key, value in notes.items():
                    replace_text(cells[index][MONEY_KEYS.index(key) + 2], value)
                index += 1
        body = doc.getElementsByTagNameNS(WORD_NS, "body")[0]
        dates = [p for p in children(body, "p") if plain_text(p).startswith("填表日期")]
        if len(dates) != 1:
            raise ValueError("模板填表日期字段变化，请先核对模板")
        fill_slots(dates[0], r"填表日期：\s*(?P<year>.*?)年(?P<month>.*?)月(?P<day>.*?)日\s*", {
            "year": str(filled_on.year), "month": str(filled_on.month), "day": str(filled_on.day),
        })
        xml = doc.toxml(encoding="UTF-8")
        minidom.parseString(xml)
        output.parent.mkdir(parents=True, exist_ok=True)
        # 排他新建，避免覆盖用户已有文件；只有写入失败才删除本次部分输出。
        with output.open("xb") as handle:
            try:
                with ZipFile(handle, "w") as target:
                    for info in source.infolist():
                        target.writestr(info, xml if info.filename == "word/document.xml"
                                        else source.read(info.filename))
            except Exception:
                output.unlink()
                raise
    with ZipFile(output) as result:
        if result.testzip() is not None:
            raise ValueError("输出 DOCX 压缩结构校验失败")
        check = minidom.parseString(result.read("word/document.xml"))
        check_cells = [children(row, "tc") for row in children(
            check.getElementsByTagNameNS(WORD_NS, "tbl")[0], "tr")]
        for index, values in expense_rows:
            if [plain_text(cell) for cell in check_cells[index]] != values:
                raise ValueError("输出费用行回读不匹配")
        if plain_text(check_cells[8][1]) != plain_text(cells[8][1]):
            raise ValueError("输出合计回读不匹配")
    return {"状态": "草稿已生成，待签字及组秘核验", "文件": str(output.resolve()),
            "人数": len(rows), "实际天数": days, "费用合计": money(total),
            "单位结算": money(unit_settlement), "付款备注行": slots_needed - len(rows),
            "核算账号": "已填入，待组秘复核" if account else "空白，待组秘填写",
            "视觉检查": "未执行；请检查分页、截断和签字位置"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="已核实的 JSON 数据")
    parser.add_argument("--output", type=Path, required=True, help="新建的 Word 草稿路径")
    parser.add_argument("--template", type=Path, help="可选：同结构的用户当前Word模板；原件不修改")
    args = parser.parse_args()
    try:
        result = fill(json.loads(args.data.read_text(encoding="utf-8")), args.output, template=args.template)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"未生成报销单：{error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
