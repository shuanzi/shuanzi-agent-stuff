#!/usr/bin/env python3
"""Validate an offline Lark Base readback against build_lark_plan output."""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ValidationError(ValueError):
    pass


def _read_json(path: str, label: str) -> Any:
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} 不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{label} 不是合法 JSON: {exc}") from exc


def _write_json(path: str, payload: Any) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _timezone(value: Any) -> ZoneInfo:
    if not isinstance(value, str) or not value:
        raise ValidationError("plan row 缺少 timezone")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError(f"plan row timezone 非法: {value}") from exc


def _datetime(value: Any, timezone: ZoneInfo) -> str | None:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            localized = parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed.astimezone(timezone)
            return localized.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _money(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return format(decimal.quantize(Decimal("0.01")), ".2f") if decimal.is_finite() else None


def _norm_select(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _selects(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    values = value if isinstance(value, list) else [value]
    names = []
    for item in values:
        name = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str):
            names.append(_norm_select(name))
    return sorted(names)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "value"):
            if isinstance(value.get(key), str):
                return value[key]
    return str(value)


def _owner_ids(value: Any) -> set[str]:
    values = value if isinstance(value, list) else [value]
    result: set[str] = set()
    for item in values:
        if isinstance(item, str):
            result.add(item)
        elif isinstance(item, dict):
            for key in ("id", "open_id", "user_id"):
                if isinstance(item.get(key), str):
                    result.add(item[key])
                    break
    return result


def _same(expected: Any, actual: Any, timezone: ZoneInfo) -> bool:
    if expected is None:
        return actual is None or actual == "" or actual == []
    if isinstance(expected, list) and all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in expected):
        return {item["id"] for item in expected} == _owner_ids(actual)
    if isinstance(expected, list):
        return sorted(_norm_select(item) for item in expected) == _selects(actual)
    if isinstance(expected, str):
        expected_time = _datetime(expected, timezone) if "T" in expected or " " in expected else None
        if expected_time is not None:
            return _datetime(actual, timezone) == expected_time
        expected_money = _money(expected)
        if expected_money is not None and "." in expected and expected.replace(".", "", 1).isdigit():
            return _money(actual) == expected_money
        return _text(actual) == expected or _selects(actual) == [_norm_select(expected)]
    return actual == expected


def _validate(plan: Any, write_result: Any, readback: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValidationError("plan 必须为对象")
    if not isinstance(write_result, dict):
        raise ValidationError("write-result 必须为对象")
    if not isinstance(readback, dict) or not isinstance(readback.get("records"), list):
        raise ValidationError("readback 必须含 records 数组")
    errors: list[dict[str, Any]] = []
    creates = plan.get("create_rows")
    updates = plan.get("update_rows")
    if not isinstance(creates, list) or not isinstance(updates, list):
        raise ValidationError("plan 必须含 create_rows 和 update_rows 数组")
    if plan.get("write_ready") is not True:
        errors.append({"kind": "plan_not_write_ready"})
    created_ids = write_result.get("created_record_ids")
    updated_ids = write_result.get("updated_record_ids")
    if not isinstance(created_ids, list) or not all(isinstance(value, str) and value for value in created_ids):
        raise ValidationError("write-result.created_record_ids 必须为非空字符串数组")
    if not isinstance(updated_ids, list) or not all(isinstance(value, str) and value for value in updated_ids):
        raise ValidationError("write-result.updated_record_ids 必须为非空字符串数组")
    if write_result.get("ignored_fields") not in (None, [], {}):
        errors.append({"kind": "ignored_fields", "value": write_result.get("ignored_fields")})
    if write_result.get("warnings") not in (None, [], {}):
        errors.append({"kind": "write_warnings", "value": write_result.get("warnings")})
    if write_result.get("failures") not in (None, [], {}):
        errors.append({"kind": "write_failures", "value": write_result.get("failures")})
    if len(created_ids) != len(creates):
        errors.append({"kind": "created_id_count", "expected": len(creates), "actual": len(created_ids)})
    if len(updated_ids) != len(updates):
        errors.append({"kind": "updated_id_count", "expected": len(updates), "actual": len(updated_ids)})
    if len(set(created_ids)) != len(created_ids) or len(set(updated_ids)) != len(updated_ids) or set(created_ids) & set(updated_ids):
        errors.append({"kind": "write_result_ids_not_unique"})

    records: dict[str, dict[str, Any]] = {}
    for record in readback["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("record_id"), str) or not isinstance(record.get("fields"), dict):
            errors.append({"kind": "invalid_readback_record"})
            continue
        records[record["record_id"]] = record
    expected_rows = list(zip(created_ids, creates)) + list(zip(updated_ids, updates))
    verified: list[dict[str, Any]] = []
    for record_id, row in expected_rows:
        record = records.get(record_id)
        if record is None:
            errors.append({"kind": "missing_readback_record", "record_id": record_id, "transaction_key": row.get("transaction_key")})
            continue
        expected_fields = row.get("expected_fields", row.get("fields"))
        if not isinstance(expected_fields, dict):
            errors.append({"kind": "invalid_plan_fields", "record_id": record_id})
            continue
        timezone = _timezone(row.get("timezone"))
        for field_name, expected in expected_fields.items():
            actual = record["fields"].get(field_name)
            if not _same(expected, actual, timezone):
                errors.append({"kind": "field_mismatch", "record_id": record_id, "transaction_key": row.get("transaction_key"), "field": field_name, "expected": expected, "actual": actual})
        verified.append({"record_id": record_id, "transaction_key": row.get("transaction_key"), "target_view": row.get("target_view")})

    memberships = readback.get("view_record_ids_by_name")
    if not isinstance(memberships, dict):
        errors.append({"kind": "missing_view_record_ids_by_name"})
    else:
        for record_id, row in expected_rows:
            target_view = row.get("target_view")
            if not isinstance(target_view, str) or not isinstance(memberships.get(target_view), list):
                errors.append({"kind": "missing_target_view", "record_id": record_id, "target_view": target_view})
            elif record_id not in memberships[target_view]:
                errors.append({"kind": "record_not_in_year_view", "record_id": record_id, "target_view": target_view})
    return {"ok": not errors, "plan_profile_name": plan.get("profile_name"), "verified_records": verified, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按返回 ID 核对 Lark Base 写入 readback")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--write-result", required=True)
    parser.add_argument("--readback", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = _validate(_read_json(args.plan, "plan"), _read_json(args.write_result, "write-result"), _read_json(args.readback, "readback"))
        _write_json(args.output, result)
        return 0 if result["ok"] else 1
    except ValidationError as exc:
        _write_json(args.output, {"ok": False, "errors": [{"kind": "invalid_input", "message": str(exc)}]})
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
