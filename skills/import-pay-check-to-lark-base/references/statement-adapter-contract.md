# 微信支付 XLSX 账单适配器契约

## Registry 与范围

以 adapter registry 路由来源；v1 只注册 `wechat-pay-xlsx`。registry 可增加新的 adapter，但当前不得把任何其他格式识别、宣传、转换或导入为受支持来源。

`wechat-pay-xlsx` 只接受单个未加密微信支付 `.xlsx`。先确认微信账单标记，再定位含 `交易时间`、`收/支`、`金额(元)` 的唯一表头行；缺列、来源无法确认或表头有歧义时拒绝。

每个 registry adapter 必须提供 `detect(path)` 与 `parse(path)`：前者返回 `format`、0–100 `confidence` 和结构 `evidence`，后者返回下述 `StatementBatch`。自动识别要求唯一最高分不低于 80 且领先第二名至少 20；显式 `--format` 仍须通过该 adapter 的结构识别，不得强制解析不匹配文件。

## `StatementBatch`

`prepare_statement.py` 写出 `statement-manifest.json`。它是传入 `build_lark_plan.py --statement` 的 `StatementBatch`；必须使用 `schema_version: 1` 和 `source_format: "wechat-pay-xlsx"`，所有金额均为两位小数的正数字符串，不使用 float 或符号金额。使用 bundled workspace Python 中已有的 `openpyxl`；不要新增 requirements 文件或运行安装命令。

```json
{
  "schema_version": 1,
  "source_format": "wechat-pay-xlsx",
  "file_sha256": "...",
  "sheet_name": "Sheet1",
  "header_row": 18,
  "detection": { "format": "wechat-pay-xlsx", "confidence": 85, "evidence": ["header row 17"] },
  "write_ready": true,
  "transactions": [
    {
      "source_format": "wechat-pay-xlsx",
      "file_sha256": "...",
      "source_row": 18,
      "transaction_id": "受保护原文",
      "transaction_key": "sha256-source-audit-key",
      "occurred_at": "2026-08-01T12:34:56+08:00",
      "timezone": "Asia/Shanghai",
      "currency": "CNY",
      "direction": "expense",
      "original_amount": "100.00",
      "refund_amount": "30.00",
      "net_amount": "70.00",
      "counterparty": "受保护原文",
      "product": "受保护原文",
      "status": "支付成功",
      "original_note": "受保护原文",
      "normalized_note": "受保护原文",
      "write_candidate": true,
      "exclusion_reason": null
    }
  ]
}
```

每个 transaction 必须携带有效 IANA `timezone`；`build_lark_plan.py` 只消费 `transaction_key`、`write_candidate: true`、秒级 `occurred_at`、`timezone`、正数 `net_amount` 和 `normalized_note`。不得增加 `date`、`amount` 或 `remark` 投影，也不得把原始交易 ID 写入 Base。将无 offset 的 `occurred_at` 解释为该 transaction 的 `timezone`；将 Base epoch readback 用同一时区转换后再按秒比较。`statement-issues.json` 另行保存 `exceptions`；`statement-summary.json` 仅用于脱敏预览。

`statement-issues.json` 的顶层形状为 `{ "schema_version": 1, "source_format": "wechat-pay-xlsx", "file_sha256": "...", "write_ready": true, "exceptions": [] }`。`statement-summary.json.months` 只聚合 `write_candidate: true` 的行，形状为 `{ "YYYY-MM": { "count": 1, "amount": "70.00" } }`。

## 退款与候选规则

- 将同一交易的部分退款折算为 `net_amount = original_amount - refund_amount`；只有净额大于零、且退款收入与支出双向对账时，才保留为 `write_candidate: true`。先按交易对方/商户文本加金额匹配；若微信导出的退款方名称变化，只允许在同金额未匹配双方均唯一时回退配对。
- 将全额退款标记为 `write_candidate: false` 并从写入候选中排除；保留来源审计信息。
- 逐记录拒绝退款额为负、超过原金额、无法关联原交易、币种不一致或无法确定净额的异常退款；将错误写入 `exceptions` 并将相关行设为不可写。此类行不阻断其他有效候选；仅账单表头的总笔数、收支笔数或金额对账异常会令 batch `write_ready: false` 并阻断本次写入。
- 只将可写的 `expense` 行设为 `write_candidate: true`。其他方向保留在 batch 审计中，但不得写入此 Profile。
- 将 `transaction_key` 和 `transaction_id` 只用于来源审计、assignment 关联和问题定位。Base 去重只能使用完整交易时间、净额、`支出` 和责任人。

将包含账单原文的字段保存在权限为 600 的临时文件；预览和日志只显示脱敏值。
