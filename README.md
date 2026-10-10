# 麦麦档案 · McProfile

> 一句「看看我的麦麦档案」，把你**已经吃过的每一单麦当劳**，变成一份能截图分享的
> **「消费 × 健康 × 权益」多维复盘报告 + 麦门人格卡片**。
>
> 还能**顺手下个单**，然后给你一张**千人千面、自带战报的炫酷分享档案**，让看到的人也想点。

麦当劳 MCP 创意开发大赛参赛作品。基于麦当劳官方 MCP Server（`mcd-mcp`），
把 MCP 里**几乎无人使用**的「订单后」能力（历史订单 / 积分 / 券 / 商城订单 / 活动日历）
充分盘活，变成普通用户看得懂、愿意晒的个人复盘——**一键调用官方 20 个只读工具**；
在此基础上，提供一条**默认安全（dry-run）**的**可选点餐闭环**（第 21 个工具 `create-order`，
仅在用户显式确认时才触发）。

---

## 1. 为什么做这个

翻遍目前已有的参赛作品，**几乎全部挤在「吃之前」**——点餐前选什么、点餐中怎么省。
而麦当劳 MCP 里整整一层「**吃之后**」的能力（订单跟踪 / 历史订单 / 售后 / 商城订单 / 权益）
却几乎无人使用。

**麦麦档案**就做这一层：不再帮你点餐，而是帮你**回顾**。它回答四个问题：

1. 我在麦当劳**花了多少、吃了多少、省了多少**？
2. 这些钱和热量，**花在了什么习惯上**？
3. 我手里那些**积分和券，还有多少没用**？
4. 我到底是哪一种**麦门人格**？

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
> 「麦麦档案」的本体是复盘；点餐闭环是**你主动发起**的附加动作，且带安全护栏——
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

`mcp-config.example.json` 已声明 `mcd-mcp` 服务（`https://mcp.mcd.cn`），
Token 通过环境变量注入，**不写死在仓库里**。

> 没有 Token 也能体验：`demo` 命令用随项目附带的**脱敏样例数据**离线生成完整档案。

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
│   ├── sources.py            # 五大域数据采集（20 个只读工具，含离线兜底）
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

## 9. 许可证

MIT。

> 免责声明：本项目为个人参赛作品，与麦当劳官方无隶属关系。
