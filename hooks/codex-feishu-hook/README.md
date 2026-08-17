# Codex 飞书完成通知 Hook

当 Codex 完成一轮工作后，通过飞书群自定义机器人发送一条通知。

本工具包通过 Codex 用户级 `Stop` Hook 触发通知，不修改现有的 `~/.codex/config.toml` 或顶层 `notify`。运行时只依赖 Python 标准库，不依赖 `requests` 或其他第三方包。

## 能力范围

- 每次 `Stop` 事件发送一张飞书交互式消息卡片。
- 支持飞书机器人签名校验。
- 支持标签、工作目录和最终回复摘要的开关与裁剪。
- 不发送 `input-messages`，也不读取或上传完整会话 transcript。
- 网络失败、飞书拒绝或配置错误默认只写本地日志，不阻塞 Codex 完成本轮工作。
- 安装脚本幂等合并 `~/.codex/hooks.json`，不会覆盖无关 Hook 或顶层 `notify`。

## 支持环境

- macOS、Linux 或 WSL
- Bash
- Python 3.9 或更高版本
- 已启用 Hooks 的 Codex 本地客户端
- 能访问飞书开放平台 Webhook 的网络

Windows 原生 PowerShell 安装器未包含在这一版中，但 Python 通知脚本本身没有第三方依赖。

## 包结构

```text
codex-feishu-hook/
├── bin/codex_feishu_notify.py       # 通知适配器
├── config/config.example.json       # 配置示例
├── examples/                        # 测试事件和手工测试脚本
├── tests/                           # 单元与离线 HTTP 集成测试
├── install.sh                       # 安装或更新
├── uninstall.sh                     # 卸载
└── README.md
```

## 一、创建飞书机器人

在目标飞书群中添加“自定义机器人”，取得：

- Webhook URL
- 签名密钥，可选但推荐开启

Webhook URL 与签名密钥都应视为凭证，不要写入项目仓库、`AGENTS.md` 或可提交的 `.codex/` 文件。

## 二、安装或更新

解压后进入目录：

```bash
cd codex-feishu-hook
```

直接运行安装器，所有设置均会在交互中完成，凭证不会写入 shell history：

```bash
./install.sh
```

安装器依次询问：

- 飞书机器人 Webhook URL：必填，必须以 `https://` 开头。
- 飞书签名密钥：可选，输入时隐藏；未开启签名校验可直接回车。
- 是否发送最终回复摘要：`Y/n`，默认发送。
- 是否发送绝对工作目录：`Y/n`，默认发送。
- 摘要上限：`0～4000`，默认 `4000`（基本不截断，接近飞书自定义机器人请求体上限的安全边界）。
- Hook 标签：可选；为空时通知不显示标签。
- 是否立即发送真实测试消息：`y/N`，默认不发送。

典型交互如下；签名密钥的实际输入不会回显：

```text
飞书机器人 Webhook URL（必填）: https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxx
飞书签名密钥（可选，直接回车跳过）: [hidden]
发送 Codex 最终回复摘要？[Y/n]: y
发送绝对工作目录？[Y/n]: y
摘要上限（0～4000，默认 4000）:
Hook 标签（可选，直接回车跳过）: P6
安装后立即发送真实测试消息？[y/N]: n
```

安装器不接受上述设置的命令行参数或凭证环境变量。重复执行 `./install.sh` 会重新收集并更新私有配置。

安装完成后重启 Codex。

## 三、安装结果

安装器默认创建：

```text
~/.codex/hooks/codex_feishu_notify.py
~/.config/codex-feishu/config.json
~/.codex/log/feishu-notify.log
~/.codex/hooks.json
```

并在 `~/.codex/hooks.json` 中追加一个受管理的 `Stop` Hook：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /Users/你的用户名/.codex/hooks/codex_feishu_notify.py",
            "timeout": 5,
            "statusMessage": "Sending Feishu completion notification"
          }
        ]
      }
    ]
  }
}
```

如果已有 `hooks.json`，安装器会追加独立的 `Stop` Hook group，保留 Otty、其他 Hook 和现有顶层 `notify`。重启 Codex 后使用 `/hooks` 审核并信任新增 Hook。

## 四、通知示例

飞书中会显示为绿色 Header 的宽屏消息卡片，项目元数据和结果摘要分区展示：

```text
✅ Codex 本轮已完成
标签：P6
项目：android-to-harmonyos
目录：/Users/你的用户名/Documents/code/android-to-harmonyos
时间：2026-07-22 15:30:00 +08

结果摘要：
已完成当前阶段实现，测试全部通过。
```

默认行为：

- 项目名取当前 `cwd` 最后一段。
- 标签的连续空白折叠为一个普通空格；空标签不显示。
- 最终回复会去掉多余空行，默认截断到 4000 字（飞书自定义机器人请求体约 20KB 上限内的安全值）。
- 不发送用户输入。
- 不发送 thread ID。
- 默认发送绝对工作目录；可在安装交互中关闭。

## 五、手工测试

使用已经安装的私有配置发送测试事件：

```bash
./examples/send-test.sh
```

或直接模拟 Codex `Stop` Hook：

```bash
CODEX_FEISHU_STRICT=1 \
CODEX_FEISHU_CONFIG="$HOME/.config/codex-feishu/config.json" \
python3 bin/codex_feishu_notify.py < examples/stop-event.json
```

`CODEX_FEISHU_STRICT=1` 只建议用于手工测试：发送失败时返回非零状态并把错误写到 stderr。Codex 正常调用时不启用 strict，以确保通知异常不会影响任务完成。

## 六、私有配置

默认位置：

```text
${XDG_CONFIG_HOME:-$HOME/.config}/codex-feishu/config.json
```

完整字段：

```json
{
  "enabled": true,
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/replace-me",
  "sign_secret": "",
  "tag": "",
  "include_summary": true,
  "summary_max_chars": 4000,
  "include_cwd": true
}
```

配置文件权限由安装器设置为 `0600`，目录权限设置为 `0700`。

可用环境变量覆盖默认路径：

```text
CODEX_FEISHU_CONFIG=/custom/path/config.json
CODEX_FEISHU_LOG=/custom/path/notify.log
CODEX_FEISHU_STRICT=1
CODEX_HOME=/custom/codex/home
XDG_CONFIG_HOME=/custom/config/home
```

## 七、Hook 信任

安装器会把飞书处理器追加到用户级 `~/.codex/hooks.json`。Codex 会并发运行同一 `Stop` 事件的所有匹配 Hook，因此它可以与现有 Computer Use `notify`、Otty Hook 及其他 Hook 同时生效。

新增或变更的非托管 Hook 需要审核。重启 Codex 后执行 `/hooks`，检查命令路径并信任飞书 Hook。适配器从 stdin 读取 `Stop` 事件，向 stdout 输出合法 JSON，且通知失败只写本地日志，不会阻止本轮结束。

## 八、错误处理与排查

默认日志：

```text
${CODEX_HOME:-$HOME/.codex}/log/feishu-notify.log
```

查看最近错误：

```bash
tail -n 50 "$HOME/.codex/log/feishu-notify.log"
```

常见问题：

### 没有收到通知

检查：

```bash
python3 --version
python3 -m json.tool "$HOME/.codex/hooks.json"
./examples/send-test.sh
```

确认已重启 Codex，并通过 `/hooks` 信任飞书 Hook。

### 飞书提示签名失败

确认：

- 飞书机器人已开启签名校验。
- `sign_secret` 与飞书安全设置中的密钥完全一致。
- 本机时间准确；签名使用当前 Unix 时间戳。

### 安装器提示 Hook 配置无效

安装器会在写入前校验 `~/.codex/hooks.json`。使用下列命令定位 JSON 语法或结构问题：

```bash
python3 -m json.tool "$HOME/.codex/hooks.json"
```

如果提示已有未受管的飞书 `Stop` Hook，请先人工确认其用途；安装器不会自动覆盖未知 Hook。

### Codex 正常完成但日志有网络错误

这是预期的降级方式。通知网络故障只记录日志，适配器默认返回成功，不会把已经完成的工作标记为失败。

## 十、卸载

移除受管的用户级 `Stop` Hook 和已安装脚本，但保留私有 Webhook 配置：

```bash
./uninstall.sh
```

同时删除私有配置和通知日志：

```bash
./uninstall.sh --purge
```

## 十一、运行测试

所有测试都不访问真实飞书；HTTP 集成测试使用本机临时服务器：

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q bin tests
bash -n install.sh uninstall.sh examples/send-test.sh
```

## 十二、安全边界

这一版有意不实现：

- 上传完整会话 transcript
- 发送用户原始 Prompt
- 发送完整 Git diff
- 调用第二个 LLM 生成通知摘要
- 后台消息队列和无限重试
- 使用 Stop Hook 自动要求 Codex 继续工作

这样可以将通知系统保持为一个低耦合的“旁路提醒”，而不是介入 Codex 的任务控制和结果判定。

## 官方参考

- Codex Advanced Configuration：`https://developers.openai.com/codex/config-advanced/`
- Codex Hooks：`https://developers.openai.com/codex/hooks/`
- 飞书自定义机器人签名示例：`https://open.feishu.cn/community/articles/7271149634339422210`
