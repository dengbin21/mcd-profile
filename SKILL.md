---
name: mcd-profile
version: 2.0.0
display_name: "麦麦档案"
display_name_en: "McProfile"
description: "围绕麦当劳官方 MCP 的一套「吃之前 → 吃之后」闭环：McSolve 先用官方 calculate-price 反复验价，算出这一单怎么点最划算（全程只读、不产生订单）；McPreheat 把活动日历和券到期日交叉，告诉你哪些券等不到活动那天；吃完再用 archive 把每一单变成『消费 × 省钱 × 健康 × 权益』复盘 + 麦门人格卡。用于『这单怎么点最划算 / 我的券什么时候到期、赶得上活动吗 / 我在麦当劳花了/省了多少、吃了多少热量 / 我的麦门人格 / 帮我点一份』等场景。依赖 mcd-mcp MCP 服务，覆盖官方 20 个只读工具 +（可选、默认关闭）1 个下单工具。"
license: MIT
---

# 麦麦档案 (McProfile)

不做只会点餐的助手，而做**一条从「吃之前」到「吃之后」的闭环**：

- **吃之前 · McSolve（招牌）**：说一句你想吃什么，它穷举上千种组合、逐一让官方 `calculate-price`
  **验真实价**，给出带 S/A/B/C 评级的**最优解 + 战报长图**——**全程只读，不产生任何订单**；
- **吃之前 · McPreheat**：距下一场活动还有几天，**你的券等得到那天吗**；
- **吃之后 · archive**：把每一单翻译成看得懂、晒得出的**六维复盘 + 麦门人格卡**；
- **（可选）点餐闭环**：默认 dry-run，须显式确认才会真正下单。

所有数据均通过 **`mcd-mcp` MCP 服务** 获取（见 `mcp-config.example.json`）。
除数值外的**全部展示文字**可由 **WorkBuddy（宿主 agent）** 生成，无需任何外部模型 Key。

🚀 **零门槛体验**：https://mcsolve.app.workbuddy.host/ （免登录、免 Token，页面里就能跑求解器与倒计时）
⭐ **仓库**：https://github.com/dengbin21/mcd-profile

## 何时触发

| 用户说 | 走哪条 |
|---|---|
| 「这单怎么点最划算」「帮我算算买什么最省」「我想吃 X，怎么点」 | **McSolve** → `solve` |
| 「我的券什么时候到期」「下周活动我的券还能用吗」「帮我备战」 | **McPreheat** → `preheat` |
| 「我在麦当劳花了/省了多少钱」「吃了多少热量」「我的麦门人格」 | 档案 → `archive` |
| 「我常去哪家店、常点什么」「最近有什么活动」 | 档案 → `savings` / `campaign` |
| 「帮我点一份…」 | 点餐闭环 → `eat`（默认 dry-run，须显式确认） |

**优先级**：用户问「怎么点/怎么买/划算吗」时**先给 McSolve**，不要用 `archive` 的省钱复盘去回答——
后者是历史统计，前者才是「这一单」的答案。

## 环境准备：拿到并配置 Token

Token 来自麦当劳开放平台 **https://open.mcd.cn/mcp** ，按你的用法二选一：

**用法 A · 在 MCP 客户端里当 Skill 用（推荐）**——由宿主 agent 直连 `mcd-mcp`，本项目不碰 Token。
在客户端的 MCP 配置里加一条（以 WorkBuddy 的 `~/.workbuddy/mcp.json` 为例）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer <粘贴你的真实 Token>" }
    }
  }
}
```

⚠️ **别照抄 `mcp-config.example.json` 的 `Bearer ${MCD_MCP_TOKEN}`**：`${}` 展开是本项目 CLI
自己实现的行为，多数 MCP 客户端不支持，直接拷过去会拿到字面量从而 401。客户端里**填真值**。

**用法 B · 直接跑本仓库的 CLI**——三种配法，命中即停：

```bash
export MCD_MCP_TOKEN=<你的 Token>            # ① 环境变量（推荐）
python -m src.cli --token <你的 Token> ...   # ② 命令行传入
cp mcp-config.example.json mcp-config.local.json  # ③ 文件（已 gitignore，不会误提交）
```

扫描顺序：`mcp-config.local.json` → `~/.workbuddy/mcp.json` → `~/.codebuddy/.mcp.json`
→ `~/.cursor/mcp.json` → `mcp-config.example.json`。**不要把真实 Token 写进
`mcp-config.example.json`**——它会被提交到仓库。

**没有 Token 也能玩**：`python -m src.cli demo`、任意命令加 `--offline`（脱敏样例数据），
或直接开在线版 https://mcsolve.app.workbuddy.host/ （免登录免 Token）。

## 一、McSolve：把 `calculate-price` 当「价格预言机」

全场都把 `calculate-price` 当「下单前的最后一步」：调一次，看看多少钱，然后下单，用完即弃。

但它其实是**免费、只读、不产生订单、可以无限次调用**的接口——
换句话说：**不花一分钱，你就能知道任意商品组合的真实实付价。**

```
query-nearby-stores   你的门店
query-meals           全菜单 100+ 款（带图带价）
query-my-coupons      你手里的券（含到期时间）
query-store-coupons   门店活动（三件6折 / 满30减5）
available-coupons     麦麦省可领券
        ↓  本地按券门槛剪枝、枚举候选组合（默认最多追加 3 件）
calculate-price × N   逐单官方验真实价（默认 Top 30）        ★ 引擎在这里
list-nutrition-foods  最优解的营养
```

**主指标是省钱率，不是最低实付**——否则目标函数会退化成「劝人只点 1 件」。
券规则解析支持满减 / 折扣 / 免费 / 买一送一 / 件数折扣（含中文数字「三」）；
买一送一必须组合里含该商品且 `count >= 2` 才生效。

护栏：`MAX_ADD_HARD=4`、`MAX_ENUM=20000`（超出时**整层**收敛、不半层截断，结果无偏）；
验价失败如实披露 `fail_count`，**不谎称「没有解」**。

## 二、McPreheat：活动日历 × 券到期日的交叉冲突

```
campaign-calendar   未来的活动（按日期分桶，不信任 stage 字段）
query-my-coupons    每张券的到期日
now-time-info       服务器时间（倒计时与「今天」的锚点）
```

钩子是**「有些券等不到活动那天」**：券到期日 < 活动开始日即冲突。
产出倒计时 + 冲突清单 + **备战度 S/A/B/C**（扣分重、加分轻，避免「有冲突却评 S」的自相矛盾）。
日期解析不出时**披露 `unparsed_count`**，不说「没有可预热的活动」。

## 能力与工具映射（官方 20 只读工具 + 1 可选写）

> 设计原则：在**「只读」**的边界内把官方工具**用满、用透**——每个工具都有实际产出，不为凑数而凑数。
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
| 8. 生成档案 | 六大画像 + 人格 + 卡片 + 工具清单 | 本地分析（`src/analysis.py`、`src/persona.py`、`src/theme.py`、`src/report/`） |
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
> **有图有价**：`query-meals` 顶层 `meals` 字典一次拿全 100+ 款商品的「图+价+名」。

## 生成的六大画像（`archive`）

| 画像 | 内容 |
|---|---|
| 🎬 **本次点餐战报** | 点餐闭环产物：门店/时间/餐品（**带商品缩略图**）/实付/省下/本单热量 |
| 🏅 **成就徽章墙** | 从数据里挑出的「可炫耀」成就，最多 9 枚（3×3） |
| 💬 **麦门金句** | 千人千面、可截图的传播文案 |
| 💰 **消费** | 累计消费、平均客单、最贵/最省一单、最爱门店、复购最多单品、时段分布 |
| 🎯 **省钱** | 累计原价 vs 实付、**累计省下多少钱、省钱率**、用券次数、最常用券、最划算一单 |
| 🩺 **健康** | 热量/蛋白/脂肪/碳水/钠累计、单餐红黄绿灯、≈几个巨无霸、与每日参考值差距 |
| 🧭 **习惯** | 官方标记的**「我的常点」**、最活跃时段、星期分布、单均件数、消费跨度 |
| 🎫 **权益** | 积分收支、手持券与临期券、门店可用券、麦麦省可领券、商城订单、抽奖活动、**积分兑换力** |
| 📅 **活动** | 官方活动日历中的**今日进行中 / 即将到来**活动 |
| 🎭 **麦门人格** | 按行为特征生成人格标签（如「优惠猎人 / 早餐仪式感大师 / 深夜加餐党」）+ 六维雷达 |

外加一份**MCP 工具覆盖清单**，让「用了多少 MCP 能力」看得见。

**千人千面**：人格 → 一整套深色潮酷配色 + Slogan（`src/theme.py`），
**同一份档案，不同的人打开是不同的那张海报**；分享产物为**竖版长图**（朋友圈/小红书比例）。

## 文案：WorkBuddy 在环（默认规则，可选模型）

**视觉结构**是规则驱动的（配色 / 徽章触发 / 雷达打分），**文字**分两层：

- **默认**：规则模板（`src/textpack.py` 的 `TEXT_REGISTRY`），零依赖、可复现；
- **在环**：由 **WorkBuddy（宿主 agent）** 写**除数值外的全部文字**——
  `brief` 导出素材 → WorkBuddy 生成 `copy_pack.json` → `--copy` 注入渲染。**无需任何外部模型 Key。**

| 字段 | 覆盖内容 |
|---|---|
| `persona_label` / `headline` / `slogan` / `tags` / `quips` / `advice` / `cta` | 人格称号 / 标题句 / 标语 / 标签 / 金句 / 建议 / 号召语 |
| `badge_desc` | 徽章描述 |
| `labels` | **全部区块标题、指标名、KPI 名、表头、页脚、元信息行**（key 见 `brief.text_map`，**须保留 `{占位符}`**） |
| `radar` | 雷达维度名（原名 → 新名） |
| `badge_title` | 徽章名（原名 → 新名） |
| `solve` / `preheat` | 场景整句覆写：`headline` / `grade_word` / `notes`（solve）、`tips`（preheat） |

### 三道护栏（模型写文案难免出错，出错的条目**自动回退默认文案**并显式打印）

1. **键名写错**（如 `sv.hero_title`）→ 提示相近的正确键，否则这条改写静默失效而你还以为生效了；
2. **删掉 `{占位符}`** → 数值会凭空消失，必须回退；
3. **夹带 `facts` 里没有的数字**（疑似编造）→ 回退。

> **数值永不出自模型**：金额 / 单量 / 热量 / 积分一律由规则计算，`{占位符}` 由程序填充。
> `grade_word` 支持两种写法：一个字符串（所有评级同一句），或 `{"S":…,"A":…,"B":…,"C":…}` 按档位各写一句。

## 命令行用法（可直接跑）

```bash
export MCD_MCP_TOKEN=<你的麦当劳 MCP Token>

# —— 吃之前：算这一单怎么点最划算（全程只读，不产生订单）——
python -m src.cli solve --items 板烧鸡腿堡 巨无霸        # 出最优解 + 战报长图
python -m src.cli solve --items 板烧鸡腿堡 --add 3 --top 30 --budget 60
python -m src.cli solve --items 板烧鸡腿堡 --html solve_report.html

# —— 吃之前：活动倒计时 + 券到期冲突 + 备战度（全程只读）——
python -m src.cli preheat

# —— 吃之后：六维复盘 + 麦门人格卡 ——
python -m src.cli archive --html card.html --png card.png --out profile.md
python -m src.cli orders / savings / account / campaign / store / tools

# —— 点餐闭环（默认安全，只算价不下单）——
python -m src.cli stores                          # 查看可选门店
python -m src.cli menu --store 1990262            # 可视化菜单（带图带价，点选导出 code:qty）
python -m src.cli eat --dry-run --items 麦辣鸡腿堡:1 圆筒冰淇淋:2
python -m src.cli eat --yes --items 9900016076:1  # 真实下单（会产生真实费用）

# —— 文案（WorkBuddy 在环）：导出素材 → 生成文案包 → 注入渲染 ——
python -m src.cli brief --for archive                    # 也可 --for solve / --for preheat
#   （WorkBuddy 读取 brief，产出 copy_pack.json）
python -m src.cli archive --copy copy_pack.json --html card.html --png card.png
python -m src.cli solve --items 板烧鸡腿堡 --copy copy_pack_solve.json
python -m src.cli preheat --copy copy_pack_preheat.json

# 离线演示（无需 Token，用脱敏样例数据跑完整链路）
python -m src.cli demo
python -m src.cli --offline solve --items 板烧鸡腿堡
python -m src.cli --offline preheat
```

子命令共 15 个：`archive` `orders` `savings` `account` `campaign` `store` `tools` `card`
`demo` `brief` `stores` `menu` `eat` `preheat` `solve`。
跑完任一条都会给**下一步建议**（preheat → solve → eat → archive → preheat 闭环）。

## 安全准则

- **只读优先**：McSolve / McPreheat / archive 只调用查询类工具，**不发起**取消、抽奖、领券、
  改地址等任何写操作；`solve` 的验价**不产生任何订单**。
- **点餐是唯一写操作，且默认关闭**：不加 `--yes`（或交互未输入「下单」）时只做**算价预览**，
  **绝不调用 `create-order`**；下单前打印门店/餐品/实付明细，须显式确认。
- **真实下单会产生真实订单与费用**，请自行确认门店与餐品后再执行；下单成功保留 `orderId` 以便撤销。
- **隐私**：Token 用环境变量注入，不写入日志、不进产物、不提交仓库；仓库内样例数据均已脱敏。
- **诚实口径**：`order-list` 仅返回最近约 10 单，文案以「最近 N 单」为准，不夸大；
  离线演示的价格为样例估算，产物里会明确标注。
- **免责声明**：结论仅供个人复盘，不构成医疗或营养建议。
