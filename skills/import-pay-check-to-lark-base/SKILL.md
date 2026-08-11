---
name: import-pay-check-to-lark-base
description: 导入支付账单或微信支付 XLSX 账单到飞书 Base。用户要求自动识别账单、净额去重、预览或核对待导入记录，并在明确确认后写入个人账本 Base 时使用；v1 仅支持微信 XLSX。
---

# 支付账单导入飞书 Base

只启用 `wechat-pay-xlsx` adapter。保留 adapter registry 的扩展接口，但不要宣传、识别、转换或导入微信以外格式。

## 先读规则

1. 读取 `$lark-base` 的 `SKILL.md`，再读取其 `lark-base-record-batch-create.md`、`lark-base-record-batch-update.md` 和 `lark-base-cell-value.md`。
2. 读取本 Skill 的 [账单适配器契约](references/statement-adapter-contract.md)、[Base Profile 与运行时契约](references/base-profile-schema.md)、[项目分类策略](references/project-classification-policy.md)。默认账本读取 [personal-ledger-profile.json](references/personal-ledger-profile.json)。
3. 将用户明确提供的 Profile 或 Base URL 作为本次覆盖项；不要回写默认 Profile。

## 保护边界

- 使用 `umask 077; mktemp -d` 建立唯一临时目录；只在其中保存账单副本、解析产物、请求 JSON 和回读结果。
- 不在对话、日志、文件名、提交或最终回复中输出完整账单行、Base token、交易单号、商户单号、联系方式或人员 ID。预览只展示完成核对所需的最少字段，并按需脱敏。
- 不修改原始 XLSX，不删除任何 Base 记录，不创建字段、视图或 select 选项。
- 不覆盖已有非空 `项目`；低置信分类保持项目为空，但仍可写入其他字段。

## 导入流程

1. 用 `lark-cli base +url-resolve --url "<Base URL>" --as user` 解析真实 `base_token`、`table_id` 和 `view_id`。再读取 Base、目标 `总明细` 表、字段和全部年度视图，按真实返回确认 Profile 的表名、字段名、字段类型、可写性和既有选项。
2. 以 Profile 中的姓名实时解析 `责任人`。遇到同名、找不到人、人员字段不可写或权限不足时停止并说明；不要猜 ID。只可在权限为 0600 的本轮 plan/payload 中暂存 `open_id`，不得写入 Profile、日志、对话或最终回复。
3. 使用 bundled workspace Python（已包含 `openpyxl`）运行 `prepare_statement.py`；不要新增 `requirements.txt`、修改系统 Python 或临时安装依赖。验证 `StatementBatch` 的 `schema_version: 1`、已注册的 `source_format` 和每行 IANA `timezone`；v1 registry 只含 `wechat-pay-xlsx`。保留完整交易时间、时区、币种、正数字符串金额和退款净额；`transaction_id` 只能用于来源审计和 artifact 关联，不能参与 Base 去重或写入字段。`statement-manifest.json.write_ready` 为 `false` 时停止，不构建或执行写入计划。
4. 读取 `总明细` 表及其全部视图的完整 Base snapshot；按分页读取，不能把首屏当作全量。写入本轮 Profile 的完整 `base_url`、`records_complete: true` 和 `views_complete: true`；任一缺失、不一致或为 `false` 时让 planner 失败关闭。用完整交易时间、净额、`支出` 和已解析责任人进行精确去重；同键备注冲突时拒绝该行，不要猜测重复关系。将 epoch readback 按交易的 `timezone` 解析。
5. 从 snapshot 中读取已有非空 `项目` 的历史记录，按分类策略生成 assignments。高置信新记录直接带项目写入；未知项目 option、单选字段的多个高置信标签或无项目字段时，一律降级为 `low`、空 `labels` 并进入 `pending`。低置信记录以 `项目: null` 写入其他字段，不得因此阻断本批其他安全记录。
6. 构建 plan：列出 `create`、精确重复、项目回填、拒绝项和低置信项。明确显示写入 `总明细`、每行目标 `{year} 年明细` 视图、分类依据和数量；先展示脱敏预览并等待用户明确确认。
7. 收到确认后，重新读取 Base snapshot、重新去重、重新分类并重建 plan。若结果、字段、权限、视图或可选项变化，展示新预览并再次等待确认。
8. 先运行 `build_lark_plan.py` 生成离线 dry-run；验证 `write_ready`、字段值、select 选项、年度视图和冲突结果。dry-run 不得写 Base。
9. 按名称顺序执行所有 `batch-create*.json`：单个创建文件为 `batch-create.json`，多个为 `batch-create_001.json`、`batch-create_002.json` 等。每份精确为 `fields + rows`，每批最多 200 行；`rows` 为空时跳过创建调用。高置信项目直接包含在 create rows。将每份 `backfill_group_*.json` 的 `record_id_list + patch` 也按最多 200 条分片，用 `+record-batch-update` 仅回填精确重复且项目为空的高置信记录。不要用它处理逐行不同的 patch。
10. 仅在 `1254291` 时对当前批次作一次短暂等待后重试；其他错误、第二次 `1254291`、`ignored_fields`、选项不匹配或部分失败均停止，报告已写入的 record ID，不删除或回滚。
11. 按每个成功 record ID 用 `+record-get` 回读 `总明细`，并读取目标年度视图的 record ID；用 `validate_readback.py` 同时校验字段和年度视图归属。只有全部预期字段和视图均一致时才报告导入完成。

## 脚本入口

在本 Skill 目录中运行：

```bash
<python-with-openpyxl> scripts/prepare_statement.py --input <file> --format auto --output-dir <private-dir>
python3 scripts/build_lark_plan.py --statement <manifest> --base-snapshot <snapshot> --profile <profile> --owner-id <runtime-id> --assignments <assignments> --output-dir <private-dir>
python3 scripts/validate_readback.py --plan <plan> --write-result <result> --readback <readback> --output <validation>
```

`--format` 可显式传 registry adapter ID；显式格式仍执行结构检测。`--assignments` 可省略，此时所有候选项目均按低置信度留空。

## 输出

先输出预览：来源、`总明细`、目标年度视图、总行数、可创建数、重复数、回填数、拒绝数、低置信数和脱敏样例。确认后的输出再列出 dry-run、写入批次、回读验收和未完成项。

保留临时目录直到用户确认结果可用；只清理本次生成的临时产物，绝不删除源文件或 Base 数据。
