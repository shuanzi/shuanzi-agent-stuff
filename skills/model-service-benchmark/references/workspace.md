# 本地执行工具与能力差距

在个人测试工作区使用工具时阅读。以下为 2026-09-23 对实际 checkout 的核对，不证明任何真实设备通过规范。使用前检查当前源码和帮助是否变化，不能把本页当新能力已经实现。

## 分工与当前能力

本技能不附带测试客户端。若使用已有 `llm_benchmark_workspace`，先从当前项目上下文定位其实际 checkout；具体字段／状态读该 checkout 的 `docs/contracts.md`，具体执行读 `.agents/skills/llm-benchmark/SKILL.md`，远程执行前读 `REMOTE_OPERATIONS.md`。这些路径均相对测试工作区根目录，不相对本技能目录。**规范符合性按本技能 revision 85 判定**；工具契约不覆盖或改写规范门槛。其他环境使用自己的工具与契约，先核对所需能力。

| 规范能力 | 当前 checkout 证据 | 使用限制 |
|---|---|---|
| 目标／方案冻结、预检、闭环扫描、逐请求与监控证据 | `llm_bench/config.py`、`runner.py`、`client.py`、`observe.py` | 可用于相应摸底与证据采集；仍须实际服务适配验证 |
| 规范矩阵 | profile 展开 workloads×concurrencies 笛卡尔积 | 不自动表达必测／补充／可选或目标等级上限；在本轮计划单独列明范围和缺口 |
| 普通三轮扫描、边界采样 | 默认 `formal_min_requests=30`，没有轮次或最短正式发压时长字段 | 改成 200／1000 也不自动得到独立三轮或每轮≥5 min；只能在被验证的外部编排下逐轮留证，否则未完成该验收 |
| Stage C／E | profile 无有限请求率、到达模式、混合配比、连续分组长测接口 | 现有 run 不能宣称完成 C/E；使用已核验有能力的工具，或交付缺口，不编造 CLI 参数／JSON 字段 |
| 完整核心门槛 | limits 只接收 TTFT／TPOT 分位数及成功率；report 的 Queue 分位数、OOM 计数留空 | 阈值检查不等于完整 PASS；需要可对齐的服务端核心证据和规范判定，不能把 waiting 数量或主机 oom 增量直接当 Queue P95／服务 OOM 完整证据 |
| 规范计时 | client 的 event_times、ttft_s、e2e_s 相对 `start_monotonic`；另存 send／first／last output | start 包含连接／序列化。按 [metrics](metrics.md) 核验字段并派生发送边界口径，保留旧值；缺边界不认证符合规范 |
| 接口成功与长度有效 | client 的 success 同时受长度和协议检查影响 | 不能无说明用作规范接口成功率；必要时从原始证据分别派生，缺证据标不可独立复核 |
| 历史预设 | `examples/profile-feishu-v2.json` 引用 revision 83，18 点、单轮至少 30 正式请求、7200 s 上限 | 是摸底预设，不是 revision 85 完整验收配置；不默认更新源码或已有历史结果 |

当前 limits 与 profile 会拒绝未知字段，省略字段会补默认值。先查看规范化后的完整配置，不只看覆盖项；自定义负载不可继续冒称原规范。通用能力不足不授权自动开发客户端或重启服务；说明可执行范围与需要的适配。

环境已安装 `inference-service-benchmark` 时，可按其入口处理续测；它是可选能力，不随本技能附带。旧轮、历史预设及续测报告不能替代规范采样。入口缺失时在用户指定项目查找当前工具，不自动安装依赖或复制历史工程。

## 现有命令的适用范围

在**实际负载客户端所在主机**的仓库根目录执行 `python3 -m llm_bench`。以下是已支持命令的形状，只执行当前请求授权的阶段；示例路径不是实际服务或已存在文件。

从 `examples/target-llama.json` 或 `examples/target-vllm.json` 派生本轮 target，核对 backend／base_url／model／auth_env／monitoring／expected／locations。linux 监控需真实服务 PID，不拿控制端 `/proc` 冒充远端资源。llama 请求字段和缓存控制不直接移植给 vLLM。

```bash
python3 -m llm_bench --help
python3 -m llm_bench preflight --target target.json --output preflight.json
```

preflight 不发送生成或 tokenize。`ready=true` 不证明定长输出、缓存、规范采样或全部核心观测已通过。

```bash
python3 -m llm_bench run --target target.json --profile profile.json --output raw-results/new-run-id
python3 -m llm_bench status raw-results/new-run-id
```

目录必须尚不存在。`run` 对 completed 和 time_limited 均返回 0，须读 `status.json`；点位 completed 也可能含失败。不要把上述单次命令写成“完整规范验收”或“持续两小时长测”。

```bash
python3 -m llm_bench report raw-results/new-run-id
python3 -m llm_bench audit raw-results/new-run-id
```

report／audit 不连接服务。首次生成可在本轮目录；历史重算先复制证据到独立派生目录，对副本执行并保留原始工件。规范复算单列原指标与发送边界指标、接口成功与长度有效性、各轮和阶段结论，不能重写 samples／run／status／历史源码。audit 0=一致，1=错误，2=未结束或缺必要证据；均不等于规范 PASS。

## 产物映射

| 内容 | 当前文件 |
|---|---|
| 目标／方案／矩阵／执行源码 | `run.json`、`executed-source/` |
| 输入／摘要、逐请求及辅助请求 | `tokens.json`、`samples.jsonl`、`auxiliary.jsonl` |
| 前后观测、资源时序、终态 | `before.json`、`after.json`、`monitor.jsonl`、`status.json` |
| 派生汇总／报告／资源图／审计 | `summary.json`、`summary.csv`、`报告.md`、`resources.svg`、`audit.json` |

`final_drain=idle/busy/unverified` 不能由客户端退出改写。仅 HTTP 模式不证明服务独占，vLLM API 进程资源不自动包括 engine worker。源码实际执行版本与当前报告生成／审计版本分别记录。
