# Base Profile 与运行时契约

Profile 使用扁平 schema。用户可以要求保存完整的 `base_url`，包括 URL 中已有的查询参数；不要另存从 URL 解析出的 `base_token`、`table_id`、`view_id` 或人员 ID。账单原文只能在本轮受保护的运行时上下文中保存。执行所需 owner ID 可暂存于权限为 0600 的本轮 plan/payload，但不得进入 Profile、日志、对话或最终回复。

## Profile

```json
{
  "profile_name": "personal-ledger",
  "base_url": "https://...",
  "table_name": "总明细",
  "view_name_template": "{year} 年明细",
  "owner_name": "姓名",
  "fields": {
    "remark": "备注",
    "date": "日期",
    "amount": "金额",
    "direction": "收支",
    "owner": "责任人",
    "project": "项目"
  },
  "values": { "expense": "支出" },
  "dedupe_fields": ["日期", "金额", "收支", "责任人"]
}
```

将 `{year}` 替换为 `occurred_at` 在账单时区中的年份。`build_lark_plan.py` 要求 `dedupe_fields` 严格等于 `date`、`amount`、`direction`、`owner` 四个实际字段名，且同顺序。始终写入 `table_name`，把 `view_name_template` 仅作为创建后验收的目标视图；视图不存在时将计划标为不可写，不创建表或视图。

## Base snapshot 输入

将 URL 解析、Base owner、表、字段和视图的真实返回归约为以下输入。`base_url` 必须精确等于本轮 runtime Profile；`table_name` 必须与 Profile 相同；`records` 必须覆盖该表的全部分页记录并标记 `records_complete: true`，`views` 必须列出全部视图名称并标记 `views_complete: true`。任一条件不满足时 planner 必须失败关闭。

```json
{
  "base_url": "https://...",
  "table_name": "总明细",
  "records_complete": true,
  "views_complete": true,
  "fields": [
    { "name": "备注", "type": "text", "writable": true },
    { "name": "日期", "type": "datetime", "writable": true },
    { "name": "金额", "type": "number", "writable": true },
    { "name": "收支", "type": "select", "writable": true, "multiple": false, "options": [{ "name": "支出" }] },
    { "name": "责任人", "type": "user", "writable": true },
    { "name": "项目", "type": "select", "writable": true, "multiple": true, "options": [{ "name": "餐饮" }] }
  ],
  "views": [{ "name": "2026 年明细" }],
  "records": [
    { "record_id": "rec_xxx", "fields": { "日期": "2026-08-01 12:34:56", "金额": 70, "收支": "支出", "责任人": [{ "id": "runtime-only" }] } }
  ]
}
```

`build_lark_plan.py` 校验 Base URL、完整性标志、语义字段类型、`writable` 和现有 options。五个必填字段任一不可写时失败关闭；可选项目字段不存在或不可写时降级为低置信 pending，不写项目。将实际 owner ID 仅传给 `--owner-id`，不要写回 Profile 或预览。

## Assignments 输入

将分类结果按 `transaction_key` 提供；没有分类时可省略该 key。`high` 必须带非空 `labels`；`low` 应使用空 `labels`，以便把项目留空而不阻断其他字段。将未知项目 option、单选项目字段中的多个高置信标签、或无项目字段的高置信分类规范化为 `low` 与空 `labels`，并记录 `pending`，不要使 plan 不可写。

```json
{
  "transactions": {
    "source-audit-key": {
      "labels": ["餐饮"],
      "confidence": "high",
      "reason": "history_exact_unique"
    },
    "another-source-audit-key": {
      "labels": [],
      "confidence": "low",
      "reason": "history_ambiguous"
    }
  }
}
```

## Plan 输出

`build_lark_plan.py` 写入 `import-plan.json`、`preview.json`、`batch-create.json`、零或多个 `backfill_group_*.json`、`pending-classification.json` 和 `conflicts.json`。主计划形状如下：

```json
{
  "schema_version": 1,
  "profile_name": "personal-ledger",
  "base_url": "https://...",
  "table_name": "总明细",
  "owner_id": "runtime-only",
  "write_ready": true,
  "issues": [],
  "create_rows": [{ "transaction_key": "source-audit-key", "target_view": "2026 年明细", "timezone": "Asia/Shanghai", "fields": {} }],
  "update_rows": [{ "record_id": "rec_xxx", "transaction_key": "source-audit-key", "target_view": "2026 年明细", "timezone": "Asia/Shanghai", "fields": {}, "expected_fields": {} }],
  "counts": { "candidates": 1, "skipped": 0, "create": 1, "backfill": 1, "pending": 0, "conflicts": 0 }
}
```

只执行 `write_ready: true` 的 plan。`counts` 精确包含 `candidates`、`skipped`、`create`、`backfill`、`pending`、`conflicts`；`pending` 仅为提示，不使无冲突计划不可写。每个 batch create 最多 200 行：仅一批时输出 `batch-create.json`，多批时输出 `batch-create_001.json`、`batch-create_002.json` 等，每份形状均为 `{ "fields": ["..."], "rows": [["..."]] }`；按 `fields` 顺序将每行交给 batch create，并跳过空 `rows`。每份 `backfill_group_*.json` 的 `record_id_list` 最多 200 个，形状为 `{ "record_id_list": ["rec_xxx"], "patch": { "项目": ["餐饮"] } }`；按同一 `patch` 分片后应用。`pending-classification.json` 与 `conflicts.json` 永不写入 Base；`write_ready: false` 时每个 create artifact 是 `{ "blocked": true, "reason": "plan_not_write_ready" }`。

## Write result、readback 与 validator 输出

写入层必须按 `create_rows`、`update_rows` 的原有顺序记录成功 ID，且两数组没有重复 ID：

```json
{
  "created_record_ids": ["rec_created"],
  "updated_record_ids": ["rec_updated"],
  "ignored_fields": [],
  "warnings": [],
  "failures": []
}
```

回读必须同时提供每个 record 的字段和以视图名分组的 record ID：

```json
{
  "records": [
    { "record_id": "rec_created", "fields": { "备注": "受保护原文", "日期": "2026-08-01 12:34:56", "金额": 70, "收支": "支出", "责任人": [{ "id": "runtime-only" }] } }
  ],
  "view_record_ids_by_name": { "2026 年明细": ["rec_created", "rec_updated"] }
}
```

`validate_readback.py` 输出：

```json
{
  "ok": true,
  "plan_profile_name": "personal-ledger",
  "verified_records": [{ "record_id": "rec_created", "transaction_key": "source-audit-key", "target_view": "2026 年明细" }],
  "errors": []
}
```

将 `ok: false` 视为验收失败。`ignored_fields`、`warnings` 或 `failures` 只要非空，validator 同样失败；不要用 batch 返回成功替代字段与年度视图的逐 ID 回读。
