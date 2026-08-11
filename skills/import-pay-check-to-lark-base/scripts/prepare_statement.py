"""Prepare a detected payment statement for a later, explicitly approved import."""

from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import tempfile

from adapters import get_adapter, iter_adapters


def _money(value):
    return format(value, ".2f")


def _select_adapter(input_path, requested_format):
    if requested_format != "auto":
        adapter = get_adapter(requested_format)
        report = adapter.detect(input_path)
        if report["confidence"] < 80:
            raise ValueError("explicit format rejected input: " + "; ".join(report["evidence"]))
        return adapter, report
    reports = [(adapter, adapter.detect(input_path)) for adapter in iter_adapters()]
    if not reports:
        raise ValueError("no statement adapters are registered")
    reports.sort(key=lambda item: (-item[1]["confidence"], item[1]["format"]))
    best_adapter, best = reports[0]
    second = reports[1][1]["confidence"] if len(reports) > 1 else -100
    if best["confidence"] < 80 or best["confidence"] - second < 20:
        raise ValueError("automatic format detection is not decisive: " + json.dumps([item[1] for item in reports], ensure_ascii=False))
    return best_adapter, best


def _summary(batch):
    transactions = batch["transactions"]
    directions = {}
    months = defaultdict(lambda: {"count": 0, "amount": Decimal("0.00")})
    for direction in ("income", "expense", "neutral"):
        records = [item for item in transactions if item["direction"] == direction]
        directions[direction] = {
            "count": len(records),
            "original_amount": _money(sum((Decimal(item["original_amount"]) for item in records), Decimal("0.00"))),
            "net_amount": _money(sum((Decimal(item["net_amount"]) for item in records), Decimal("0.00"))),
        }
    for item in (item for item in transactions if item["write_candidate"]):
        month = item["occurred_at"][:7] if item["occurred_at"] else "invalid"
        value = months[month]
        value["count"] += 1
        value["amount"] += Decimal(item["net_amount"])
    candidates = [item for item in transactions if item["write_candidate"]]
    refunds = [item for item in transactions if Decimal(item["refund_amount"]) > 0]
    return {
        "schema_version": 1,
        "source_format": batch["source_format"],
        "file_sha256": batch["file_sha256"],
        "write_ready": batch["write_ready"],
        "original": {"transaction_count": len(transactions), "amount": _money(sum((Decimal(item["original_amount"]) for item in transactions), Decimal("0.00")))},
        "directions": directions,
        "refunds": {"transaction_count": len(refunds), "amount": _money(sum((Decimal(item["refund_amount"]) for item in refunds), Decimal("0.00")))},
        "candidates": {"transaction_count": len(candidates), "amount": _money(sum((Decimal(item["net_amount"]) for item in candidates), Decimal("0.00")))},
        "months": {month: {"count": values["count"], "amount": _money(values["amount"])} for month, values in sorted(months.items())},
    }


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)
    os.chmod(path, 0o600)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="source statement XLSX")
    parser.add_argument("--format", default="auto", help="auto or a registered adapter id")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    adapter, detection = _select_adapter(args.input, args.format)
    batch = adapter.parse(args.input)
    batch["detection"] = detection
    manifest = {key: batch[key] for key in ("schema_version", "source_format", "file_sha256", "sheet_name", "header_row", "detection", "write_ready", "transactions")}
    issues = {key: batch[key] for key in ("schema_version", "source_format", "file_sha256", "write_ready", "exceptions")}
    output = Path(args.output_dir)
    _write_json(output / "statement-manifest.json", manifest)
    _write_json(output / "statement-summary.json", _summary(batch))
    _write_json(output / "statement-issues.json", issues)
    return 0 if batch["write_ready"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print("prepare_statement: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
