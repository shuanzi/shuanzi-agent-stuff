# shuanzi-agent-stuff

个人 AI Agent 工具集：存放自用的 Codex Hook 和 Agent Skill。

## 仓库结构

```text
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

## Skills

### [codex-thread-orchestration](skills/codex-thread-orchestration/)

编排包含多个阶段或子任务的 Codex thread：负责任务拆解、隔离 branch/worktree、依赖调度、变更集成、校验和最终汇报。

### [gpt-pro-dual-agent](skills/gpt-pro-dual-agent/)

组织高可信的双代理协作：Codex 担任总负责人，将已登录的 ChatGPT Pro 对话作为外部高级研究/设计/实现代理。涵盖协作契约、GitHub connector 或脱敏源码包提供上下文、长任务监控与会话恢复、外部补丁的本地独立审查与验收。

### [translate-article-to-everything-agent](skills/translate-article-to-everything-agent/)

抓取可访问的网页文章，完整翻译为简体中文，并归档到飞书知识库固定的 Everything Agent 节点。遇到登录墙/付费墙/反爬时 fail closed，不创建不完整文档。

### [import-pay-check-to-lark-base](skills/import-pay-check-to-lark-base/)

将支付账单导入飞书多维表格（Base）个人账本：自动识别账单、净额去重、脱敏预览确认后写入。v1 仅支持微信支付 XLSX 格式，保留 adapter 扩展接口。

### [steelman-dialogue](skills/steelman-dialogue/)

按两阶段流程对问题或方案进行双向钢人论证：先重述问题、呈现正反两方最强论证并提出一个关键问题，再基于回答给出判断和行动建议。

## 使用方式

- **Hooks**：进入对应目录，按各自 README 运行 `install.sh` 安装。
- **Skills**：将对应目录放入 Agent 客户端的 skills 加载路径（如 `~/.agents/skills/`），由客户端按 `SKILL.md` 的 `description` 自动匹配触发。
