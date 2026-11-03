#!/usr/bin/env python3
"""按已核对清单生成给组秘的差旅 ZIP；只使用 Python 标准库。"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import unicodedata
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile


def filename(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须为非空文件名")
    value = unicodedata.normalize("NFC", value)
    if (value in (".", "..") or value != value.strip() or value.endswith(".")
            or any(char in '<>:"/\\|?*' or unicodedata.category(char) == "Cc"
                   for char in value)):
        raise ValueError(f"{label} 必须为单层文件名，不能包含路径或无效字符")
    stem = value.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or stem in {
            f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)}:
        raise ValueError(f"{label} 使用了系统保留文件名")
    return value


def require_keys(value, keys):
    if not isinstance(value, dict) or value.keys() != set(keys):
        raise ValueError(f"清单字段必须恰为 {', '.join(keys)}")


def package(manifest_path, output_dir):
    """清单相对路径以清单所在目录为基准，返回校验后的新 ZIP 路径。"""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require_keys(manifest, ("title", "blockers", "files"))
    title = filename(manifest["title"], "申请标题")
    if not isinstance(manifest["blockers"], list):
        raise ValueError("blockers 必须为列表，明确记录尚未解决的缺件或冲突")
    if manifest["blockers"]:
        raise ValueError("仍有缺件或冲突，补齐并核对后再打包")
    if not isinstance(manifest["files"], list) or not manifest["files"]:
        raise ValueError("files 必须为非空文件清单")

    entries = {}
    names = set()
    has_form = False
    for item in manifest["files"]:
        require_keys(item, ("source", "name", "role"))
        name = filename(item["name"], "包内文件名")
        if name.casefold() in names:
            raise ValueError(f"包内文件名重复：{name}")
        names.add(name.casefold())
        if item["role"] not in ("form", "attachment"):
            raise ValueError("role 必须为 form 或 attachment")
        has_form = has_form or item["role"] == "form"
        source = item["source"]
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source 必须为非空文件路径")
        source = (manifest_path.parent / source).resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"源文件必须为普通文件：{source}")
        content = source.read_bytes()
        if not content:
            raise ValueError(f"源文件为空：{source}")
        entries[f"{title}/{name}"] = content
    if not has_form:
        raise ValueError("清单至少需要一份已核对的报销表（role=form）")

    output_dir = Path(output_dir).resolve()
    output = output_dir / f"{title}.zip"
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"输出已存在：{output}")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".reimbursement-", suffix=".zip", dir=output_dir,
                                     delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        with ZipFile(temporary_path) as archive:
            if archive.namelist() != list(entries) or archive.testzip() is not None:
                raise ValueError("ZIP 目录、条目数或 CRC 校验失败")
            for name, content in entries.items():
                if archive.read(name) != content:
                    raise ValueError(f"ZIP 原字节核对失败：{name}")
        # 同目录硬链接原子发布，已有结果（含并发生成）会使 link 失败。
        os.link(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="已核对的 JSON 文件清单")
    parser.add_argument("--output-dir", type=Path, required=True, help="新 ZIP 所在目录")
    args = parser.parse_args()
    try:
        output = package(args.manifest, args.output_dir)
    except (ValueError, OSError, BadZipFile, TypeError) as error:
        print(f"未生成组秘 ZIP：{error}", file=sys.stderr)
        return 1
    print(json.dumps({"文件": str(output), "状态": "已按清单打包并通过 ZIP 回读校验"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
