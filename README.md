# 麦麦档案 · McProfile

> **先替你算出最划算的那一单，再帮你复盘吃过的每一单。**
>
> 一句 `solve --items 板烧鸡腿堡`，它穷举上千种组合、逐一让官方 `calculate-price` **验真实价**，
> 给出**带 S/A/B/C 评级的最优解 + 战报长图**——全程只读，**不产生任何订单、不花一分钱**。
>
> 吃完了再一句 `archive`，把每一单变成「消费 × 健康 × 权益」海报 + 麦门人格卡；
> 想再吃一单还能走完一条**默认 dry-run** 的点餐闭环。
>
> 还有一句 `preheat`：距下一场活动还有几天，**你的券等得到那天吗**。

麦当劳 MCP 创意开发大赛参赛作品。基于麦当劳官方 MCP Server（`mcd-mcp`），
**一键调用官方 20 个只读工具**；并额外保留唯一一个写操作 `create-order`
作为**可选点餐闭环**（默认关闭、须显式确认）。

⭐ **觉得有意思？给个 Star 就是最大的支持 → [github.com/dengbin21/mcd-profile](https://github.com/dengbin21/mcd-profile)**

🚀 **不想装环境？直接在线玩 → [mcsolve.app.workbuddy.host](https://mcsolve.app.workbuddy.host/)**
（免登录、免 Token：页面里就能跑求解器和活动倒计时，用的是脱敏样例数据）

## 招牌玩法 · 麦麦最优解（McSolve）

> **说一句你想吃什么，它替你把「这一单怎么点最划算」算出来——
> 花 0 元，穷举上千种组合，逐一让官方接口验价。全程只读，不产生任何订单。**

全场都把 `calculate-price` 当「下单前的最后一步」：调一次，看看多少钱，然后下单，用完即弃。

但它其实是**免费、只读、不产生订单、可以无限次调用**的接口——
换句话说：**不花一分钱，你就能知道任意商品组合的真实实付价。**

McSolve 把它当**模拟器**反复调用：

```
query-nearby-stores   你的门店
query-meals           全菜单 100+ 款（带图带价）
query-my-coupons      你手里的券（含到期）
query-store-coupons   门店活动（三件6折 / 满30减5）
available-coupons     麦麦省可领券
        ↓  本地按券门槛剪枝、枚举候选组合
calculate-price × N   逐单官方验真实价      ★ 引擎在这里
list-nutrition-foods  最优解的营养
```

**调用量怎么控**：组合空间是天文数字，所以分两段——本地**免费**枚举几千种，
按券门槛与预算剪枝排序后，只对 **Top 30** 个候选调官方接口验真实价。
本地估算**只用于排序，最终价格一律以官方为准**，绝不拿估算当结果。
（`--top` 控制验价次数，`--workers` 让这 30 次并发跑，实测 6.2s → 1.7s。）

```bash
$ python -m src.cli solve --items 板烧鸡腿堡
```

真实跑出来是这样（脱敏样例数据）：

```
菜单 47 款 ｜ 券 8 张（可解析规则 6 条）
  [1/30]  验价 → 新的最优 ¥21.50
  [2/30]  验价 → ¥21.90            ← 触发「三件任选6折」，多 2 件只多 4 毛
  …
  [30/30] 验价完成

直觉点法   1 件   ¥21.50   均价 ¥21.50
算法最优解 3 件   ¥21.90   均价 ¥7.30
→ 多花 ¥0.4，多得 2 件，均价降 66%
```

**关键在第 2 次验价**：单点汉堡不触发折扣，凑够三件才吃到 6 折——
这个差价别人不会告诉你，但官方接口会。

产出是一张带 **S/A/B/C 评级**的战报长图（`examples/solve_report.html`），
含「**你的直觉点法 vs 算法最优解**」的对照，直接截图就能晒。

> 免登录可玩：打开 [site/index.html](site/index.html)，
> 纯前端、脱敏样例数据，选想吃的就能现场算出最优解。

## 钩子 · 麦麦预热台（McPreheat）

> **距「周末欢乐桶限时回归」还有 15 天——但你有 1 张券 10-12 就到期了。**
> **这张券等不到那天。**

`campaign-calendar` 在别人手里是个静态列表：把活动列出来，看完没有下文。
但它只要和**券的到期时间**交叉一次，就会长出一个真实的冲突：

| 数据来源 | 字段 |
|---|---|
| `campaign-calendar` | 未来活动的日期 |
| `query-my-coupons` | 每张券的 `availableTime`（到期时间） |
| `now-time-info` | 服务器当前时间（倒计时基准） |

**券到期日 < 活动开始日 → 这张券赶不上。** 这条不是文案，是算出来的。

它同时给了三样东西，这正是「钩子」的构成：

- **紧迫感**：倒计时（网页端实时到秒）
- **行动理由**：哪些券必须先用掉，否则白攒
- **可比较**：备战度 **S/A/B/C** 评分（券包撑不撑得住、积分够不够兑）

```bash
$ python -m src.cli preheat
```

```
距「秋日限定新品上新」还有 7 天，但你有 1 张券等不到那天
备战度 A（75/100）—— 大体就绪，还能补

⚠️ 等不到那天的券
  满30减5元券   2026.10.12 23:59   3 天后

✅ 能撑到活动当天
  免费香芋派（7 天后到期）⚠️ 压线
  免费中薯条（53 天后到期）
```

> 免登录可玩：[site/index.html](site/index.html) 上的倒计时**实时走秒**。

## 和同类作品比，三个不一样

| | 大多数麦当劳 Skill | McProfile |
|---|---|---|
| 场景 | 「吃之前」：选什么、怎么省 | **算出怎么买最划算** + 「吃之后」复盘 |
| 价格口径 | 按菜单价自己估算 | **官方 `calculate-price` 逐单验价** |
| 券的处理 | 列出来给你看 | **解析门槛，用凑单去触发它** |
| 写操作 | 代下单 / 领券 / 抽奖，或刻意回避 | 求解全程只读；`create-order` 默认 dry-run + 三道护栏 |
| 产出 | 一份推荐 / 一张表 | **带评级的最优解战报** + 合体长图 |
| MCP 覆盖 | 通常 3–8 个工具 | **20 个只读 + 1 个写**，每个都有实际产出并在档案末尾自证 |

### 四个入口是一条闭环，不是四个工具

大多数参赛作品是「算完、出张图、结束」。McProfile 把四个入口串成一条时间线：

```text
preheat  下一场活动还有几天 → 你的券赶不赶得上
   ↓
solve    这一单怎么点最划算 → 官方验价过的最优解
   ↓
eat      照着最优解下单（默认 dry-run）→ 出战报
   ↓
archive  复盘吃过的每一单
   ↓
         └── 回到 preheat：指向下一场活动
```

这条线上的**四个入口**（`preheat` / `solve` / `eat` / `archive`）跑完都会打印一条
**可直接复制的下一步命令**，不会把你停在半路。（离线演示模式下会说明原因，
不会给出拿演示数据去下单的命令。）其余子命令是单维度查询，不打扰你。

---

## 1. 为什么做这个

麦当劳 MCP 官方一共 35 个工具。翻一遍参赛作品会发现，**绝大多数挤在「吃之前」**——
点餐前选什么、点餐中怎么省；即便是做「复盘 / 人格 / 年度总结」的那一批，
也几乎都停在**只读**：算完、出张图，就结束了。

**McProfile 多做一步**：复盘之后还能**真的替你下一单**，并把这一单立刻变成
「本单战绩 + 历史画像」的合体海报。它回答四个问题（外加一个别人不回答的）：

1. 我在麦当劳**花了多少、吃了多少、省了多少**？
2. 这些钱和热量，**花在了什么习惯上**？
3. 我手里那些**积分和券，还有多少没用**？
4. 我到底是哪一种**麦门人格**？
5. 想再吃一单的话，**能不能顺手就点了、并立刻晒出去**？

## 2. 它长什么样

```bash
$ python -m src.cli archive
```

输出一份 Markdown 档案，核心是**六张画像 + 一张工具清单**：

| 画像 | 内容 |
|---|---|
| 🎬 **本次点餐战报** | 点餐闭环产物：门店/时间/餐品/实付/省下/热量（无点餐时不展示） |
| 🏅 **成就徽章墙** | 从数据里挑出的「可炫耀」成就，最多 9 枚（3×3） |
| 💬 **麦门金句** | 千人千面、可截图的传播文案 |
| 💰 **消费画像** | 累计消费、平均客单、最贵/最省的一单、最爱门店、复购最多单品、时段分布 |
| 🎯 **省钱画像** | 累计原价 vs 实付、**累计省下多少钱、省钱率**、用券次数、最常用券、最划算一单 |
| 🩺 **健康画像** | 热量/蛋白/脂肪/碳水/钠累计摄入、单餐红黄绿灯、≈几个巨无霸、与每日参考值差距 |
| 🧭 **习惯画像** | 官方标记的**「我的常点」**、最活跃时段、星期分布、单均件数、消费跨度 |
| 🎫 **权益画像** | 积分收支、手持券与临期券、门店可用券、麦麦省可领券、商城订单、抽奖活动、**积分兑换力** |
| 📅 **活动画像** | 官方活动日历中的**今日进行中 / 即将到来**活动 |
| 🎭 **麦门人格** | 按行为特征生成人格标签（如「优惠猎人 / 早餐仪式感大师 / 深夜加餐党」）+ 六维雷达 |

并额外给出**「下个月怎么吃更省 / 更健康」**的具体建议，以及一份**MCP 工具覆盖清单**
（本次到底调用了哪些官方工具、各自产出多少条，让「用了多少 MCP 能力」看得见）。

还能一键生成一张**可分享卡片**（`--html` / `--png`），**暗黑潮酷**配色、带人格雷达，
天生适合截图发群、发朋友圈。

### 2.1 招牌玩法：点餐 → 炫酷档案 → 分享

```bash
$ python -m src.cli eat --dry-run          # 先安全预览（只算价，不下单）
$ python -m src.cli eat --yes              # 确认后真实下单
```

点完单后，档案会变成一张**「本次战报 + 历史画像」合体**的分享长图：

- **🎬 本次点餐战报**：门店 / 时间 / 餐品（**每个餐品带商品缩略图**）/ 实付 / 省下 / 这一单热量；
- **🖼 有图有价**：`query-meals` 顶层 `meals` 一次拿全 **100+ 款商品的「图+价+名」**；
  分享卡里的图**内嵌**（HTML 转 `data:` URI **单文件自包含**、脱网可见；PNG 用 matplotlib 嵌入），
  缺图 / 断网自动降级为纯文字；
- **🏅 成就徽章墙**：从你的数据里挑出「值得炫耀」的战果（省钱 100+、≈N 个巨无霸、早八战士…）；
- **💬 麦门金句**：按数据生成的千人千面文案，天生适合截图；
- **🎨 千人千面主题**：按麦门人格套用**一整套深色潮酷配色 + Slogan**
  （优惠猎人=金、深夜加餐党=靛蓝、巨无霸原教旨=赤红、甜品收割机=粉紫…），
  **同一份档案，不同的人打开是不同的那张海报**；
- **📇 竖版长图**：1080×自适应高度（朋友圈 / 小红书比例）。

## 3. 依赖的麦当劳 MCP 能力（20 只读 + 1 可选写）

本 Skill 以 MCP 的**「订单后 + 权益 + 场景/营销」层**为主，**档案部分全部只用只读工具**；
额外的**点餐闭环**会用到唯一一个写操作 `create-order`，且**默认关闭、必须显式确认**：

| 域 | 工具 |
|---|---|
| 订单 | `order-list`（历史订单，**数据主体**）、`query-order`（单笔详情：券/优惠/餐方式） |
| 权益 | `query-my-account`、`query-my-coupons`、`query-my-prizes`、`query-lottery-info`、`available-coupons` |
| 商城 | `mall-order-list`、`mall-order-detail`、`mall-points-products` |
| 场景 | `query-nearby-stores`、`delivery-query-addresses`、`delivery-query-stores`、`query-meals`、`query-meal-detail`、`query-store-coupons`、`calculate-price` |
| 营销 | `campaign-calendar`、`now-time-info` |
| 营养 | `list-nutrition-foods`（160 款餐品营养库） |
| **点餐（可选写）** | `create-order` —— 仅在 `eat --yes`（或交互输入「下单」）时触发 |

> **刻意不用**：`cancel-order` / `mall-create-order` / `party-order-create` /
> `auto-bind-coupons` / `draw-lottery` / `delivery-create-address` 等**写操作**，以及
> `query-promotions`、`query-meal-assistance`（仅企业团餐场景）。
> 「McProfile」的本体是复盘；点餐闭环是**你主动发起**的附加动作，且带安全护栏——
> **默认 dry-run、下单前打印明细、必须 `--yes` 或二次确认**。
>
> 详细调用流程、字段与业务价值见 **[MCP_INTEGRATION.md](./MCP_INTEGRATION.md)**。

## 4. 安装

```bash
# 需要 Python 3.10+
pip install -r requirements.txt

# 配置麦当劳 MCP Token（来自 https://open.mcd.cn/mcp）
export MCD_MCP_TOKEN=<你的麦当劳 MCP Token>
```

Token 三种配法，命中即停，优先级从高到低：

| 方式 | 用法 | 说明 |
|---|---|---|
| ① 环境变量 | `export MCD_MCP_TOKEN=...` | 推荐；也可 `python -m src.cli --token <Token> ...` |
| ② 本地配置文件 | `cp mcp-config.example.json mcp-config.local.json` 后填值 | 已加进 `.gitignore`，不会误提交 |
| ③ 系统 MCP 配置 | 已配过 `mcd-mcp` 的话自动读取 | 依次扫 `~/.workbuddy/mcp.json`、`~/.codebuddy/.mcp.json`、`~/.cursor/mcp.json` |

⚠️ **不要把真实 Token 写进 `mcp-config.example.json`**——那是模板，会被提交到仓库。
另外它里面的 `Bearer ${MCD_MCP_TOKEN}` 是**本项目 CLI 自己**展开的占位符，
多数 MCP 客户端不支持 `${}` 展开，直接拷进客户端会拿到字面量从而 401，客户端里请填真值。

> 没有 Token 也能体验：`demo` 命令用随项目附带的**脱敏样例数据**离线生成完整档案，
> 或直接开在线版 https://mcsolve.app.workbuddy.host/ （免登录、免 Token）。

## 5. 使用示例

```bash
# 生成你的麦麦档案（联网读取真实数据，调用 20 个官方工具）
python -m src.cli archive

# 同时导出分享卡片（HTML + PNG）与 Markdown 档案
python -m src.cli archive --html card.html --png card.png --out profile.md

# 分维度查看
python -m src.cli orders      # 历史订单（含券/优惠）
python -m src.cli savings     # 省钱复盘
python -m src.cli account     # 积分与券
python -m src.cli campaign    # 近期活动
python -m src.cli store       # 门店与地址
python -m src.cli tools       # MCP 工具覆盖清单

# —— 点餐闭环（默认安全，只算价不下单）——
python -m src.cli stores                      # 先看可选门店（收藏/位置/外送）
python -m src.cli menu --store 1990262        # 可视化点餐菜单：带图带价，点选一键复制点餐话术（也可导出 code:qty）
python -m src.cli eat --dry-run               # 选店→选餐→算价（不下单）+ 生成分享档案
python -m src.cli eat --dry-run --items 麦辣鸡腿堡 圆筒冰淇淋:2   # 按名称点餐：自动换官方编码，歧义时列候选
python -m src.cli eat --yes --items 9900016076:1 --share out.png   # 真实下单并出竖版长图

# 离线演示（无需 Token，样例数据；已内嵌一张脱敏「本次战报」）
python -m src.cli demo

# —— 文案（WorkBuddy 在环，无需任何外部模型 Key）——
python -m src.cli brief --out copy_brief.json   # 导出素材+全部文字默认值+schema，交给 WorkBuddy
python -m src.cli archive --copy copy_pack.json --html card.html --png card.png  # 注入模型文案渲染
#   └─ copy_pack.json 可覆盖除数值外的全部文字：称号/区块标题/指标名/雷达维度/徽章名…
```

> ⚠️ **`eat` 的真实下单会产生真实订单与费用**。不加 `--yes`（或在交互里输入「下单」）
> 时，程序只做**算价预览**，绝不会调用 `create-order`。

**示例输出（节选，脱敏样例数据）：**

```markdown
## 🎯 你的麦门人格：**优惠猎人**
> 在你手里，没有一单是原价买的。

## 💰 消费画像  |  累计消费 **¥488.70**

## 🎯 省钱画像
| 累计原价 | 累计实付 | 累计省下 | 省钱率 |
|---|---|---|---|
| ¥590.70 | ¥488.70 | **¥102.00** | **17.3%** |

## 🧭 习惯画像
- **官方「我的常点」：** 人气经典随心配

## 🩺 健康画像
**≈ 28.2 个巨无霸的热量。** 平均每单 803 kcal。
```

完整示例见 [`examples/demo_profile.md`](./examples/demo_profile.md)、
分享卡片见 [`examples/profile_card.html`](./examples/profile_card.html) 与
[`examples/profile_card.png`](./examples/profile_card.png)。

## 6. 项目结构

```
mcd-profile/
├── README.md                 # 本文档
├── CONTEST_DECLARATION.md    # 参赛声明（官方原文，未改动）
├── MCP_INTEGRATION.md        # 麦当劳 MCP 集成说明
├── workbuddy.md              # WorkBuddy 开发对话上下文
├── SKILL.md                  # Agent Skill 定义
├── mcp-config.example.json   # mcd-mcp 服务声明（脱敏示例）
├── requirements.txt
├── src/
│   ├── mcp_client.py         # 极简 MCP Streamable HTTP 客户端（含调用日志）
│   ├── models.py             # 领域模型（订单/权益/商城/场景/营销/点餐）与解析
│   ├── sources.py            # 六域数据采集（20 个只读工具，含离线兜底）
│   ├── nutrition.py          # 营养库与订单→营养匹配
│   ├── analysis.py           # 消费/健康/权益/省钱/习惯/活动 六大分析
│   ├── persona.py            # 麦门人格引擎
│   ├── theme.py              # 千人千面主题（配色/徽章/金句）
│   ├── ordering.py           # 点餐链路（选店→富菜单→算价→护栏→下单→验证）
│   ├── order_text.py         # 点餐话术解析（纯函数：清单/话术→编码，歧义拒绝瞎猜）
│   ├── menu_view.py          # 可视化点餐菜单 HTML（带图带价 + 点选导出点餐话术 / code:qty）
│   ├── images.py             # 商品图工具（下载缓存 / 转 data-uri / 读为数组，全程降级）
│   ├── textpack.py           # 文案层（WorkBuddy 在环：brief→copy_pack→注入渲染）
│   ├── archive.py            # 采集→分析→人格 聚合（可并入本次战报）+ 工具覆盖清单
│   ├── report/               # 渲染包：base（共享）/ markdown / html / png 三渲染器
│   └── cli.py                # 命令行入口（archive/.../eat/stores/menu/brief，只做编排与展示）
├── data/
│   ├── nutrition_snapshot.json   # 160 条营养快照
│   ├── orders_sample.json        # 脱敏样例订单（含券/优惠）
│   ├── archive_sample.json       # 脱敏样例权益（积分/券/抽奖/兑换）
│   ├── scene_sample.json         # 脱敏样例场景（门店/地址/常点/算价）
│   ├── marketing_sample.json     # 脱敏样例活动
│   └── meal_report_sample.json   # 脱敏样例「本次点餐战报」（供 demo 展示合体档案）
└── examples/
    ├── demo_profile.md
    ├── profile_card.html
    ├── profile_card.png
    ├── copy_brief.json        # 文案素材样例（brief 产物，交给 WorkBuddy）
    ├── copy_pack.json         # 文案包样例（WorkBuddy 产物：称号/文案 + labels/radar/badge_title，供 --copy）
    ├── menu_img/              # 商品图本地缓存（下载后内嵌进卡片，可忽略）
    ├── menu_<store>.html      # 可视化点餐菜单（menu 产物：带图带价，点选导出下单清单）
    └── eat_report.html/.png   # 点餐战报分享档案（eat 产物，含商品缩略图，HTML 自包含 / 竖版长图）
```

## 7. 设计要点

- **工具覆盖最大化**：在「只读」前提下，覆盖官方 35 个工具中**合理可用的 20 个**，
  每个工具都有实际产出（见档案末尾的「工具覆盖清单」），不为凑数而凑数。
- **口径诚实**：`order-list` 实测只返回**最近约 10 单**（无分页参数），因此定位为
  「档案 / 体检」而非「年度账单」；文案统一用「最近 N 单」，不夸大。
- **营养可解释**：订单里的**套餐会被拆成 `comboItemList` 单品**再逐项映射营养，
  避免「按套餐名估热量」的误差；映射命中率（覆盖率）如实披露，未收录的新品不硬凑。
- **千人千面**：人格 → 一整套深色潮酷配色 + 徽章墙 + 金句，**同一份档案，人人不同**；
  目标是让看到的人**也想点一单**、也想晒一张。
- **文案在环（视觉稳、文字活）**：视觉结构走规则（可复现），**除数值外的全部文字**可交给
  **WorkBuddy** 生成——`brief` 导出素材 + 输出 schema → WorkBuddy 写 `copy_pack.json` → `--copy` 注入，
  覆盖**人格称号**/标题句/标语/标签/金句/建议/徽章描述/CTA，以及 `labels`（**全部区块标题、指标名、
  KPI 名、表头、页脚、元信息行**）、`radar`（雷达维度名）、`badge_title`（徽章名）；
  **无需任何外部模型 Key**，无注入时回退规则模板。
  > 数值（金额/单量/热量/积分…）**永不出自模型**，一律规则计算；`labels` 里的 `{占位符}` 由程序填充，
  > 模型只改文字、必须保留占位符。称号默认是规则人格（如「优惠猎人」），可让 WorkBuddy 按数据命名为
  > **独一份**（如「满减操盘手」）；**配色仍锚定规则人格**，只有文字变，视觉不会错乱。
  >
  > 模型写文案难免出错，所以 `--copy` 加载时**逐条校验并显式打印**，出错的条目**自动回退默认文案**：
  > ① 键名写错（如 `sv.hero_title`）→ 提示相近的正确键（否则这条改写静默失效，你以为生效了）；
  > ② 删掉 `{占位符}` → 数值会消失，必须回退；③ 夹带 `facts` 里没有的数字（疑似编造）→ 回退。
  > 评级词支持两种写法：一个字符串（所有评级同一句），或 `{"S":…,"A":…,"B":…,"C":…}` 按档位各写一句。
- **隐私优先**：仓库内所有样例数据均为**脱敏/示例**数据；Token 只走环境变量。
- **可分享**：人格 + 雷达 + 反差点（「你在麦当劳花了 ¥X、省了 ¥Y、吃进 ≈Z 个巨无霸」）
  + 竖版长图，天生适合传播，而大赛排名正按 Star 计。

## 8. 安全准则

- **档案部分只读取**订单、权益、门店、活动等数据，**不发起**取消、抽奖、领券或支付。
- **点餐闭环是唯一写操作**，且带**三道护栏**：
  1. **默认 dry-run**：不加 `--yes`（或交互未输入「下单」）绝不调用 `create-order`；
  2. **下单前打印**门店 / 餐品清单 / 原价 / 优惠 / 实付，要求二次确认；
  3. 下单成功后保留 `orderId`，并提示可在官方渠道撤销。
- **真实下单会产生真实订单与费用**，请自行确认门店与餐品后再执行。
- 展示的金额、积分、券信息以麦当劳官方 MCP 实时返回为准。
- 档案结论仅供个人复盘参考，**不构成医疗、营养或其他专业建议**。

## 9. 支持一下

如果这份「麦麦档案」让你想晒一张，**点个 Star 就是最大的支持**：

**⭐ [github.com/dengbin21/mcd-profile](https://github.com/dengbin21/mcd-profile)**

麦当劳 MCP 创意开发大赛按 GitHub Star 排名，你的一下点击就是我的一票。也欢迎把它转给同样爱麦的朋友。

## 10. 许可证

MIT。

> 免责声明：本项目为个人参赛作品，与麦当劳官方无隶属关系。
