# MCP 集成说明 · MCP_INTEGRATION

本文说明「麦麦档案」实际使用的**麦当劳 MCP Server**、**Tool**、**调用流程**与**业务价值**。

---

## 1. 使用的 MCP Server

| 项 | 值 |
|---|---|
| 服务名 | **`mcd-mcp`** |
| 传输方式 | Streamable HTTP（`type: streamablehttp`，等价 `http`） |
| 端点 | `https://mcp.mcd.cn` |
| 鉴权 | 请求头 `Authorization: Bearer <MCD_MCP_TOKEN>` |
| 协议 | MCP JSON-RPC 2.0（`initialize` / `tools/list` / `tools/call`） |
| 工具总数 | 35 个（2026-10 实测） |
| 本作品调用 | **20 个只读工具** + **1 个可选写操作 `create-order`**（默认关闭，见 §2.1 / §8） |
| 服务声明位置 | 本项目 `mcp-config.example.json`（脱敏示例） |

握手实测：`initialize` 返回 `serverInfo.name = mcd-mcp`；`tools/list` 返回 35 个工具；
`tools/call` 成功返回 `structuredContent.data`。

## 2. 实际用到的 Tool（20 只读 + 1 可选写）

> 设计原则：在**「只读复盘」**的边界内，尽量把官方工具用满、用透——每个工具都有实际产出，
> 不做「凑数调用」。写操作中**只保留 `create-order` 且默认关闭**（点餐闭环，需显式确认），
> 其余写操作与团餐专用工具**刻意不用**（见文末 §7）。

| # | 域 | Tool | 入参 | 用途 |
|---|---|---|---|---|
| 1 | 订单 | `order-list` | 无 | **数据主体**：历史订单（实付/门店/套餐成分） |
| 2 | 订单 | `query-order` | `orderId` | 单笔详情：**用券明细 / 优惠金额 / 堂食外带 / 门店地址** |
| 3 | 权益 | `query-my-account` | 无 | 积分账户（可用/累计/已用） |
| 4 | 权益 | `query-my-coupons` | 无 | 手持券资产与到期时间 |
| 5 | 权益 | `query-my-prizes` | 无 | 抽奖奖品（可用/失效） |
| 6 | 权益 | `query-lottery-info` | 无 | 当前积分抽奖活动与奖品池 |
| 7 | 权益 | `available-coupons` | 无 | 麦麦省可领取券 |
| 8 | 商城 | `mall-order-list` | 无 | 积分商城订单 |
| 9 | 商城 | `mall-order-detail` | `orderId` | 商城订单详情（耗时/实付积分） |
| 10 | 商城 | `mall-points-products` | 无 | 积分可兑换商品（**积分兑换力**） |
| 11 | 场景 | `query-nearby-stores` | `beType, searchType` | 收藏/附近门店 |
| 12 | 场景 | `delivery-query-addresses` | 无 | 外送地址 |
| 13 | 场景 | `delivery-query-stores` | `addressId, beType` | 地址可配送门店 |
| 14 | 场景 | `query-meals` | `storeCode, orderType, beType` | 门店菜单（**顶层 `meals` 字典一次拿全带图带价**：`name/image/currentPrice/originalPrice`；含类目 `categories` 与官方「我的常点」`frequent`） |
| 15 | 场景 | `query-meal-detail` | `storeCode, orderType, beType, code` | 单个餐品的组成 / 图片（改菜或补图时才调） |
| 16 | 场景 | `query-store-coupons` | `storeCode, orderType, beType` | 最爱门店的可用券 |
| 17 | 场景 | `calculate-price` | `storeCode, orderType, beType, items` | 按「常点」预估价格；**并返回下单所需的 `takeWayList`**；**McSolve 中作为「验价引擎」反复调用（见 §2.2）** |
| 18 | 营销 | `campaign-calendar` | 无 | 官方营销活动日历 |
| 19 | 营销 | `now-time-info` | 无 | 服务器时间（作为「今天」基准） |
| 20 | 营养 | `list-nutrition-foods` | 无 | 160 款餐品营养库（订单→营养映射） |
| 21 | **点餐（写）** | `create-order` | `storeCode, orderType, beType, items[], takeWayCode, …` | **可选**：真实下单（`eat --yes` 才触发） |

### 2.1 点餐闭环（唯一写操作，默认关闭）

`src/ordering.py` 实现一条**严格按官方依赖顺序**的点餐链路，
`create-order` 只有在**显式确认**（`--yes` 或交互输入「下单」）时才被调用：

```
query-nearby-stores / delivery-query-stores   取门店（storeCode / beCode）
  → query-meals                               取富菜单（code→name/image/price）+ 类目 + 常点
    → query-meal-detail                       补商品组成 / 单品图（按需）
      → calculate-price                       算价，并拿到 takeWayList[].code
        → create-order                        下单（takeWayCode 取自上一跳）
          → query-order                       复核订单状态
```

> **硬依赖**：到店场景 `create-order` 的 `takeWayCode` **必传**，且**只能来自
> `calculate-price` 返回的 `takeWayList[].code`** —— 因此**下单前必须先算价**。
> `calculate-price` 的价格字段单位为**分**（代码内统一换算为元）。

> **富菜单一处发现**：`query-meals` 的**顶层 `meals` 是一个字典**（`{code: {name, image,
> currentPrice, originalPrice, canWithOrder}}`），**一次调用即可拿全 100+ 款商品的「图 + 价 + 名」**；
> `categories[].meals[]` 只带 `{code, tags}`，`frequent` 是「我的常点」。
> 据此 `src/ordering.py` 的 `load_menu()` **无需额外网络调用**即可拼出带图带价、带类目的完整菜单，供展示与选餐。

> **可视化点餐**（`src/menu_view.py` / `menu` 子命令）：终端与选择卡片渲染不了图片，
> 故把上述富菜单渲染成**可浏览的网页**——商品图 / 价 / 折扣 / 类目筛选 / 搜索 / 点选购物车，
> 点完**一键复制点餐话术**（或导出 `code:qty` 清单），交给 `eat --items ... [--yes]`，
> 让「看图点餐 → 真实下单 → 生成战报」形成完整闭环。
> ⚠️ `canWithOrder` 经实测对**全部商品恒为 `false`**（含可正常下单商品），**不能当作可售标志**，故不使用。

下单后，`src/archive.py` 的 `build_meal_report(...)` 会把这一单组装成**「本次点餐战报」**
（门店/餐品/实付/省下/本单热量），并**并入历史档案**，交给 `src/report/` 渲染成千人千面的分享长图。
战报里的每个餐品都会**内嵌商品图**：`src/images.py` 负责下载与格式转换，
HTML 卡片转 `data:image/...;base64` **单文件自包含**（脱网也看得到图），PNG 长图用 matplotlib 把图片
`imshow` 进对应坐标；**任意缺图 / 断网 / 缺依赖都优雅降级为纯文字**，绝不让配图拖垮主流程。

### 2.2 `calculate-price`：从「最后一步」到「验价引擎」（McSolve）

官方 35 个工具里，`calculate-price` 有个容易被忽略的性质：
**只读、免费、不产生订单、可无限次调用**——它是一台**「价格预言机」**。

大多数作品（含本作品的 `eat` 链路）只把它当「下单前的最后一步」：调一次，
看看多少钱，然后下单。McSolve（`src/solver.py` + `solve` 子命令）把它当**模拟器**反复调用：

```
query-nearby-stores / query-meals     门店与全菜单（100+ 款，带图带价）
query-my-coupons / query-store-coupons / available-coupons     三层券
        ↓
  本地枚举：必选 + 0..3 件追加 → 按券门槛与预算剪枝 → 候选数千种
  按「粗估省钱率」排序
        ↓
calculate-price × N（默认 N=30）      逐单验真实价   ★ 引擎
        ↓
list-nutrition-foods                  最优解的营养
```

| 关键点 | 做法 |
|---|---|
| **组合爆炸** | 本地枚举（免费）与官方验价（有成本）分离：枚举数千种，只对 **Top 30** 验价 |
| **排序指标** | 用**省钱率**而非实付——否则「什么都不加」永远最优，求解器会退化成「劝人少买」 |
| **券规则解析** | 从券面文案提取门槛：`满30减5` / `三件任选6折` / `免费X` / `买一送一`，**件数不够就不估折扣** |
| **件数约束** | 「三件任选6折」须凑够 3 件才生效（含中文数字「三」的解析） |
| **口径诚实** | 本地估算**只用于排序**；最终 `original / paid / discount` **一律取官方返回值**，绝不拿估算当结果 |
| **对照基准** | 首个候选恒为「只点必选」= 你的直觉点法，用于输出「直觉 vs 算法」的实付与均价对比 |

产出：带 **S/A/B/C 评级**的最优解 + 「直觉点法 vs 算法最优解」对照 + 战报长图
（`src/solve_report.py`）。**全程只读**：不领券、不抽奖、不下单。

> 典型结果（脱敏样例数据）：只点板烧鸡腿堡 ¥21.50（不触发折扣）；
> 凑够三件后触发「6 折」，实付 ¥21.90 拿到 3 件——**多花 ¥0.4，单件均价降 66%**。

### 2.3 `campaign-calendar` × 券到期：从「活动列表」到「预热冲突」（McPreheat）

`campaign-calendar` 在多数作品里只是一个静态列表——列出来，看完没有下文。
但把它和**券的到期时间**交叉一次，就会长出一个真实的冲突（`src/preheat.py` + `preheat` 子命令）：

```
campaign-calendar    未来活动的日期（如 2026-10-25「周末欢乐桶限时回归」）
query-my-coupons     每张券的 instructions.availableTime（如 2026.10.12 23:59 到期）
now-time-info        服务器当前时间 → 倒计时基准
        ↓  交叉判断：券到期日 < 活动开始日
「这张券等不到那天」  ★ 钩子在这里
```

| 关键点 | 做法 |
|---|---|
| **不信任 `stage`** | 真实接口里 `stage`（today/future）未必可靠，一律**按日期判断** |
| **倒计时目标取严格未来** | 今天已在跑的活动归到「进行中」，不进倒计时——否则倒计时恒为 0，钩子失效 |
| **冲突判定** | 券到期日 < 活动开始日 → 归入 `missing`，并在卡片最前排红块告警 |
| **压线标记** | 撑得到但 7 天内到期 → 单独标「压线」，提示风险 |
| **备战度评分** | 纯规则可解释：miss −25 / 紧急 −10 / 当天无券 −20 / 今日有活动 +5 / 积分够兑 +5 |
| **口径诚实** | 「用户一张券都没有」与「券接口没返回」在代码里长一样，**此时不臆测**，不给吓人结论 |

产出：倒计时 + 冲突预警 + 备战度 S/A/B/C 的竖版预热卡（`src/preheat_report.py`），
网页端落地页的倒计时**实时到秒**。**全程只读**：不领券、不抽奖、不下单。

> 典型结果（脱敏样例数据）：距「秋日限定新品上新」还有 7 天，
> 但「满30减5元券」3 天后到期 → **赶不上**，备战度 A（75/100）。

## 3. 调用流程

```
                      用户：看看我的麦麦档案
                                │
   ┌────────────────────────────┼────────────────────────────┐
   │                  数据采集（src/sources.py）                │
   │                                                            │
   │  【订单域】 order-list ──► 历史订单                         │
   │            └ query-order ×N ──► 券 / 优惠 / 餐方式明细       │
   │  【权益域】 query-my-account / query-my-coupons /           │
   │            query-my-prizes / query-lottery-info /           │
   │            available-coupons                                │
   │  【商城域】 mall-order-list ─► mall-order-detail ×N          │
   │            └ mall-points-products（积分兑换力）              │
   │  【场景域】 query-nearby-stores / delivery-query-addresses   │
   │            └ delivery-query-stores                          │
   │            └ query-meals（最爱门店）──► frequent「我的常点」  │
   │                └ query-meal-detail / query-store-coupons     │
   │                └ calculate-price（再来一单预估）             │
   │  【营销域】 campaign-calendar / now-time-info                │
   └────────────────────────────┬───────────────────────────────┘
                                │
             list-nutrition-foods ──► 160 条营养库
                                │
       订单商品名 ──(三级匹配)──► 营养值（热量/钠/蛋白…）
                                │
   ┌────────────────────────────┼────────────────────────────┐
   │        六大分析（analysis.py）                             │
   │  消费 / 健康 / 权益 / 省钱 / 习惯 / 活动                   │
   └────────────────────────────┬────────────────────────────┘
                                │
                     麦门人格引擎（persona.py）
                                │
              Markdown 档案 + 可分享卡片（HTML/PNG）
              + MCP 工具覆盖清单（本次调了哪些、产出多少）

   ──────────────────────（可选）点餐闭环 ──────────────────────
   用户：来一份 …
        │
   ordering.py：query-nearby-stores → query-meals → query-meal-detail
                → calculate-price（拿 takeWayCode）
                → 【安全护栏：默认 dry-run，须显式确认】
                → create-order → query-order（复核）
        │
   本次战报（MealReport）──► build_archive(order_ctx=…) ──► 并入上面的档案
```

### 关键数据处理规则（已在代码中实现）

- **订单归一化**：`order-list` 返回 `{"list":[...]}`；`realTotalAmount` 是**字符串金额（元）**。
- **优惠明细补全**：`order-list` 不含券与优惠，需逐单调 `query-order` 取
  `couponList / totalDiscountAmount / takeWay / storeAddress`，据此算出**省钱率**。
- **套餐展开**：订单行若含 `comboItemList`，**拆成单件**再计营养；
  单件（如周边、派）无 `comboItemList` 则用其 `productName`。
- **营养匹配**：`src/nutrition.py` 的三级匹配——归一化精确 → 核心名精确 → 相似度阈值；
  命中率以「覆盖率」如实披露。
- **商城订单拆包**：`mall-order-list` 返回 `[{hasNext, lastId, list:[...]}]`（多包一层），需拆包。
- **门店参数推导**：从订单里**最常出现的门店**推断 `storeCode`，并用该店订单的
  `beType/orderType` 调 `query-meals` 等场景工具，避免用户手填。
- **临期券**：以 `now-time-info` 的服务器日期为基准，计算 30 天内到期券。
- **退款处理**：`orderStatus` 含「退款」的订单**不计入消费与健康统计**，但单独计数提示。
- **全局容错**：任一工具失败 `src/sources.py` 记入 `errors` 与 `tool_calls`，其余照常。

## 4. 真实调用示例

### 4.1 取历史订单

```bash
curl -sS -X POST https://mcp.mcd.cn \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $MCD_MCP_TOKEN" \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"order-list","arguments":{}}}'
```

返回（节选，实测真实结构）：

```json
{"list":[{
  "orderId":"1030...271","createTime":"2026-10-09 08:46:54",
  "storeName":"南京徐庄路快捷小站","orderStatus":"订单已完成","realTotalAmount":"15.6",
  "orderProductList":[{
    "productName":"猪柳蛋麦满分套餐","quantity":1,
    "comboItemList":[
      {"name":"猪柳蛋麦满分","quantity":1},
      {"name":"脆薯饼","quantity":1},
      {"name":"大杯鲜萃咖啡","quantity":1}
    ]}]}]}
```

### 4.2 取单笔订单详情（补优惠与用券）

```bash
curl -sS -X POST https://mcp.mcd.cn -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $MCD_MCP_TOKEN" \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"query-order","arguments":{"orderId":"1030459020000661722407464271"}}}'
```

返回关键字段：`totalAmount`（原价）、`realTotalAmount`（实付）、
`totalDiscountAmount`（优惠）、`couponList[]{couponName,discountAmount}`、
`takeWay`（堂食/外带）、`storeAddress`。

### 4.3 取「我的常点」

```bash
curl -sS -X POST https://mcp.mcd.cn -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $MCD_MCP_TOKEN" \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call",
       "params":{"name":"query-meals","arguments":{"storeCode":"1990262001","orderType":1,"beType":1}}}'
```

返回 `{categories, meals, frequent}`，其中 `frequent.code` 即官方标记的**「我的常点」**。

## 5. 业务价值

| 维度 | 说明 |
|---|---|
| **把算价当模拟器** | `calculate-price` 免费、只读、可反复调用 → 穷举 + 官方验价，给出**「最优解」而非「建议」** |
| **把活动日历交叉出冲突** | `campaign-calendar` × 券的 `availableTime` × `now-time-info` → 算出「**哪些券赶不上下一场活动**」，给倒计时一个行动理由（§2.3） |
| **盘活「订单后」数据** | 把 MCP 里几乎无人使用的历史订单/权益，变成**用户看得懂的个人复盘** |
| **工具覆盖最大化** | 在只读边界内调用 **20 个官方工具**，并输出「工具覆盖清单」自证 |
| **口径诚实** | `order-list` 仅返回最近约 10 单，故定位为「档案/体检」而非「年度账单」 |
| **营养可解释** | 套餐按 `comboItemList` 拆件映射营养，并披露覆盖率，不硬凑 |
| **可下单可分享** | 可选点餐闭环（`create-order`，默认关闭）+ 千人千面竖版长图，形成「点餐→晒图」传播闭环 |
| **天生可传播** | 人格 + 雷达 + 反差点 + 战报 + 徽章墙，契合按 Star 计分的赛制 |
| **风险可控** | 档案只读；唯一写操作默认 dry-run、下单前打印明细、须显式确认 |

## 6. 错误与降级

- 网络/协议异常：`src/mcp_client.py` 统一抛 `McpError`，兼容 JSON 与 SSE 响应。
- 单个工具失败不致命：`src/sources.py` 记录告警并计入工具清单，其余工具照常。
- 全部失败/无 Token：自动回退 `data/` 下的**脱敏样例数据**，`demo` 命令离线可用。
- 无 Token 调用：`initialize`/`tools/call` 返回 403，属预期，请配置 `MCD_MCP_TOKEN`。

## 7. 刻意未使用的工具（边界说明）

| 类别 | 工具 | 不用的原因 |
|---|---|---|
| 交易（写） | `cancel-order`、`mall-create-order`、`party-order-create` | 复盘产品不发起取消/代下单（`create-order` 例外，见 §2.1，默认关闭） |
| 权益（写） | `auto-bind-coupons`、`draw-lottery` | 不替用户领券/抽奖，避免误操作 |
| 地址（写） | `delivery-create-address` | 不改动用户地址簿 |
| 团餐专用 | `query-promotions`、`query-meal-assistance`、`query-meal-detail`(团餐口径) | 仅企业团餐（`beType=6`）场景，个人档案不适用 |
| 派对（深层） | `query-party-city/-store/-date/-session` | 属「活动策划」而非「事后复盘」，本作品不纳入主链路 |

> 这些工具在需要时可作为独立功能扩展，但不应混进「档案复盘」的只读语义中。

## 8. 写操作安全护栏

`create-order` 是本作品唯一会**改变用户账户状态**的调用，故设置三道护栏（`src/ordering.py`）：

1. **默认 dry-run**：`place()` 必须收到 `confirm=True`，否则**直接抛错拒绝**；
   CLI 不加 `--yes` 时只走 `calculate-price`，**绝不触碰 `create-order`**。
2. **下单前打印明细**：门店 / 餐品清单 / 原价 / 优惠 / 实付 / 取餐方式，交给用户确认。
3. **留痕可撤销**：下单成功后打印并保留 `orderId`，提示可在官方渠道 `cancel-order`。

> ⚠️ **真实下单会产生真实订单与费用**。本作品的默认行为是「算价预览」，请自行确认后再执行。
