# 境外费用标准：地区索引与查询规则

校订日期：2026-10-23。两份原 PDF 的 17 页已逐页核对，包含总表 **269 条**、2017 年住宿调整 **61 条**；另有 4 页外事流程通知已校订。下面索引覆盖原表的 188 个国家（地区）名称，保留原文名称与大洲编排。

## 从哪里查

| 查询内容 | 机器读取 | 人工阅读与回原件 |
|---|---|---|
| 住宿、伙食、公杂费总表，B001–B269 | [总表 CSV](data/境外费用标准总表.csv) | [逐页校订表](attachments/境外费用标准总表-OCR.md)；[原 PDF](../assets/境外费用标准总表.pdf) |
| 2017 年住宿费调整，U001–U061 | [调整表 CSV](data/境外住宿标准调整_2017.csv) | [通知全文与校订表](attachments/境外住宿标准调整_2017-OCR.md)；[原 PDF](../assets/境外住宿标准调整_2017.pdf) |
| 公杂费领取条件、其他执行条款 | 表格金额不能替代正文 | [2017 通知第 2 页](attachments/境外住宿标准调整_2017-OCR.md#pdf-page-2) |
| 公示、审批、备案、ARP 与核销流程 | 按事项读取，无费用金额表 | [外事通知查询入口](attachments/外事流程通知-OCR.md) |

文件名中的 `-OCR` 保留以兼容既有链接，内容已改为对照原图的校订稿。PDF 的物理页码从 1 起，可能与纸面印刷页码不同。总表第 10 页是空白预算审批表，不是费用标准行。

## Agent 查询步骤

1. 先按下方国家（地区）索引找到 B、U 记录，再读相应 CSV 行或点击记录 ID。每次保留国家、实际城市、费用项目、币种、金额、记录 ID 和 PDF 页码。
2. 在该国记录中核对具体城市、同一行中的城市组及备注。`其他城市` 与原城市单元格空白不同；不能将空白机械改为“其他城市”，也不能给所有城市套该国最高金额。
3. 总表列出住宿、伙食、公杂费。2017 附件只列住宿费金额，是部分地区的调整表；查住宿时须同时查看两表，按实际日期及匹配范围判断。通知原文生效日期为 **2018-01-01**，落款日期为 2017-11-13，印发日期为 2017-11-16。原文日期不等于本次已核验其为最新制度。
4. **逐项保留币种。** 不按国家现实通行币种推断，不把新住宿币种复制到总表伙食、公杂费，不把不同币种金额直接相加或自动换算。
5. 输出采用的原文值及来源；遇范围重组或原文冲突，列出具体候选行和待确认点。不要仅按国家名称连接两表，或生成一张未经范围判断的“最终合并标准表”。金额本身已校订，无需逐项重复 OCR；发生原文疑点或新旧范围冲突时回读相应 PDF 页。

在技能根目录可按关键词或稳定 ID 检索：

```sh
rg -n '日本|新潟|U002' references/data/境外住宿标准调整_2017.csv
rg -n '斯洛伐克|B187|U042' references/data
```

CSV 使用 UTF-8 BOM；程序读取使用 `encoding='utf-8-sig'`，金额按十进制处理。两表所有金额均为**所列原币种、每人每天**的限额，不是人民币，也不是每次出访总额。

## 字段与空值

| 字段 | 含义与使用方式 |
|---|---|
| `record_id` | 包内稳定 ID：B 为总表，U 为 2017 调整表；不可脱离前缀只用序号连接 |
| `source_row` | 原表序号；B 表 1–269，U 表 1–61 |
| `continent` | 原表分区，按源表继承；不是另行修正后的地理分类 |
| `country_region` | 展开原国别续行后的国家（地区）名称，每条都有值 |
| `city_scope` | 原城市栏，同格多城市保留为一条；原空白仍为空字符串 |
| `scope_kind` | `named_cities` 为有名称的城市/城市组；`other_cities` 为原文“其他城市”；`unspecified` 为原城市栏空白 |
| `lodging_currency`、`lodging` | 住宿费币种原文及金额 |
| `meal_currency`、`meal` | 伙食费币种及金额；U 表没有此标准列，均为空，不能当成 0 |
| `incidental_currency`、`incidental` | 公杂费币种及金额；U 表没有此标准列，均为空，不能当成 0 |
| `pdf_page` | 原 PDF 物理页码，从 1 开始；可用 PDF 链接的 `#page=N` 定位 |
| `printed_page` | 纸面印刷页码，去除页脚横线，仅保留数字 |
| `source_country_blank` | 原国别单元格是否为承接前行的逻辑续行；`true`/`false`，便于复核合并关系，不按文字垂直居中落点判断 |
| `remarks` | 原表备注；空白表示原件无备注，不代表已确认无适用条件 |

国家续行已展开，城市未向下填充。例如 B027 继承沙特阿拉伯，B127–B128 继承罗马尼亚，B162–B163 继承波兰；跨页不能重新猜国家。

## 币种与地区匹配的重点

| 情形 | 校订后的原文事实 | 使用边界 |
|---|---|---|
| 斯洛伐克 | B187：欧元，住宿 90、伙食 35、公杂 30；U042：住宿 120 美元 | 两份源表币种确有差异。不能把伙食 35、公杂 30 改为美元；具体报销组合需要财务确认时列明此差异 |
| 香港 | B060：港币，住宿 1500、伙食 500、公杂 300；U019：住宿 1900 港元 | 保留“港币”/“港元”各自原文写法；不能因文字不同漏掉对应关系，也不能据此臆造汇率变化 |
| 日本 | B006–B009 均为日元；U002 为新潟住宿 11000 日元，备注“新增标准” | 新潟有专属行，不能当成其他国家的美元金额，也不能把新增额用于日本所有城市 |
| 巴基斯坦 | B011 原城市组为伊斯兰堡、拉合尔、卡拉奇；U003 仅伊斯兰堡 270 美元；U004 其他城市 170 美元，备注明确“含拉合尔、卡拉奇、奎达” | 按备注拆分匹配；不能将 U003 的 270 套到旧 B011 整组 |
| 澳大利亚 | B251 原城市组为“堪培拉、帕斯、布里斯班”；U060 仅堪培拉 210 美元 | 210 不扩展到帕斯、布里斯班；“帕斯”是原表字样，不静默改名 |
| 菲律宾、墨西哥、伊拉克 | U014 宿务 180、U051 坎昆 160、U007 巴格达 320，均为美元且备注“新增标准”；伊拉克另有 U008 其他城市 290 | 新增行保留城市粒度，不能只按国家覆盖所有城市 |
| 美国 | B200–B208 原列九组城市；U047 为华盛顿、芝加哥 260，U048 纽约 270，U049 洛杉矶 250，U050 其他城市 200，均为美元 | 新表未在“其他城市”备注列明旧金山、休斯顿、波士顿、夏威夷。遇这些旧单列城市，给出旧专属行与 U050 候选，请财务确认覆盖解释；不擅自认定全部覆盖或全部保留 |
| 欧洲及其他地区 | 捷克、匈牙利、瑞典、丹麦、挪威、瑞士、冰岛等在原总表中列美元 | 以行内币种为准，不按现代货币体系改成欧元或当地货币 |

已定向复核非整十或易错数值：B071 卢旺达伙食 32、B085 津巴布韦公杂 33、B091 苏丹公杂 32、B096 吉布提伙食 60、B103 尼日尔公杂 35、B234 古巴公杂 37、B239 玻利维亚伙食 36、B243 海地公杂 43、B255 萨摩亚伙食 47。以上均为美元每人每天，不能为整齐而改成相邻常见值。

## 国家（地区）索引

按原总表顺序排列，记录 ID 可直达校订稿对应行。“该表未列”仅指 2017 附件未列该国，不代表该国无标准。原表名称按原样保留，例如孟加拉、斯威士兰、马其顿、法属留尼汪；必要的当代名称映射另行核实，不改写原始数据。

| 国家（地区） | 总表记录 ID（B） | 2017 住宿调整 ID（U） |
|---|---|---|
| 蒙古 | [B001](attachments/境外费用标准总表-OCR.md#b001) | 该表未列 |
| 朝鲜 | [B002](attachments/境外费用标准总表-OCR.md#b002) | [U001](attachments/境外住宿标准调整_2017-OCR.md#u001) |
| 韩国 | [B003](attachments/境外费用标准总表-OCR.md#b003)、[B004](attachments/境外费用标准总表-OCR.md#b004)、[B005](attachments/境外费用标准总表-OCR.md#b005) | 该表未列 |
| 日本 | [B006](attachments/境外费用标准总表-OCR.md#b006)、[B007](attachments/境外费用标准总表-OCR.md#b007)、[B008](attachments/境外费用标准总表-OCR.md#b008)、[B009](attachments/境外费用标准总表-OCR.md#b009) | [U002](attachments/境外住宿标准调整_2017-OCR.md#u002) |
| 缅甸 | [B010](attachments/境外费用标准总表-OCR.md#b010) | 该表未列 |
| 巴基斯坦 | [B011](attachments/境外费用标准总表-OCR.md#b011)、[B012](attachments/境外费用标准总表-OCR.md#b012)、[B013](attachments/境外费用标准总表-OCR.md#b013) | [U003](attachments/境外住宿标准调整_2017-OCR.md#u003)、[U004](attachments/境外住宿标准调整_2017-OCR.md#u004) |
| 斯里兰卡 | [B014](attachments/境外费用标准总表-OCR.md#b014) | [U005](attachments/境外住宿标准调整_2017-OCR.md#u005) |
| 马尔代夫 | [B015](attachments/境外费用标准总表-OCR.md#b015) | [U006](attachments/境外住宿标准调整_2017-OCR.md#u006) |
| 孟加拉 | [B016](attachments/境外费用标准总表-OCR.md#b016) | 该表未列 |
| 伊拉克 | [B017](attachments/境外费用标准总表-OCR.md#b017) | [U007](attachments/境外住宿标准调整_2017-OCR.md#u007)、[U008](attachments/境外住宿标准调整_2017-OCR.md#u008) |
| 阿拉伯联合酋长国 | [B018](attachments/境外费用标准总表-OCR.md#b018) | 该表未列 |
| 也门 | [B019](attachments/境外费用标准总表-OCR.md#b019)、[B020](attachments/境外费用标准总表-OCR.md#b020)、[B021](attachments/境外费用标准总表-OCR.md#b021) | 该表未列 |
| 阿曼 | [B022](attachments/境外费用标准总表-OCR.md#b022) | [U009](attachments/境外住宿标准调整_2017-OCR.md#u009) |
| 伊朗 | [B023](attachments/境外费用标准总表-OCR.md#b023) | [U010](attachments/境外住宿标准调整_2017-OCR.md#u010) |
| 科威特 | [B024](attachments/境外费用标准总表-OCR.md#b024) | 该表未列 |
| 沙特阿拉伯 | [B025](attachments/境外费用标准总表-OCR.md#b025)、[B026](attachments/境外费用标准总表-OCR.md#b026)、[B027](attachments/境外费用标准总表-OCR.md#b027) | 该表未列 |
| 巴林 | [B028](attachments/境外费用标准总表-OCR.md#b028) | [U011](attachments/境外住宿标准调整_2017-OCR.md#u011) |
| 以色列 | [B029](attachments/境外费用标准总表-OCR.md#b029) | [U012](attachments/境外住宿标准调整_2017-OCR.md#u012) |
| 巴勒斯坦 | [B030](attachments/境外费用标准总表-OCR.md#b030) | 该表未列 |
| 文莱 | [B031](attachments/境外费用标准总表-OCR.md#b031) | 该表未列 |
| 印度 | [B032](attachments/境外费用标准总表-OCR.md#b032)、[B033](attachments/境外费用标准总表-OCR.md#b033)、[B034](attachments/境外费用标准总表-OCR.md#b034) | 该表未列 |
| 不丹 | [B035](attachments/境外费用标准总表-OCR.md#b035) | 该表未列 |
| 越南 | [B036](attachments/境外费用标准总表-OCR.md#b036)、[B037](attachments/境外费用标准总表-OCR.md#b037)、[B038](attachments/境外费用标准总表-OCR.md#b038) | 该表未列 |
| 柬埔寨 | [B039](attachments/境外费用标准总表-OCR.md#b039) | 该表未列 |
| 老挝 | [B040](attachments/境外费用标准总表-OCR.md#b040) | [U013](attachments/境外住宿标准调整_2017-OCR.md#u013) |
| 马来西亚 | [B041](attachments/境外费用标准总表-OCR.md#b041) | 该表未列 |
| 菲律宾 | [B042](attachments/境外费用标准总表-OCR.md#b042) | [U014](attachments/境外住宿标准调整_2017-OCR.md#u014) |
| 印度尼西亚 | [B043](attachments/境外费用标准总表-OCR.md#b043) | 该表未列 |
| 东帝汶 | [B044](attachments/境外费用标准总表-OCR.md#b044) | 该表未列 |
| 泰国 | [B045](attachments/境外费用标准总表-OCR.md#b045)、[B046](attachments/境外费用标准总表-OCR.md#b046)、[B047](attachments/境外费用标准总表-OCR.md#b047)、[B048](attachments/境外费用标准总表-OCR.md#b048) | 该表未列 |
| 新加坡 | [B049](attachments/境外费用标准总表-OCR.md#b049) | 该表未列 |
| 阿富汗 | [B050](attachments/境外费用标准总表-OCR.md#b050) | [U015](attachments/境外住宿标准调整_2017-OCR.md#u015) |
| 尼泊尔 | [B051](attachments/境外费用标准总表-OCR.md#b051) | 该表未列 |
| 黎巴嫩 | [B052](attachments/境外费用标准总表-OCR.md#b052) | [U016](attachments/境外住宿标准调整_2017-OCR.md#u016) |
| 塞浦路斯 | [B053](attachments/境外费用标准总表-OCR.md#b053) | 该表未列 |
| 约旦 | [B054](attachments/境外费用标准总表-OCR.md#b054) | [U017](attachments/境外住宿标准调整_2017-OCR.md#u017) |
| 土耳其 | [B055](attachments/境外费用标准总表-OCR.md#b055)、[B056](attachments/境外费用标准总表-OCR.md#b056)、[B057](attachments/境外费用标准总表-OCR.md#b057) | 该表未列 |
| 叙利亚 | [B058](attachments/境外费用标准总表-OCR.md#b058) | [U018](attachments/境外住宿标准调整_2017-OCR.md#u018) |
| 卡塔尔 | [B059](attachments/境外费用标准总表-OCR.md#b059) | 该表未列 |
| 香港 | [B060](attachments/境外费用标准总表-OCR.md#b060) | [U019](attachments/境外住宿标准调整_2017-OCR.md#u019) |
| 澳门 | [B061](attachments/境外费用标准总表-OCR.md#b061) | 该表未列 |
| 台湾 | [B062](attachments/境外费用标准总表-OCR.md#b062) | 该表未列 |
| 马达加斯加 | [B063](attachments/境外费用标准总表-OCR.md#b063)、[B064](attachments/境外费用标准总表-OCR.md#b064)、[B065](attachments/境外费用标准总表-OCR.md#b065) | 该表未列 |
| 喀麦隆 | [B066](attachments/境外费用标准总表-OCR.md#b066) | 该表未列 |
| 多哥 | [B067](attachments/境外费用标准总表-OCR.md#b067) | 该表未列 |
| 科特迪瓦 | [B068](attachments/境外费用标准总表-OCR.md#b068) | 该表未列 |
| 摩洛哥 | [B069](attachments/境外费用标准总表-OCR.md#b069) | 该表未列 |
| 阿尔及利亚 | [B070](attachments/境外费用标准总表-OCR.md#b070) | 该表未列 |
| 卢旺达 | [B071](attachments/境外费用标准总表-OCR.md#b071) | 该表未列 |
| 几内亚 | [B072](attachments/境外费用标准总表-OCR.md#b072) | 该表未列 |
| 埃塞俄比亚 | [B073](attachments/境外费用标准总表-OCR.md#b073) | 该表未列 |
| 厄立特里亚 | [B074](attachments/境外费用标准总表-OCR.md#b074) | 该表未列 |
| 莫桑比克 | [B075](attachments/境外费用标准总表-OCR.md#b075) | 该表未列 |
| 塞舌尔 | [B076](attachments/境外费用标准总表-OCR.md#b076) | 该表未列 |
| 肯尼亚 | [B077](attachments/境外费用标准总表-OCR.md#b077) | 该表未列 |
| 利比亚 | [B078](attachments/境外费用标准总表-OCR.md#b078) | 该表未列 |
| 安哥拉 | [B079](attachments/境外费用标准总表-OCR.md#b079) | 该表未列 |
| 赞比亚 | [B080](attachments/境外费用标准总表-OCR.md#b080) | 该表未列 |
| 几内亚比绍 | [B081](attachments/境外费用标准总表-OCR.md#b081) | [U020](attachments/境外住宿标准调整_2017-OCR.md#u020) |
| 突尼斯 | [B082](attachments/境外费用标准总表-OCR.md#b082) | 该表未列 |
| 布隆迪 | [B083](attachments/境外费用标准总表-OCR.md#b083) | [U021](attachments/境外住宿标准调整_2017-OCR.md#u021) |
| 莱索托 | [B084](attachments/境外费用标准总表-OCR.md#b084) | 该表未列 |
| 津巴布韦 | [B085](attachments/境外费用标准总表-OCR.md#b085) | 该表未列 |
| 尼日利亚 | [B086](attachments/境外费用标准总表-OCR.md#b086)、[B087](attachments/境外费用标准总表-OCR.md#b087)、[B088](attachments/境外费用标准总表-OCR.md#b088) | 该表未列 |
| 毛里求斯 | [B089](attachments/境外费用标准总表-OCR.md#b089) | 该表未列 |
| 索马里 | [B090](attachments/境外费用标准总表-OCR.md#b090) | [U022](attachments/境外住宿标准调整_2017-OCR.md#u022) |
| 苏丹 | [B091](attachments/境外费用标准总表-OCR.md#b091) | 该表未列 |
| 贝宁 | [B092](attachments/境外费用标准总表-OCR.md#b092) | 该表未列 |
| 马里 | [B093](attachments/境外费用标准总表-OCR.md#b093) | [U023](attachments/境外住宿标准调整_2017-OCR.md#u023) |
| 乌干达 | [B094](attachments/境外费用标准总表-OCR.md#b094) | 该表未列 |
| 塞拉利昂 | [B095](attachments/境外费用标准总表-OCR.md#b095) | 该表未列 |
| 吉布提 | [B096](attachments/境外费用标准总表-OCR.md#b096) | 该表未列 |
| 塞内加尔 | [B097](attachments/境外费用标准总表-OCR.md#b097) | 该表未列 |
| 冈比亚 | [B098](attachments/境外费用标准总表-OCR.md#b098) | 该表未列 |
| 加蓬 | [B099](attachments/境外费用标准总表-OCR.md#b099) | 该表未列 |
| 中非 | [B100](attachments/境外费用标准总表-OCR.md#b100) | [U024](attachments/境外住宿标准调整_2017-OCR.md#u024) |
| 布基纳法索 | [B101](attachments/境外费用标准总表-OCR.md#b101) | 该表未列 |
| 毛里塔尼亚 | [B102](attachments/境外费用标准总表-OCR.md#b102) | 该表未列 |
| 尼日尔 | [B103](attachments/境外费用标准总表-OCR.md#b103) | 该表未列 |
| 乍得 | [B104](attachments/境外费用标准总表-OCR.md#b104) | 该表未列 |
| 赤道几内亚 | [B105](attachments/境外费用标准总表-OCR.md#b105) | 该表未列 |
| 加纳 | [B106](attachments/境外费用标准总表-OCR.md#b106) | [U025](attachments/境外住宿标准调整_2017-OCR.md#u025) |
| 坦桑尼亚 | [B107](attachments/境外费用标准总表-OCR.md#b107)、[B108](attachments/境外费用标准总表-OCR.md#b108)、[B109](attachments/境外费用标准总表-OCR.md#b109) | 该表未列 |
| 刚果（金） | [B110](attachments/境外费用标准总表-OCR.md#b110) | 该表未列 |
| 刚果（布） | [B111](attachments/境外费用标准总表-OCR.md#b111) | 该表未列 |
| 埃及 | [B112](attachments/境外费用标准总表-OCR.md#b112) | 该表未列 |
| 圣多美和普林西比 | [B113](attachments/境外费用标准总表-OCR.md#b113) | 该表未列 |
| 博茨瓦纳 | [B114](attachments/境外费用标准总表-OCR.md#b114) | 该表未列 |
| 南非 | [B115](attachments/境外费用标准总表-OCR.md#b115)、[B116](attachments/境外费用标准总表-OCR.md#b116)、[B117](attachments/境外费用标准总表-OCR.md#b117)、[B118](attachments/境外费用标准总表-OCR.md#b118) | 该表未列 |
| 纳米比亚 | [B119](attachments/境外费用标准总表-OCR.md#b119) | 该表未列 |
| 斯威士兰 | [B120](attachments/境外费用标准总表-OCR.md#b120) | 该表未列 |
| 利比里亚 | [B121](attachments/境外费用标准总表-OCR.md#b121) | [U026](attachments/境外住宿标准调整_2017-OCR.md#u026) |
| 佛得角 | [B122](attachments/境外费用标准总表-OCR.md#b122) | 该表未列 |
| 科摩罗 | [B123](attachments/境外费用标准总表-OCR.md#b123) | 该表未列 |
| 南苏丹 | [B124](attachments/境外费用标准总表-OCR.md#b124) | [U027](attachments/境外住宿标准调整_2017-OCR.md#u027) |
| 马拉维 | [B125](attachments/境外费用标准总表-OCR.md#b125) | 该表未列 |
| 罗马尼亚 | [B126](attachments/境外费用标准总表-OCR.md#b126)、[B127](attachments/境外费用标准总表-OCR.md#b127)、[B128](attachments/境外费用标准总表-OCR.md#b128) | [U028](attachments/境外住宿标准调整_2017-OCR.md#u028) |
| 马其顿 | [B129](attachments/境外费用标准总表-OCR.md#b129) | 该表未列 |
| 斯洛文尼亚 | [B130](attachments/境外费用标准总表-OCR.md#b130) | [U029](attachments/境外住宿标准调整_2017-OCR.md#u029) |
| 波黑 | [B131](attachments/境外费用标准总表-OCR.md#b131) | 该表未列 |
| 克罗地亚 | [B132](attachments/境外费用标准总表-OCR.md#b132) | [U030](attachments/境外住宿标准调整_2017-OCR.md#u030) |
| 阿尔巴尼亚 | [B133](attachments/境外费用标准总表-OCR.md#b133) | 该表未列 |
| 保加利亚 | [B134](attachments/境外费用标准总表-OCR.md#b134) | 该表未列 |
| 俄罗斯 | [B135](attachments/境外费用标准总表-OCR.md#b135)、[B136](attachments/境外费用标准总表-OCR.md#b136)、[B137](attachments/境外费用标准总表-OCR.md#b137)、[B138](attachments/境外费用标准总表-OCR.md#b138)、[B139](attachments/境外费用标准总表-OCR.md#b139) | 该表未列 |
| 立陶宛 | [B140](attachments/境外费用标准总表-OCR.md#b140) | 该表未列 |
| 拉脱维亚 | [B141](attachments/境外费用标准总表-OCR.md#b141) | [U031](attachments/境外住宿标准调整_2017-OCR.md#u031) |
| 爱沙尼亚 | [B142](attachments/境外费用标准总表-OCR.md#b142) | [U032](attachments/境外住宿标准调整_2017-OCR.md#u032) |
| 乌克兰 | [B143](attachments/境外费用标准总表-OCR.md#b143)、[B144](attachments/境外费用标准总表-OCR.md#b144)、[B145](attachments/境外费用标准总表-OCR.md#b145) | [U033](attachments/境外住宿标准调整_2017-OCR.md#u033) |
| 阿塞拜疆 | [B146](attachments/境外费用标准总表-OCR.md#b146) | 该表未列 |
| 亚美尼亚 | [B147](attachments/境外费用标准总表-OCR.md#b147) | 该表未列 |
| 格鲁吉亚 | [B148](attachments/境外费用标准总表-OCR.md#b148) | 该表未列 |
| 吉尔吉斯斯坦 | [B149](attachments/境外费用标准总表-OCR.md#b149)、[B150](attachments/境外费用标准总表-OCR.md#b150) | 该表未列 |
| 塔吉克斯坦 | [B151](attachments/境外费用标准总表-OCR.md#b151) | 该表未列 |
| 土库曼斯坦 | [B152](attachments/境外费用标准总表-OCR.md#b152) | 该表未列 |
| 乌兹别克斯坦 | [B153](attachments/境外费用标准总表-OCR.md#b153)、[B154](attachments/境外费用标准总表-OCR.md#b154)、[B155](attachments/境外费用标准总表-OCR.md#b155) | 该表未列 |
| 白俄罗斯 | [B156](attachments/境外费用标准总表-OCR.md#b156) | 该表未列 |
| 哈萨克斯坦 | [B157](attachments/境外费用标准总表-OCR.md#b157)、[B158](attachments/境外费用标准总表-OCR.md#b158)、[B159](attachments/境外费用标准总表-OCR.md#b159) | [U034](attachments/境外住宿标准调整_2017-OCR.md#u034) |
| 摩尔多瓦 | [B160](attachments/境外费用标准总表-OCR.md#b160) | 该表未列 |
| 波兰 | [B161](attachments/境外费用标准总表-OCR.md#b161)、[B162](attachments/境外费用标准总表-OCR.md#b162)、[B163](attachments/境外费用标准总表-OCR.md#b163) | [U035](attachments/境外住宿标准调整_2017-OCR.md#u035) |
| 德国 | [B164](attachments/境外费用标准总表-OCR.md#b164)、[B165](attachments/境外费用标准总表-OCR.md#b165)、[B166](attachments/境外费用标准总表-OCR.md#b166)、[B167](attachments/境外费用标准总表-OCR.md#b167) | [U036](attachments/境外住宿标准调整_2017-OCR.md#u036) |
| 荷兰 | [B168](attachments/境外费用标准总表-OCR.md#b168)、[B169](attachments/境外费用标准总表-OCR.md#b169)、[B170](attachments/境外费用标准总表-OCR.md#b170) | 该表未列 |
| 意大利 | [B171](attachments/境外费用标准总表-OCR.md#b171)、[B172](attachments/境外费用标准总表-OCR.md#b172)、[B173](attachments/境外费用标准总表-OCR.md#b173)、[B174](attachments/境外费用标准总表-OCR.md#b174) | 该表未列 |
| 比利时 | [B175](attachments/境外费用标准总表-OCR.md#b175) | 该表未列 |
| 奥地利 | [B176](attachments/境外费用标准总表-OCR.md#b176) | 该表未列 |
| 希腊 | [B177](attachments/境外费用标准总表-OCR.md#b177) | [U037](attachments/境外住宿标准调整_2017-OCR.md#u037) |
| 法国 | [B178](attachments/境外费用标准总表-OCR.md#b178)、[B179](attachments/境外费用标准总表-OCR.md#b179)、[B180](attachments/境外费用标准总表-OCR.md#b180) | [U038](attachments/境外住宿标准调整_2017-OCR.md#u038)、[U039](attachments/境外住宿标准调整_2017-OCR.md#u039)、[U040](attachments/境外住宿标准调整_2017-OCR.md#u040) |
| 西班牙 | [B181](attachments/境外费用标准总表-OCR.md#b181) | 该表未列 |
| 卢森堡 | [B182](attachments/境外费用标准总表-OCR.md#b182) | 该表未列 |
| 爱尔兰 | [B183](attachments/境外费用标准总表-OCR.md#b183) | [U041](attachments/境外住宿标准调整_2017-OCR.md#u041) |
| 葡萄牙 | [B184](attachments/境外费用标准总表-OCR.md#b184) | 该表未列 |
| 芬兰 | [B185](attachments/境外费用标准总表-OCR.md#b185) | 该表未列 |
| 捷克 | [B186](attachments/境外费用标准总表-OCR.md#b186) | 该表未列 |
| 斯洛伐克 | [B187](attachments/境外费用标准总表-OCR.md#b187) | [U042](attachments/境外住宿标准调整_2017-OCR.md#u042) |
| 匈牙利 | [B188](attachments/境外费用标准总表-OCR.md#b188) | 该表未列 |
| 瑞典 | [B189](attachments/境外费用标准总表-OCR.md#b189) | 该表未列 |
| 丹麦 | [B190](attachments/境外费用标准总表-OCR.md#b190) | 该表未列 |
| 挪威 | [B191](attachments/境外费用标准总表-OCR.md#b191) | 该表未列 |
| 瑞士 | [B192](attachments/境外费用标准总表-OCR.md#b192) | [U043](attachments/境外住宿标准调整_2017-OCR.md#u043) |
| 冰岛 | [B193](attachments/境外费用标准总表-OCR.md#b193) | [U044](attachments/境外住宿标准调整_2017-OCR.md#u044) |
| 马耳他 | [B194](attachments/境外费用标准总表-OCR.md#b194) | [U045](attachments/境外住宿标准调整_2017-OCR.md#u045) |
| 塞尔维亚 | [B195](attachments/境外费用标准总表-OCR.md#b195) | 该表未列 |
| 黑山 | [B196](attachments/境外费用标准总表-OCR.md#b196) | 该表未列 |
| 英国 | [B197](attachments/境外费用标准总表-OCR.md#b197)、[B198](attachments/境外费用标准总表-OCR.md#b198)、[B199](attachments/境外费用标准总表-OCR.md#b199) | [U046](attachments/境外住宿标准调整_2017-OCR.md#u046) |
| 美国 | [B200](attachments/境外费用标准总表-OCR.md#b200)、[B201](attachments/境外费用标准总表-OCR.md#b201)、[B202](attachments/境外费用标准总表-OCR.md#b202)、[B203](attachments/境外费用标准总表-OCR.md#b203)、[B204](attachments/境外费用标准总表-OCR.md#b204)、[B205](attachments/境外费用标准总表-OCR.md#b205)、[B206](attachments/境外费用标准总表-OCR.md#b206)、[B207](attachments/境外费用标准总表-OCR.md#b207)、[B208](attachments/境外费用标准总表-OCR.md#b208) | [U047](attachments/境外住宿标准调整_2017-OCR.md#u047)、[U048](attachments/境外住宿标准调整_2017-OCR.md#u048)、[U049](attachments/境外住宿标准调整_2017-OCR.md#u049)、[U050](attachments/境外住宿标准调整_2017-OCR.md#u050) |
| 加拿大 | [B209](attachments/境外费用标准总表-OCR.md#b209)、[B210](attachments/境外费用标准总表-OCR.md#b210)、[B211](attachments/境外费用标准总表-OCR.md#b211) | 该表未列 |
| 墨西哥 | [B212](attachments/境外费用标准总表-OCR.md#b212)、[B213](attachments/境外费用标准总表-OCR.md#b213)、[B214](attachments/境外费用标准总表-OCR.md#b214) | [U051](attachments/境外住宿标准调整_2017-OCR.md#u051) |
| 巴西 | [B215](attachments/境外费用标准总表-OCR.md#b215)、[B216](attachments/境外费用标准总表-OCR.md#b216)、[B217](attachments/境外费用标准总表-OCR.md#b217)、[B218](attachments/境外费用标准总表-OCR.md#b218) | 该表未列 |
| 牙买加 | [B219](attachments/境外费用标准总表-OCR.md#b219) | 该表未列 |
| 特立尼达和多巴哥 | [B220](attachments/境外费用标准总表-OCR.md#b220) | 该表未列 |
| 厄瓜多尔 | [B221](attachments/境外费用标准总表-OCR.md#b221) | [U052](attachments/境外住宿标准调整_2017-OCR.md#u052) |
| 阿根廷 | [B222](attachments/境外费用标准总表-OCR.md#b222) | [U053](attachments/境外住宿标准调整_2017-OCR.md#u053) |
| 乌拉圭 | [B223](attachments/境外费用标准总表-OCR.md#b223) | 该表未列 |
| 智利 | [B224](attachments/境外费用标准总表-OCR.md#b224)、[B225](attachments/境外费用标准总表-OCR.md#b225)、[B226](attachments/境外费用标准总表-OCR.md#b226)、[B227](attachments/境外费用标准总表-OCR.md#b227) | [U054](attachments/境外住宿标准调整_2017-OCR.md#u054) |
| 哥伦比亚 | [B228](attachments/境外费用标准总表-OCR.md#b228)、[B229](attachments/境外费用标准总表-OCR.md#b229)、[B230](attachments/境外费用标准总表-OCR.md#b230)、[B231](attachments/境外费用标准总表-OCR.md#b231) | 该表未列 |
| 巴巴多斯 | [B232](attachments/境外费用标准总表-OCR.md#b232) | 该表未列 |
| 圭亚那 | [B233](attachments/境外费用标准总表-OCR.md#b233) | 该表未列 |
| 古巴 | [B234](attachments/境外费用标准总表-OCR.md#b234) | [U055](attachments/境外住宿标准调整_2017-OCR.md#u055) |
| 巴拿马 | [B235](attachments/境外费用标准总表-OCR.md#b235) | 该表未列 |
| 格林纳达 | [B236](attachments/境外费用标准总表-OCR.md#b236) | [U056](attachments/境外住宿标准调整_2017-OCR.md#u056) |
| 安提瓜和巴布达 | [B237](attachments/境外费用标准总表-OCR.md#b237) | [U057](attachments/境外住宿标准调整_2017-OCR.md#u057) |
| 秘鲁 | [B238](attachments/境外费用标准总表-OCR.md#b238) | 该表未列 |
| 玻利维亚 | [B239](attachments/境外费用标准总表-OCR.md#b239) | 该表未列 |
| 尼加拉瓜 | [B240](attachments/境外费用标准总表-OCR.md#b240) | 该表未列 |
| 苏里南 | [B241](attachments/境外费用标准总表-OCR.md#b241) | [U058](attachments/境外住宿标准调整_2017-OCR.md#u058) |
| 委内瑞拉 | [B242](attachments/境外费用标准总表-OCR.md#b242) | 该表未列 |
| 海地 | [B243](attachments/境外费用标准总表-OCR.md#b243) | 该表未列 |
| 波多黎各 | [B244](attachments/境外费用标准总表-OCR.md#b244) | 该表未列 |
| 多米尼加 | [B245](attachments/境外费用标准总表-OCR.md#b245) | 该表未列 |
| 多米尼克 | [B246](attachments/境外费用标准总表-OCR.md#b246) | [U059](attachments/境外住宿标准调整_2017-OCR.md#u059) |
| 巴哈马 | [B247](attachments/境外费用标准总表-OCR.md#b247) | 该表未列 |
| 圣卢西亚 | [B248](attachments/境外费用标准总表-OCR.md#b248) | 该表未列 |
| 阿鲁巴岛 | [B249](attachments/境外费用标准总表-OCR.md#b249) | 该表未列 |
| 哥斯达黎加 | [B250](attachments/境外费用标准总表-OCR.md#b250) | 该表未列 |
| 澳大利亚 | [B251](attachments/境外费用标准总表-OCR.md#b251)、[B252](attachments/境外费用标准总表-OCR.md#b252)、[B253](attachments/境外费用标准总表-OCR.md#b253) | [U060](attachments/境外住宿标准调整_2017-OCR.md#u060) |
| 新西兰 | [B254](attachments/境外费用标准总表-OCR.md#b254) | 该表未列 |
| 萨摩亚 | [B255](attachments/境外费用标准总表-OCR.md#b255) | 该表未列 |
| 斐济 | [B256](attachments/境外费用标准总表-OCR.md#b256)、[B257](attachments/境外费用标准总表-OCR.md#b257)、[B258](attachments/境外费用标准总表-OCR.md#b258) | 该表未列 |
| 巴布亚新几内亚 | [B259](attachments/境外费用标准总表-OCR.md#b259) | 该表未列 |
| 密克罗尼西亚 | [B260](attachments/境外费用标准总表-OCR.md#b260) | 该表未列 |
| 马绍尔群岛 | [B261](attachments/境外费用标准总表-OCR.md#b261) | 该表未列 |
| 瓦努阿图 | [B262](attachments/境外费用标准总表-OCR.md#b262) | [U061](attachments/境外住宿标准调整_2017-OCR.md#u061) |
| 基里巴斯 | [B263](attachments/境外费用标准总表-OCR.md#b263) | 该表未列 |
| 汤加 | [B264](attachments/境外费用标准总表-OCR.md#b264) | 该表未列 |
| 帕劳 | [B265](attachments/境外费用标准总表-OCR.md#b265) | 该表未列 |
| 库克群岛 | [B266](attachments/境外费用标准总表-OCR.md#b266) | 该表未列 |
| 所罗门群岛 | [B267](attachments/境外费用标准总表-OCR.md#b267) | 该表未列 |
| 法属留尼汪 | [B268](attachments/境外费用标准总表-OCR.md#b268) | 该表未列 |
| 法属波利尼西亚 | [B269](attachments/境外费用标准总表-OCR.md#b269) | 该表未列 |
