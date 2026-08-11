#!/usr/bin/env python3
"""Build an offline, fail-closed Lark Base import plan.

The input statement must already have been normalized by prepare_statement.
No network calls or lark-cli calls are made here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from adapters import ADAPTERS


MONEY_RE = re.compile(r"^(?:0|[1-9]\d*)\.\d{2}$")
TYPE_ALIASES = {
    "text": {"text"},
    "datetime": {"datetime", "date_time"},
    "number": {"number"},
    "select": {"select", "single_select", "singleselect", "multi_select", "multiselect"},
    "user": {"user"},
}


class PlanError(ValueError):
    pass


def _read_json(path: str, label: str) -> Any:
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise PlanError(f"{label} 不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"{label} 不是合法 JSON: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _type_name(value: Any) -> str:
    return value.lower().replace("-", "_").replace(" ", "") if isinstance(value, str) else ""


def _normalize_select(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _option_map(options: Any, field_name: str) -> dict[str, str]:
    if not isinstance(options, list):
        raise PlanError(f"select 字段 {field_name} 的 options 必须为数组")
    result: dict[str, str] = {}
    for option in options:
        name = option if isinstance(option, str) else option.get("name") if isinstance(option, dict) else None
        if not isinstance(name, str) or not name:
            raise PlanError(f"select 字段 {field_name} 的 options 必须为字符串或含 name 的对象")
        normalized = _normalize_select(name)
        if normalized in result:
            raise PlanError(f"select 字段 {field_name} 有规范化后重复的 option: {name}")
        result[normalized] = name
    return result


def _field_map(snapshot: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("fields"), list):
        raise PlanError("base snapshot.fields 必须为数组")
    result: dict[str, dict[str, Any]] = {}
    for field in snapshot["fields"]:
        if not isinstance(field, dict) or not isinstance(field.get("name"), str) or not isinstance(field.get("type"), str):
            raise PlanError("base snapshot.fields 每项必须含 name 和 type 字符串")
        if field["name"] in result:
            raise PlanError(f"Base 字段重复: {field['name']}")
        if "multiple" in field and field["multiple"] is not None and not isinstance(field["multiple"], bool):
            raise PlanError(f"Base 字段 {field['name']} 的 multiple 只能为 true、false 或 null")
        result[field["name"]] = field
    return result


def _require_field(metadata: dict[str, dict[str, Any]], name: str, kind: str) -> dict[str, Any]:
    field = metadata.get(name)
    if field is None:
        raise PlanError(f"profile 指向不存在的 {kind} 字段: {name}")
    if _type_name(field["type"]) not in TYPE_ALIASES[kind]:
        raise PlanError(f"Base 字段 {name} 类型不符：应为 {kind}，实际为 {field['type']}")
    return field


def _writable(field: dict[str, Any], field_name: str) -> bool:
    value = field.get("writable")
    if not isinstance(value, bool):
        raise PlanError(f"Base 字段 {field_name} 的 writable 必须为布尔值")
    return value


def _profile_and_fields(profile: Any, snapshot: Any) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str], dict[str, str]]:
    if not isinstance(profile, dict):
        raise PlanError("profile 必须为对象")
    for key in ("profile_name", "base_url", "table_name", "view_name_template", "owner_name", "fields", "values", "dedupe_fields"):
        if key not in profile:
            raise PlanError(f"profile 缺少字段: {key}")
    fields = profile["fields"]
    values = profile["values"]
    if not isinstance(fields, dict) or not isinstance(values, dict) or not isinstance(profile["dedupe_fields"], list):
        raise PlanError("profile.fields、profile.values 和 profile.dedupe_fields 类型不正确")
    for key in ("remark", "date", "amount", "direction", "owner"):
        if not isinstance(fields.get(key), str) or not fields[key]:
            raise PlanError(f"profile.fields.{key} 必须为非空字符串")
    if "project" in fields and (not isinstance(fields["project"], str) or not fields["project"]):
        raise PlanError("profile.fields.project 必须为非空字符串")
    if not isinstance(values.get("expense"), str) or not values["expense"]:
        raise PlanError("profile.values.expense 必须为非空字符串")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("table_name"), str):
        raise PlanError("base snapshot.table_name 必须为字符串")
    if snapshot.get("base_url") != profile["base_url"]:
        raise PlanError("base snapshot.base_url 必须与 profile.base_url 精确一致")
    if snapshot["table_name"] != profile["table_name"]:
        raise PlanError(
            f"base snapshot.table_name 与 profile 不一致：{snapshot['table_name']} != {profile['table_name']}"
        )
    if snapshot.get("records_complete") is not True:
        raise PlanError("base snapshot.records_complete 必须为 true")
    if snapshot.get("views_complete") is not True:
        raise PlanError("base snapshot.views_complete 必须为 true")
    expected_key_fields = [fields["date"], fields["amount"], fields["direction"], fields["owner"]]
    if profile["dedupe_fields"] != expected_key_fields:
        raise PlanError("profile.dedupe_fields 必须严格为 date、amount、direction、owner 对应字段")

    metadata = _field_map(snapshot)
    remark = _require_field(metadata, fields["remark"], "text")
    date = _require_field(metadata, fields["date"], "datetime")
    amount = _require_field(metadata, fields["amount"], "number")
    direction = _require_field(metadata, fields["direction"], "select")
    owner = _require_field(metadata, fields["owner"], "user")
    for field_name, field in (
        (fields["remark"], remark),
        (fields["date"], date),
        (fields["amount"], amount),
        (fields["direction"], direction),
        (fields["owner"], owner),
    ):
        if not _writable(field, field_name):
            raise PlanError(f"Base 必填字段不可写: {field_name}")
    project = None
    if fields.get("project") and fields["project"] in metadata:
        project_candidate = _require_field(metadata, fields["project"], "select")
        if _writable(project_candidate, fields["project"]):
            project = project_candidate
    directions = _option_map(direction.get("options"), fields["direction"])
    normalized_expense = _normalize_select(values["expense"])
    if normalized_expense not in directions:
        raise PlanError(f"支出值不在方向字段 {fields['direction']} 的 live options 中")
    projects = _option_map(project.get("options"), fields["project"]) if project else {}
    return profile, metadata, directions, projects


def _timezone(value: Any, context: str) -> ZoneInfo:
    if not isinstance(value, str) or not value:
        raise PlanError(f"{context}.timezone 必须为 IANA 时区字符串")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise PlanError(f"{context}.timezone 不是有效 IANA 时区: {value}") from exc


def _canonical_datetime(value: Any, timezone: ZoneInfo, context: str) -> str:
    if not isinstance(value, str):
        raise PlanError(f"{context}.occurred_at 必须为 ISO8601 字符串")
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise PlanError(f"{context}.occurred_at 不是 ISO8601 时间: {value}") from exc
    localized = parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed.astimezone(timezone)
    return localized.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _readback_datetime(value: Any, timezone: ZoneInfo) -> str | None:
    if isinstance(value, str):
        try:
            return _canonical_datetime(value, timezone, "readback")
        except PlanError:
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _money(value: Any, context: str) -> str:
    if not isinstance(value, str) or not MONEY_RE.fullmatch(value):
        raise PlanError(f"{context}.net_amount 必须为两位小数的正数定点字符串")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PlanError(f"{context}.net_amount 非法") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise PlanError(f"{context}.net_amount 必须为正数")
    return value


def _readback_money(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return format(parsed.quantize(Decimal("0.01")), ".2f")


def _transactions(statement: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(statement, dict) or not isinstance(statement.get("transactions"), list):
        raise PlanError("statement 必须为 prepare_statement 输出，且含 transactions 数组")
    if statement.get("schema_version") != 1:
        raise PlanError("statement.schema_version 必须为 1")
    source_format = statement.get("source_format")
    if not isinstance(source_format, str) or source_format not in ADAPTERS:
        raise PlanError("statement.source_format 必须是已注册的 adapter ID")
    if statement.get("write_ready") is not True:
        raise PlanError("statement.write_ready 必须为 true；来源汇总异常时禁止构建写入计划")
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, raw in enumerate(statement["transactions"]):
        context = f"statement.transactions[{index}]"
        if not isinstance(raw, dict):
            raise PlanError(f"{context} 必须为对象")
        if raw.get("source_format") != source_format:
            raise PlanError(f"{context}.source_format 必须与 StatementBatch 一致")
        key = raw.get("transaction_key")
        remark = raw.get("normalized_note")
        if not isinstance(key, str) or not key:
            raise PlanError(f"{context}.transaction_key 必须为非空字符串")
        if raw.get("write_candidate") is not True:
            skipped.append({"transaction_key": key, "action": "skip", "reason": "write_candidate=false"})
            continue
        if not isinstance(remark, str):
            raise PlanError(f"{context}.normalized_note 必须为字符串")
        timezone_name = raw.get("timezone")
        timezone = _timezone(timezone_name, context)
        candidates.append(
            {
                "transaction_key": key,
                "occurred_at": _canonical_datetime(raw.get("occurred_at"), timezone, context),
                "net_amount": _money(raw.get("net_amount"), context),
                "remark": remark,
                "timezone": timezone_name,
            }
        )
    return candidates, skipped


def _assignments(raw: Any, transactions: list[dict[str, Any]], project_options: dict[str, str], project_field: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    supplied = {} if raw is None else raw.get("transactions") if isinstance(raw, dict) else None
    if supplied is None or not isinstance(supplied, dict):
        raise PlanError("assignments 必须为含 transactions 对象的 JSON")
    result: dict[str, dict[str, Any]] = {}
    keys = {transaction["transaction_key"] for transaction in transactions}
    unknown_keys = sorted(set(supplied) - keys)
    if unknown_keys:
        raise PlanError(f"assignments 含不存在的 transaction_key: {', '.join(unknown_keys)}")
    for transaction in transactions:
        key = transaction["transaction_key"]
        entry = supplied.get(key, {"labels": [], "confidence": "low", "reason": "未提供分类"})
        if not isinstance(entry, dict) or entry.get("confidence") not in {"high", "low"}:
            raise PlanError(f"assignments.transactions.{key} 的 confidence 必须为 high 或 low")
        labels = entry.get("labels")
        if not isinstance(labels, list) or not all(isinstance(label, str) and label for label in labels):
            raise PlanError(f"assignments.transactions.{key}.labels 必须为字符串数组")
        if not isinstance(entry.get("reason"), str):
            raise PlanError(f"assignments.transactions.{key}.reason 必须为字符串")
        resolved = [project_options[_normalize_select(label)] for label in labels if _normalize_select(label) in project_options]
        unsafe_high = (
            entry["confidence"] == "high"
            and (
                not labels
                or project_field is None
                or len(resolved) != len(labels)
                or (project_field.get("multiple") is False and len(resolved) > 1)
            )
        )
        if entry["confidence"] == "high" and not labels:
            raise PlanError(f"assignments.transactions.{key} 高置信分类必须有标签")
        result[key] = {
            "labels": [] if entry["confidence"] == "low" or unsafe_high else resolved,
            "confidence": "low" if unsafe_high else entry["confidence"],
            "reason": entry["reason"] + ("; degraded_unsafe_project_assignment" if unsafe_high else ""),
        }
    return result


def _view_name(template: Any, occurred_at: str) -> str:
    if not isinstance(template, str) or not template:
        raise PlanError("profile.view_name_template 必须为非空字符串")
    try:
        return template.format(year=occurred_at[:4])
    except (KeyError, IndexError, ValueError) as exc:
        raise PlanError("profile.view_name_template 只能包含 {year}") from exc


def _view_names(snapshot: Any) -> set[str]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("views"), list):
        raise PlanError("base snapshot.views 必须为数组")
    names = set()
    for view in snapshot["views"]:
        if not isinstance(view, dict) or not isinstance(view.get("name"), str):
            raise PlanError("base snapshot.views 每项必须含 name")
        names.add(view["name"])
    return names


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


def _select_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        name = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str):
            result.append(name)
    return result


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


def _has_project(record: dict[str, Any], project_name: str | None) -> bool:
    return bool(project_name and _select_values(record["fields"].get(project_name)))


def _matches_key(record: dict[str, Any], profile: dict[str, Any], transaction: dict[str, Any], owner_id: str, expense: str) -> bool:
    fields = profile["fields"]
    return (
        _readback_datetime(record["fields"].get(fields["date"]), _timezone(transaction["timezone"], "transaction")) == transaction["occurred_at"]
        and _readback_money(record["fields"].get(fields["amount"])) == transaction["net_amount"]
        and {_normalize_select(value) for value in _select_values(record["fields"].get(fields["direction"]))} == {_normalize_select(expense)}
        and owner_id in _owner_ids(record["fields"].get(fields["owner"]))
    )


def _project_value(labels: list[str], field: dict[str, Any] | None) -> Any:
    if field is None or not labels:
        return None
    return labels[0] if field.get("multiple") is False else labels


def _full_fields(profile: dict[str, Any], transaction: dict[str, Any], owner_id: str, expense: str, labels: list[str], project_field: dict[str, Any] | None) -> dict[str, Any]:
    names = profile["fields"]
    result = {
        names["remark"]: transaction["remark"],
        names["date"]: transaction["occurred_at"],
        names["amount"]: transaction["net_amount"],
        names["direction"]: expense,
        names["owner"]: [{"id": owner_id}],
    }
    if project_field is not None:
        result[names["project"]] = _project_value(labels, project_field)
    return result


def build_plan(statement: Any, snapshot: Any, profile: Any, owner_id: str, assignment_data: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if not isinstance(owner_id, str) or not owner_id:
        raise PlanError("--owner-id 必须为非空字符串")
    profile, metadata, direction_options, project_options = _profile_and_fields(profile, snapshot)
    transactions, skipped = _transactions(statement)
    expense = direction_options[_normalize_select(profile["values"]["expense"])]
    project_name = profile["fields"].get("project")
    project_candidate = metadata.get(project_name) if project_name else None
    project_field = project_candidate if project_candidate and project_candidate.get("writable") is True else None
    assignments = _assignments(assignment_data if assignment_data is not None else {"transactions": {}}, transactions, project_options, project_field)
    views = _view_names(snapshot)
    records_raw = snapshot.get("records") if isinstance(snapshot, dict) else None
    if not isinstance(records_raw, list):
        raise PlanError("base snapshot.records 必须为数组")
    records: list[dict[str, Any]] = []
    for record in records_raw:
        if not isinstance(record, dict) or not isinstance(record.get("record_id"), str) or not isinstance(record.get("fields"), dict):
            raise PlanError("base snapshot.records 每项必须含 record_id 与 fields")
        records.append(record)

    validation_issues: list[dict[str, Any]] = []
    target_views: dict[str, str] = {}
    for transaction in transactions:
        key = transaction["transaction_key"]
        view = _view_name(profile["view_name_template"], transaction["occurred_at"])
        target_views[key] = view
        if view not in views:
            validation_issues.append({"kind": "missing_year_view", "transaction_key": key, "target_view": view})

    conflicts: list[dict[str, Any]] = []
    blocked_keys: set[str] = set()
    statement_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for transaction in transactions:
        statement_groups[(transaction["occurred_at"], transaction["net_amount"], expense, owner_id)].append(transaction)
    for dedupe_key, group in statement_groups.items():
        if len(group) > 1:
            keys = [item["transaction_key"] for item in group]
            conflicts.append({"kind": "multiple_statement_rows_for_dedupe_key", "dedupe_key": dedupe_key, "transaction_keys": keys})
            blocked_keys.update(keys)

    creates: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    preview_rows = list(skipped)
    for transaction in transactions:
        key = transaction["transaction_key"]
        view = target_views[key]
        assignment = assignments[key]
        if key in blocked_keys:
            preview_rows.append({"transaction_key": key, "action": "conflict", "target_view": view})
            continue
        matches = [record for record in records if _matches_key(record, profile, transaction, owner_id, expense)]
        if len(matches) > 1:
            conflicts.append({"kind": "multiple_base_records_for_dedupe_key", "transaction_key": key, "record_ids": [record["record_id"] for record in matches]})
            preview_rows.append({"transaction_key": key, "action": "conflict", "target_view": view, "record_ids": [record["record_id"] for record in matches]})
            continue
        if matches:
            record = matches[0]
            current_remark = _text(record["fields"].get(profile["fields"]["remark"]))
            if current_remark != transaction["remark"]:
                conflicts.append({"kind": "base_key_remark_conflict", "transaction_key": key, "record_id": record["record_id"], "statement_remark": transaction["remark"], "base_remark": current_remark})
                preview_rows.append({"transaction_key": key, "action": "conflict", "target_view": view, "record_ids": [record["record_id"]]})
                continue
            if _has_project(record, project_name) or not project_name:
                preview_rows.append({"transaction_key": key, "action": "complete", "target_view": view, "record_ids": [record["record_id"]]})
                continue
            if project_field is None:
                pending.append({"transaction_key": key, "record_ids": [record["record_id"]], "reason": assignment["reason"], "target_view": view, "action": "project_field_missing"})
                preview_rows.append({"transaction_key": key, "action": "pending", "target_view": view})
                continue
            if assignment["confidence"] == "high":
                expected = _full_fields(profile, transaction, owner_id, expense, assignment["labels"], project_field)
                updates.append({"record_id": record["record_id"], "transaction_key": key, "target_view": view, "timezone": transaction["timezone"], "fields": {project_name: _project_value(assignment["labels"], project_field)}, "expected_fields": expected})
                preview_rows.append({"transaction_key": key, "action": "backfill", "target_view": view, "record_ids": [record["record_id"]], "labels": assignment["labels"]})
            else:
                pending.append({"transaction_key": key, "record_ids": [record["record_id"]], "reason": assignment["reason"], "target_view": view, "action": "existing_project_empty"})
                preview_rows.append({"transaction_key": key, "action": "pending", "target_view": view})
            continue

        labels = assignment["labels"] if assignment["confidence"] == "high" else []
        row = {"transaction_key": key, "target_view": view, "timezone": transaction["timezone"], "fields": _full_fields(profile, transaction, owner_id, expense, labels, project_field)}
        creates.append(row)
        if project_name and assignment["confidence"] == "low":
            pending.append({"transaction_key": key, "record_ids": [], "reason": assignment["reason"], "target_view": view, "action": "new_project_empty"})
        preview_rows.append({"transaction_key": key, "action": "create", "target_view": view, "labels": labels})

    write_ready = not validation_issues and not conflicts
    executable_creates = creates if write_ready else []
    executable_updates = updates if write_ready else []
    field_names = [profile["fields"][name] for name in ("remark", "date", "amount", "direction", "owner")] + ([project_name] if project_field is not None else [])
    plan = {
        "schema_version": 1,
        "profile_name": profile["profile_name"],
        "base_url": profile["base_url"],
        "table_name": profile["table_name"],
        "owner_id": owner_id,
        "write_ready": write_ready,
        "issues": validation_issues + conflicts,
        "create_rows": executable_creates,
        "update_rows": executable_updates,
        "counts": {"candidates": len(transactions), "skipped": len(skipped), "create": len(creates), "backfill": len(updates), "pending": len(pending), "conflicts": len(conflicts)},
    }
    preview = {"write_ready": write_ready, "rows": preview_rows}
    if write_ready:
        batch_rows: list[list[Any]] = []
        for row in executable_creates:
            values = []
            for field_name in field_names:
                value = row["fields"].get(field_name)
                if field_name == profile["fields"]["amount"] and value is not None:
                    value = float(Decimal(value))
                values.append(value)
            batch_rows.append(values)
        batch_payloads = [{"fields": field_names, "rows": batch_rows[index:index + 200]} for index in range(0, len(batch_rows), 200)]
        if not batch_payloads:
            batch_payloads = [{"fields": field_names, "rows": []}]
    else:
        batch_payloads = [{"blocked": True, "reason": "plan_not_write_ready"}]
    groups: dict[tuple[tuple[str, Any], ...], list[str]] = defaultdict(list)
    for row in executable_updates:
        patch = row["fields"]
        groups[tuple(sorted((key, json.dumps(value, ensure_ascii=False, sort_keys=True)) for key, value in patch.items()))].append(row["record_id"])
    backfills = []
    for patch_items, record_ids in sorted(groups.items()):
        patch = {key: json.loads(value) for key, value in patch_items}
        for index in range(0, len(record_ids), 200):
            backfills.append({"record_id_list": record_ids[index:index + 200], "patch": patch})
    pending_payload = {"write_ready": write_ready, "items": pending}
    conflicts_payload = {"write_ready": write_ready, "items": validation_issues + conflicts}
    return plan, preview, batch_payloads, backfills, pending_payload, conflicts_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="离线构建 Lark Base 导入计划")
    parser.add_argument("--statement", required=True)
    parser.add_argument("--base-snapshot", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--assignments")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = build_plan(_read_json(args.statement, "statement"), _read_json(args.base_snapshot, "base snapshot"), _read_json(args.profile, "profile"), args.owner_id, _read_json(args.assignments, "assignments") if args.assignments else None)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(output_dir, 0o700)
        plan, preview, batch_payloads, backfills, pending, conflicts = result
        _write_json(output_dir / "import-plan.json", plan)
        _write_json(output_dir / "preview.json", preview)
        if len(batch_payloads) == 1:
            _write_json(output_dir / "batch-create.json", batch_payloads[0])
        else:
            for index, payload in enumerate(batch_payloads, start=1):
                _write_json(output_dir / f"batch-create_{index:03d}.json", payload)
        for index, payload in enumerate(backfills, start=1):
            _write_json(output_dir / f"backfill_group_{index:03d}.json", payload)
        _write_json(output_dir / "pending-classification.json", pending)
        _write_json(output_dir / "conflicts.json", conflicts)
        return 0
    except PlanError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
