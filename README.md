# shuanzi-agent-stuff

个人 AI Agent 工具集：存放自用的 Codex Hook 和 Agent Skill。

## 仓库结构

```text
├── codex_pets/ # Codex 自定义 Pet 包与可追溯生成记录
├── hooks/     # Codex 等客户端的 Hook 工具包
└── skills/    # 可复用的 Agent Skill（含 SKILL.md 定义）
```

## Hooks

### [codex-feishu-hook](hooks/codex-feishu-hook/)

Codex 完成一轮工作后，通过飞书群自定义机器人发送完成通知卡片。

- 通过 Codex 用户级 `Stop` Hook 触发，不修改现有 `~/.codex/config.toml` 或顶层 `notify`。
- 支持飞书机器人签名校验；标签、工作目录和最终回复摘要可开关、可裁剪。
- 运行时只依赖 Python 标准库；网络失败只写本地日志，不阻塞 Codex。
- 安装脚本幂等合并 `~/.codex/hooks.json`，不覆盖无关 Hook。

使用与安装详见 [hooks/codex-feishu-hook/README.md](hooks/codex-feishu-hook/README.md)。

## Codex Pets

`codex_pets/` 存放采用 Codex v2 sprite 合同的自定义 Pet：每个最终 atlas 为 `1536×2288` 的 `8×11` 网格，并在 `pet.json` 中声明 `spriteVersionNumber: 2`。

- `niulai/`：可直接安装的黄角牛 Pet 包。
- `claude-code-3d-pet-run/`：Claude Code 3D 的可追溯生成记录；最终 v2 atlas 位于 `final/spritesheet-extended.webp`，并保留 prompts、逐帧素材和 QA 证据。

可按以下方式安装：

```bash
# 黄角牛
PET_DIR="${CODEX_HOME:-$HOME/.codex}/pets/huangjiaoniu"
mkdir -p "$PET_DIR"
cp codex_pets/niulai/pet.json codex_pets/niulai/spritesheet.webp "$PET_DIR/"

# Claude Code 3D
PET_DIR="${CODEX_HOME:-$HOME/.codex}/pets/claude-code-3d"
mkdir -p "$PET_DIR"
cp codex_pets/claude-code-3d-pet-run/final/pet.json "$PET_DIR/"
cp codex_pets/claude-code-3d-pet-run/final/spritesheet-extended.webp "$PET_DIR/spritesheet.webp"
```

## Skills

以下七个技能的唯一维护源已集中到[Home Repo](/Users/xiquandai/vibecoding/home_repo/.agents/skills/)：`codex-thread-orchestration`、`gpt-pro-dual-agent`、`industry-report`、`model-service-benchmark`、`steelman-dialogue`、`translate-article-to-everything-agent`、`wechat-article-workflow-co-gemini`。本仓库原有 `skills/<名称>` 路径保留为绝对符号链接，修改时编辑 Home 中的实际文件。

这些本地入口依赖 Home Repo；单独克隆本仓库时需一并恢复它。Home 当前没有 remote，不能从本仓库的公开远端自动取得共享技能；GitHub 网页中的符号链接也不等同于普通目录浏览。安装器会识别链接来源并复制完整实际文件，覆盖前检查源目标关系；既有入口若已指向同一来源，则保留原入口。

### [travel-reimbursement](skills/travel-reimbursement/)

通过逐轮问答收集人员、行程、票据和支付截图，支持从零开始或先提供一批材料，已有记录时从缺项继续。依据中国科学院软件研究所智能软件研究中心的离线资料核对费用并填写原版 Word，关键电子材料补齐后生成可交给组秘核验的 ZIP，另列账号填写、线下签字和纸质原件交接等人工待办。

调用：`$travel-reimbursement 帮我报销这次出差`。可由下方交互式安装器安装，或复制完整技能目录到客户端的 skills 加载路径。包含脱敏空白模板、离线参考及仅依赖 Python 标准库的填表和打包脚本；规则来源维护日期为 2026-10-23，未重新核验现行效力，其他单位不能直接套用。整理材料不包含发送、ARP 提交或支付。

聚焦测试：`python3 -m unittest discover -s skills/travel-reimbursement/scripts -p 'test_*.py' -v`。

### [model-service-benchmark](skills/model-service-benchmark/)

依据科研 Agent 模型推理服务 Benchmark 规范 revision 85，先确定目标、阶段和预算，再核查已有生成式 LLM 服务，执行性能摸底、容量边界验证或持续运行评估，并产出可复核中文报告。包含规范矩阵、指标口径、A–E 阶段、报告模板与现有工具能力说明；不附带测试客户端或默认部署服务。

调用：`$model-service-benchmark`。可通过下方交互式安装器安装，或单独复制技能目录到客户端的 skills 加载路径。

### [industry-report](skills/industry-report/)

编写、审阅或修改产业与政策专题研究报告：从共性问题组织证据、章节论证和案例分析，分别判断外审问题与建议改法，并按当前授权保护修改范围。包含研究、审阅、真实改写示例和按需使用的交付配套方法。

调用：`$industry-report`。可通过下方交互式安装器安装，或单独复制技能目录到客户端的 skills 加载路径。

### [wechat-article-workflow-co-gemini](skills/wechat-article-workflow-co-gemini/)

与 Codex 逐篇讨论公众号文章方向，搜集素材后交由 Antigravity CLI 的 `gemini-4-argon-high`（`--effort high`）主笔，再由 Codex 独立核验、用户审阅，交回 Gemini 修订并制作 HTML。保留版本、来源、核验意见和可恢复的 CLI 会话记录；交付 Markdown、可复制正文的 HTML 及按需配图，图片由用户在公众号后台上传。

调用：`$wechat-article-workflow-co-gemini 帮我写一篇公众号文章，先讨论思路`。需要已安装、登录且可调用指定模型的 `agy`；调用脚本仅依赖 Python 3 标准库。可通过下方安装器安装，不包含草稿箱接入或发布。

聚焦测试：`python3 -m unittest discover -s skills/wechat-article-workflow-co-gemini/scripts -p 'test_*.py' -v`。运行完成不等于文章验收；本地预览、公众号粘贴和图片上传分别核对。

### [codex-thread-orchestration](skills/codex-thread-orchestration/)

在用户明确要求时创建、管理或协调独立 Codex 聊天：可只查已有聊天进度，也可隔离并行写入、跟进依赖并按授权集成结果。

### [gpt-pro-dual-agent](skills/gpt-pro-dual-agent/)

组织高可信的双代理协作：Codex 担任总负责人，将已登录的 ChatGPT Pro 对话作为外部高级研究/设计/实现代理。涵盖协作契约、GitHub connector 或脱敏源码包提供上下文、长任务监控与会话恢复、外部补丁的本地独立审查与验收。

### [translate-article-to-everything-agent](skills/translate-article-to-everything-agent/)

抓取可访问的网页文章，完整翻译为简体中文，并归档到飞书知识库固定的 Everything Agent 节点。遇到登录墙/付费墙/反爬时 fail closed，不创建不完整文档。

### [import-pay-check-to-lark-base](skills/import-pay-check-to-lark-base/)

将支付账单导入飞书多维表格（Base）个人账本：自动识别账单、净额去重、脱敏预览确认后写入。v1 仅支持微信支付 XLSX 格式，保留 adapter 扩展接口。

### [steelman-dialogue](skills/steelman-dialogue/)

对问题或方案做双向钢人论证。默认先呈现正反两方最强理由并问一个关键问题，再基于回答给出判断和建议；用户要求一次完成时，按现有条件直接判断。

## 使用方式

在仓库根目录运行交互式安装脚本：

```bash
./install.sh
```

安装器会自动识别当前环境已安装的 Agent（Claude Code、Codex），也支持安装到通用 Agent 目录（`~/.agents/`）；可逐项勾选要安装的 hooks 和 skills。重复执行时同名内容会被覆盖，以最后一次安装为准。

也可以用环境变量覆盖目标目录：`CLAUDE_HOME`、`CODEX_HOME`、`AGENTS_HOME`。

注意：当前 hooks 仅支持 Codex；选择其他 Agent 时会自动跳过 hooks，只安装 skills。

如需单独安装，仍可按各子目录 README 操作：Hooks 进入对应目录运行 `install.sh`；Skills 将对应目录放入 Agent 客户端的 skills 加载路径，由客户端按 `SKILL.md` 的 `description` 自动匹配触发。
