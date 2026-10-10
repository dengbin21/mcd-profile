# 麦麦战绩 · McProfile（Skill）

> **先替你算出最划算的那一单，再帮你复盘吃过的每一单。**
>
> 对 AI 说一句「我想吃板烧鸡腿堡，怎么点最划算」，它就穷举上千种组合、
> 逐一让麦当劳官方 `calculate-price` **验真实价**，给出带 **S/A/B/C 评级**的
> 最优解 + 战报长图——全程只读，**不产生任何订单、不花一分钱**。
>
> 吃完再问「我在麦当劳花了多少、省了多少、我的麦门人格」，把每一单变成
> 「消费 × 省钱 × 健康 × 权益」复盘 + 麦门人格卡。
>
> 还有一句「我的券什么时候到期，赶得上下一场活动吗」，告诉你哪些券等不到那天。

这是一个 **Agent Skill**，不是命令行工具、也不是网页应用。它本身不包含任何
可执行代码——由 **宿主 AI 代理**读取 `SKILL.md` 的指令，直接调用麦当劳官方
MCP（`mcd-mcp`）的 20 个只读工具完成全部玩法。因此：

- 用户**不需要 clone 仓库**、不需要装 Python、不需要任何模型 Key；
- 只读优先：求解 / 预热 / 复盘全部只调用查询类工具，不领券、不抽奖、不下单；
- 唯一写操作 `create-order` 作为可选点餐闭环，默认关闭、须显式确认。

⭐ **觉得有意思？给个 Star 就是最大的支持 → [github.com/dengbin21/mcd-profile](https://github.com/dengbin21/mcd-profile)**

---

## 怎么用（三步）

1. **把本 Skill 装进你的 AI 代理**（支持 Skill + MCP 的客户端，如 WorkBuddy / Codex）：
   导入本仓库，或把 `SKILL.md` 放进客户端的 skills 目录。
2. **配好麦当劳官方 MCP**（一次性）：到 **https://open.mcd.cn/mcp** 申请 Token，
   然后在客户端的 MCP 配置里加一条（以 WorkBuddy 的 `~/.workbuddy/mcp.json` 为例）：

   ```json
   {
     "mcpServers": {
       "mcd-mcp": {
         "type": "streamablehttp",
         "url": "https://mcp.mcd.cn",
         "headers": { "Authorization": "Bearer <你的真实 Token>" }
       }
     }
   }
   ```

   ⚠️ Token 必须填真值；重启客户端后确认 `mcd-mcp` 已连接（工具列表里有
   `calculate-price` 即可）。
3. **直接说人话**。宿主 agent 读了 `SKILL.md` 就知道该调哪些工具：

| 你说 | 走哪条 |
|---|---|
| 「这单怎么点最划算」「我想吃 X，怎么点省」 | **McSolve**：`query-meals` + `calculate-price` ×30 逐单验价 |
| 「我的券什么时候到期」「赶得上活动吗」 | **McPreheat**：`campaign-calendar` × 券到期日 |
| 「我在麦当劳花了/省了多少钱」「我的麦门人格」 | **archive**：`order-list` → 六维画像 + 人格卡 |
| 「帮我点一份…」 | 点餐闭环（默认 dry-run，须显式确认才下单） |

## 三个招牌玩法

### ① McSolve · 麦麦最优解（吃之前）

把官方 `calculate-price` 当**价格预言机**反复调用：

```
query-meals           全菜单（带图带价）
query-my-coupons      你手里的券（含到期）
query-store-coupons   门店活动券
available-coupons     麦麦省可领券
        ↓  本地按券门槛剪枝、枚举候选组合
calculate-price × 30  逐单官方验真实价     ★ 引擎
list-nutrition-foods  最优解的营养
```

- 主指标是**省钱率**而非最低实付——否则求解器会退化成「劝人少买」；
- 本地估算只用于排序，**最终价格一律以官方验价为准**；
- 支持**预算 × 热量双约束**（`--budget` 限实付、`--kcal` 限热量）；
- 产出「你的直觉点法 vs 算法最优解」对照 + S/A/B/C 评级 + 战报长图。

### ② McPreheat · 麦麦预热台（吃之前）

把官方活动日历和**券的到期时间**交叉起来：

> 距「秋日限定新品上新」还有 7 天——但你有 1 张券 3 天后就到期。
> **这张券等不到那天。**

- 冲突是**算出来的**（券到期日 < 活动开始日），不是编的文案；
- 产出倒计时 + 冲突清单 + 备战度 S/A/B/C 评分 + 预热卡。

### ③ archive · 六维复盘 + 麦门人格卡（吃之后）

把历史订单翻译成看得懂、晒得出的个人档案：

- 消费 / 省钱 / 健康 / 习惯 / 权益 / 活动 **六张画像**；
- **麦门人格** + 千人千面主题（配色/徽章/金句），同一个人不同人打开不同海报；
- 一并输出 **MCP 工具覆盖清单**，让「用了多少 MCP 能力」看得见。

## 依赖的麦当劳 MCP 能力（20 只读 + 1 可选写）

| 域 | 工具 |
|---|---|
| 订单 | `order-list`、`query-order` |
| 权益 | `query-my-account`、`query-my-coupons`、`query-my-prizes`、`query-lottery-info`、`available-coupons` |
| 商城 | `mall-order-list`、`mall-order-detail`、`mall-points-products` |
| 场景 | `query-nearby-stores`、`delivery-query-addresses`、`delivery-query-stores`、`query-meals`、`query-meal-detail`、`query-store-coupons`、`calculate-price` |
| 营销 | `campaign-calendar`、`now-time-info` |
| 营养 | `list-nutrition-foods` |
| **点餐（可选写）** | `create-order` —— 仅用户显式确认时触发 |

> **刻意不用**：`cancel-order` / `mall-create-order` / `party-order-create` /
> `auto-bind-coupons` / `draw-lottery` / `delivery-create-address` 等写操作。
> 详细调用流程、字段与业务价值见 **[MCP_INTEGRATION.md](./MCP_INTEGRATION.md)**。

## 安全准则

- **只读优先**：求解 / 预热 / 复盘只调用查询类工具；`calculate-price` 验价不产生订单。
- **点餐是唯一写操作且默认关闭**：未获显式确认前只做算价预览，绝不调用 `create-order`；
  下单前先列出门店/餐品/实付明细，下单成功保留 `orderId` 以便撤销。
- **口径诚实**：`order-list` 仅返回最近约 10 单，定位为「复盘」而非「年度账单」；
  券的核销通常需要券绑定的凭证商品码（官方卡包接口不返回），验价以官方按账号
  自动匹配的券价为准，联网战报中对此有显式披露。
- **隐私**：Token 只存在客户端的 MCP 配置里，不写日志、不进产物。
- **免责**：结论仅供个人复盘，不构成医疗或营养建议。

## 仓库结构

```
mcd-profile/
├── SKILL.md                # Skill 定义（本产品本体：触发表 / 玩法 / 工具映射 / 安全）
├── README.md               # 本文档（怎么用）
├── MCP_INTEGRATION.md      # 麦当劳 MCP 集成说明（Server / Tool / 调用流程 / 业务价值）
├── CONTEST_DECLARATION.md  # 参赛声明（官方原文，未改动）
└── workbuddy.md            # WorkBuddy 开发对话上下文（联动奖励核验用）
```

## 许可证

MIT。

> 免责声明：本项目为个人参赛作品，与麦当劳官方无隶属关系。
