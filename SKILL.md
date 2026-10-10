---
name: mcd-profile
version: 1.2.0
display_name: "麦麦档案"
display_name_en: "McProfile"
description: "把你的麦当劳历史订单，变成一份『消费 × 省钱 × 健康 × 权益』多维复盘 + 麦门人格卡片；并可选完成一次真实点餐，点餐后生成一张千人千面、自带战报的炫酷分享档案。用于『我在麦当劳花了/省了多少、吃了多少热量 / 看看我的麦门人格 / 券和积分有没有浪费 / 帮我点一份』等场景。档案全程只读历史订单与权益数据；点餐为可选写操作，默认 dry-run、须显式确认。依赖 mcd-mcp MCP 服务，覆盖官方 20 个只读工具 +（可选）1 个下单工具。"
license: MIT
---

# 麦麦档案 (McProfile)

不做只会点餐的助手，而做**复盘**——把「已经吃过的每一单麦当劳」翻译成看得懂、晒得出的个人复盘；
并在此基础上，提供一条**默认安全（dry-run）**的**可选点餐闭环**，点完单立刻得到一张
**「本次战报 + 历史画像」合体**的炫酷分享档案。

所有数据均通过 **`mcd-mcp` MCP 服务** 获取（见 `mcp-config.example.json`）；
本 Skill 负责把历史订单、权益、商城、场景、营销数据，翻译成**六大画像 + 麦门人格 + 工具覆盖清单**。

## 何时触发

用户表达「回顾在麦当劳的花销/饮食/权益」，例如：

- 「看看我的麦麦档案」「我在麦当劳花了多少钱」
- 「帮我统计一下这月在麦当劳吃了多少热量」
- 「我在麦当劳省了多少钱」「我的券有没有浪费」
- 「我的麦门人格是什么」「生成一张麦当劳年度总结卡片」
- 「我最近的麦当劳活动有哪些」「我常去哪家店、常点什么」
- 「帮我点一份…（点餐闭环，需显式确认）」→ 走 `eat` 子命令

## 能力与工具映射（官方 20 只读工具 + 1 可选写）

> 设计原则：在**「只读复盘」**的边界内，尽量把官方工具**用满、用透**——
> 每个工具都有实际产出（见档案末尾的「工具覆盖清单」），不为凑数而凑数。
> 写操作**只保留 `create-order`**（点餐闭环），且**默认关闭、须显式确认**。

| 步骤 | 目的 | 调用的 MCP 工具 |
|---|---|---|
| 1. 取历史订单 | 订单、实付金额、门店、套餐成分 | `order-list` |
| 2. 补优惠明细 | 单笔券/优惠/餐方式/门店地址（算省钱率） | `query-order` ×N |
| 3. 取权益 | 积分、手持券、奖品、抽奖、可领券 | `query-my-account`、`query-my-coupons`、`query-my-prizes`、`query-lottery-info`、`available-coupons` |
| 4. 取商城 | 商城订单、订单详情、积分兑换力 | `mall-order-list`、`mall-order-detail` ×N、`mall-points-products` |
| 5. 取场景 | 门店、地址、菜单/常点、门店券、算价 | `query-nearby-stores`、`delivery-query-addresses`、`delivery-query-stores`、`query-meals`、`query-meal-detail`、`query-store-coupons`、`calculate-price` |
| 6. 取营销 | 活动日历、服务器时间 | `campaign-calendar`、`now-time-info` |
| 7. 取营养库 | 把订单商品名映射成热量/钠/蛋白 | `list-nutrition-foods` |
| 8. 生成档案 | 六大画像 + 人格 + 卡片 + 工具清单 | 本地分析（`src/analysis.py`、`src/persona.py`、`src/theme.py`、`src/report/`（base/markdown/html/png）） |
| 9. **（可选）点餐** | 选店→选餐→算价→（确认）下单→复核 | `query-nearby-stores`、`query-meals`、`query-meal-detail`、`calculate-price`、**`create-order`**、`query-order` |

**按域归类（共 21 个，含 1 个可选写）：**

| 域 | 工具 |
|---|---|
| 订单 | `order-list`、`query-order` |
| 权益 | `query-my-account`、`query-my-coupons`、`query-my-prizes`、`query-lottery-info`、`available-coupons` |
| 商城 | `mall-order-list`、`mall-order-detail`、`mall-points-products` |
| 场景 | `query-nearby-stores`、`delivery-query-addresses`、`delivery-query-stores`、`query-meals`、`query-meal-detail`、`query-store-coupons`、`calculate-price` |
| 营销 | `campaign-calendar`、`now-time-info` |
| 营养 | `list-nutrition-foods` |
| **点餐（写）** | **`create-order`**（默认关闭，`eat --yes` 才触发） |

### 点餐链路（唯一写操作，默认关闭）

```
query-nearby-stores / delivery-query-stores → query-meals（富菜单：图+价+名+常点）
  → query-meal-detail（按需补组成/单品图）
    → calculate-price（算价并取 takeWayList[].code）
      → 【安全护栏：默认 dry-run，须显式确认】
        → create-order（takeWayCode 取自上一跳）→ query-order（复核）
```

> **硬依赖**：到店场景 `create-order` 的 `takeWayCode` **必传**，且只能来自
> `calculate-price` 的 `takeWayList[].code` —— **下单前必须先算价**。
>
> **有图有价**：`query-meals` 顶层 `meals` 字典一次拿全 100+ 款商品的「图+价+名」，
> 生成分享卡时商品图**内嵌**进卡片（HTML 为 `data:` URI 自包含，PNG 用 matplotlib 嵌入）。

## 生成的六大画像

| 画像 | 内容 |
|---|---|
| 🎬 **本次点餐战报** | 点餐闭环产物：门店/时间/餐品（**带商品缩略图**）/实付/省下/本单热量（无点餐时不展示） |
| 🏅 **成就徽章墙** | 从数据里挑出的「可炫耀」成就，最多 9 枚（3×3） |
| 💬 **麦门金句** | 千人千面、可截图的传播文案 |
| 💰 **消费** | 累计消费、平均客单、最贵/最省一单、最爱门店、复购最多单品、时段分布 |
| 🎯 **省钱** | 累计原价 vs 实付、**累计省下多少钱、省钱率**、用券次数、最常用券、最划算一单 |
| 🩺 **健康** | 热量/蛋白/脂肪/碳水/钠累计、单餐红黄绿灯、≈几个巨无霸、与每日参考值差距 |
| 🧭 **习惯** | 官方标记的**「我的常点」**、最活跃时段、星期分布、单均件数、消费跨度 |
| 🎫 **权益** | 积分收支、手持券与临期券、门店可用券、麦麦省可领券、商城订单、抽奖活动、**积分兑换力** |
| 📅 **活动** | 官方活动日历中的**今日进行中 / 即将到来**活动 |
| 🎭 **麦门人格** | 按行为特征生成人格标签（如「优惠猎人 / 早餐仪式感大师 / 深夜加餐党」）+ 六维雷达 |

外加一份**MCP 工具覆盖清单**（本次调了哪些官方工具、各自产出多少条），让「用了多少 MCP 能力」看得见。

**千人千面**：人格 → 一整套深色潮酷配色 + Slogan（`src/theme.py`），
**同一份档案，不同的人打开是不同的那张海报**；分享产物为**竖版长图**（1080×自适应，朋友圈/小红书比例）。
> **称号亦可千人千面**：默认是规则人格标签（如「优惠猎人」），但**可由 WorkBuddy 命名**独一份的称号
> （如「满减操盘手」）；**配色仍锚定规则人格**，保证视觉不会错乱。

### 文案：WorkBuddy 在环（默认规则，可选模型）

档案的**视觉结构**是规则驱动的（配色 / 徽章触发 / 雷达打分），**文字**则分两层：

- **默认**：规则模板（`src/textpack.py` 的文本注册表 `TEXT_REGISTRY` +
  `theme.build_quips` / `report.build_advice`），零依赖、可复现；
- **在环**：由 **WorkBuddy（宿主 agent）** 写**除数值外的全部文字**（`src/textpack.py`）——
  `brief` 导出素材 → WorkBuddy 生成 `copy_pack.json` → `--copy` 注入渲染。**无需任何外部模型 Key。**

**覆写范围（除数值外的全部文字）**：

| 字段 | 覆盖内容 |
|---|---|
| `persona_label` / `headline` / `slogan` / `tags` / `quips` / `advice` / `cta` | 人格称号 / 标题句 / 标语 / 标签 / 金句 / 建议 / 号召语 |
| `badge_desc` | 徽章描述 |
| `labels` | **全部区块标题、指标名、KPI 名、表头、页脚、元信息行**（key 见 `brief.text_map`，**须保留 `{占位符}`**） |
| `radar` | 雷达维度名（原名 → 新名） |
| `badge_title` | 徽章名（原名 → 新名） |

> **数值永不出自模型**：金额 / 单量 / 热量 / 积分等一律由规则计算；`labels` 里的
> `{rate}`/`{n}`/`{theme}` 等占位符由程序填充，模型只改文字、必须原样保留。

## 工作流程

1. **采集**：调用上述 20 个只读工具（`src/sources.py`），归一化为领域模型；
   从订单推断最爱门店参数，供 `query-meals` / `query-store-coupons` / `calculate-price` 复用。
   任一工具失败不致命，记录告警并计入工具清单；全部失败则回退脱敏样例。
2. **补全优惠**：逐单调 `query-order` 取 `couponList / totalDiscountAmount / takeWay / storeAddress`，据此算省钱率。
3. **映射营养**：套餐按 `comboItemList` 拆件，逐项匹配 `list-nutrition-foods`；
   命中率以「覆盖率」如实披露。
4. **分析**：消费 / 省钱 / 健康 / 习惯 / 权益 / 活动 六大画像（`src/analysis.py`）。
5. **人格**：按 早餐/夜宵/肉食/甜品/咖啡/省钱 六维打分，生成人格标签与雷达（`src/persona.py`）。
6. **呈现**：输出 Markdown 档案 + MCP 工具覆盖清单，可选导出**可分享卡片**（暗黑潮酷 HTML / 竖版长图 PNG）（`src/report/`（base/markdown/html/png）、`src/theme.py`）。
7. **（可选）点餐闭环**（`src/ordering.py`）：选店 → 选餐（**富菜单：一次拿到 100+ 款的图+价+名**）
   → 算价 →（安全护栏）下单 → 复核；下单后把这一单组装成**战报**（`build_meal_report`）**并入档案**；
   商品图经 `src/images.py` 下载后**内嵌**进分享卡
   （HTML 转 `data:` URI 自包含，PNG 用 matplotlib 嵌入），缺图/断网自动降级为纯文字。
   生成合体分享长图。
   > **可视化点餐**（`src/menu_view.py` / `menu` 子命令）：终端与选择卡片渲染不了图片，
   > 故提供网页版菜单——把 100+ 款商品的图+价铺出来，支持类目筛选 / 搜索 / 点选购物车，
   > 一键复制**点餐话术**（如「我要点：麦辣鸡腿汉堡×2（门店，到店取餐）」），粘贴回对话即可点单；
   > 也可导出 `code:qty` 清单喂给 `eat --items ...`。
8. **（可选）文案在环**（`src/textpack.py`）：`brief` 导出素材（含全部文字默认值 + 输出 schema）
   → WorkBuddy 生成 `copy_pack.json`（可覆盖**除数值外的全部文字**：称号 / 区块标题 / 指标名 /
   雷达维度 / 徽章名 …）→ `--copy` 注入；不注入则回退规则模板。

## 命令行用法（可直接跑）

```bash
export MCD_MCP_TOKEN=<你的麦当劳 MCP Token>

# 生成麦麦档案（联网读取真实数据，调用 20 个官方只读工具）
python -m src.cli archive

# 导出分享卡片 + 档案
python -m src.cli archive --html card.html --png card.png --out profile.md

# 分维度查看
python -m src.cli orders      # 历史订单（含券/优惠）
python -m src.cli savings     # 省钱复盘
python -m src.cli account     # 积分与券
python -m src.cli campaign    # 近期活动
python -m src.cli store       # 门店与地址
python -m src.cli tools       # MCP 工具覆盖清单

# —— 点餐闭环（默认安全，只算价不下单）——
python -m src.cli stores                          # 查看可选门店
python -m src.cli menu --store 1990262            # 可视化点餐菜单（带图带价，点选导出 code:qty）
python -m src.cli eat --dry-run                   # 选店→选餐→算价 + 生成分享档案（不下单）
python -m src.cli eat --dry-run --items 麦辣鸡腿堡 圆筒冰淇淋:2   # 按名称点餐（自动换官方编码，歧义时列候选）
python -m src.cli eat --yes --items 9900016076:1 --share out.png   # 真实下单并出竖版长图

# 离线演示（无需 Token；已内嵌一张脱敏「本次战报」）
python -m src.cli demo

# —— 文案（WorkBuddy 在环）：导出素材 → 生成文案包 → 注入渲染 ——
python -m src.cli brief --out copy_brief.json          # 导出文案素材（交给 WorkBuddy）
#   （WorkBuddy 读取 copy_brief.json，产出 copy_pack.json）
python -m src.cli archive --copy copy_pack.json --html card.html --png card.png
```

## 安全准则

- **档案只读**：复盘部分仅调用查询类工具，**不发起**取消、抽奖、领券、改地址等任何写操作。
- **点餐是唯一写操作，且默认关闭**：不加 `--yes`（或交互未输入「下单」）时只做**算价预览**，
  **绝不调用 `create-order`**；下单前打印门店/餐品/实付明细，须显式确认。
- **真实下单会产生真实订单与费用**，请自行确认门店与餐品后再执行；下单成功保留 `orderId` 以便撤销。
- **隐私**：Token 用环境变量注入，不写入日志、不提交公开仓库；仓库内样例数据均已脱敏。
- **诚实口径**：`order-list` 仅返回最近约 10 单，文案以「最近 N 单」为准，不夸大。
- **免责声明**：档案结论仅供个人复盘，不构成医疗或营养建议。
