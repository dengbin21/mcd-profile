# WorkBuddy 开发对话上下文 · workbuddy.md

> 本文记录使用 **WorkBuddy** 开发「麦麦档案 McProfile」过程中的关键对话与决策，
> 用于核验是否符合 WorkBuddy 联动活动奖励条件。

## 一、项目背景

- **开发方式**：全程在 WorkBuddy（CodeBuddy）中完成——需求拆解、数据侦察、
  竞赛情报分析、方向选择、代码编写、真实接口联调、文档产出与交付。
- **目标**：参加麦当劳 MCP 创意开发大赛，基于官方 `mcd-mcp` 开发一个有实际价值的 Skill。

## 二、关键开发步骤（对话脉络）

1. **确认 MCP 接入**
   - 读取 `~/.codebuddy/.mcp.json`，确认客户端支持 `streamablehttp` 类型并归一化为 `http`。
   - 结果：`initialize` 握手成功，`tools/list` 返回 **35 个工具**。

2. **竞赛情报分析（决定做什么）**
   - 用真实账号实测 MCP **全部 35 个工具**，并抓取官方仓库 issues 与 RANKING。
   - 关键发现：**33 个在册作品里，70% 挤在「省钱」+「营养」两条赛道**，全部都在
     「吃之前」竞争；而 MCP 里整整一层**「订单后」能力**（`order-list`、`query-order`、
     `cancel-order`、`query-survey-coupon`、`mall-order-*`）几乎无人使用。
   - 决策：**避开红海，做「订单后复盘」这一白地**——即「麦麦档案」。

3. **数据侦察（真实联调）**
   - `order-list` → 实测返回 **10 条真实历史订单**，字段含
     `orderId / createTime / storeName / orderStatus / realTotalAmount` 与
     `orderProductList[].comboItemList[]`（套餐成分拆解）。
   - `query-my-account` → 积分账户（可用 1320.1 / 累计 34703.1）。
   - `query-my-coupons` / `query-my-prizes` / `mall-order-list` → 券、奖品、商城订单均可用。
   - 进一步把订单域扩展到 **权益 / 商城 / 场景 / 营销 / 营养** 五大域，合计锁定
     **20 个只读工具**（门店、地址、菜单、常点、门店券、算价、活动日历、服务器时间、营养库…）。
   - 结论：**数据够厚，足以支撑一个「复盘」产品**；约束是 `order-list` 无分页（约 10 单）。

3.5 **点餐链路侦察（为「点餐→晒图」闭环铺路）**
   - 实测 `create-order` 入参：`storeCode / orderType（1 到店 / 2 外送）/ beType` 必填，
     商品用 `items[{productCode, quantity, roundList, couponId, modification}]`。
   - **关键硬依赖**：到店场景 `takeWayCode` **必传**，且其值**只能来自 `calculate-price`
     返回的 `takeWayList[].code`** → **必须「先算价、再下单」**。
   - 另发现 `calculate-price` 价格字段单位为**分**，须统一换算为元。
   - **富菜单一处发现**：`query-meals` 的**顶层 `meals` 是字典**（`{code: {name, image,
     currentPrice, originalPrice}}`）——**一次调用拿全 100+ 款的「图+价+名」**；
     配合 `categories`（类目）与 `frequent`（我的常点），即可拼出带图带价的完整菜单用于展示与选餐，无需额外网络调用。
   - **陷阱**：`canWithOrder` 实测对**全部商品恒为 `false`**（含可正常下单商品），**不是可售标志**，已弃用。

4. **核心实现**
   - `src/mcp_client.py`：极简 MCP Streamable HTTP 客户端（兼容 JSON 与 SSE，含调用日志）。
   - `src/models.py`：订单/权益/商城/场景/营销/**点餐**领域模型与解析。
   - `src/sources.py`：订单/权益/商城/场景/营销/营养 **六域 20 个只读工具**采集 + 离线兜底。
   - `src/nutrition.py`：营养库与「订单商品名 → 营养」三级匹配。
   - `src/analysis.py`：消费 / 省钱 / 健康 / 习惯 / 权益 / 活动 **六大画像**。
   - `src/persona.py`：麦门人格引擎（六维雷达 + 标签）。
   - `src/theme.py`：**千人千面主题引擎**（人格 → 配色/光晕/Slogan + 成就徽章 + 金句）。
   - `src/ordering.py`：**点餐链路**（选店→**富菜单**→算价→安全护栏→下单→复核）。
   - `src/menu_view.py`：**可视化点餐菜单**（把富菜单渲染成带图带价网页，支持类目筛选/搜索/点选购物车，一键导出 `code:qty` 下单清单）。
   - `src/images.py`：**商品图工具**（下载缓存 / 转 `data:` URI 自包含 / 读为数组供 PNG 嵌入；全程优雅降级）。
   - `src/textpack.py`：**文案层（WorkBuddy 在环）**——文本注册表（除数值外全部文字的单一事实源）+ `brief` 导出素材 → 模型写 `copy_pack.json` → `--copy` 注入，覆盖人格称号、区块标题、指标名、雷达维度、徽章名等；无外部 Key。
   - `src/report/`：Markdown 档案 + **暗黑潮酷** HTML / **竖版长图** PNG + 工具覆盖清单。
   - `src/archive.py`：采集→分析→人格聚合（可并入**本次战报**）。
   - `src/cli.py`：命令行入口（archive / orders / savings / account / campaign / store / tools / demo / **brief** / **stores / menu / eat**）。

5. **工程打磨**
   - **套餐口径**：发现订单里既有单品也有套餐，遂按 `comboItemList` **拆件计营养**，
     并披露「营养映射覆盖率」，避免高估/低估。
   - **退款**：识别 `orderStatus` 含「退款」的订单，不计入消费与健康统计。
   - **工具覆盖最大化**：在「只读复盘」边界内，把官方可用工具拉到 **20 个**，
     并让每个工具都有实际产出；末尾输出「工具覆盖清单」自证，不做凑数调用。
   - **写操作最小化 + 三道护栏**：仅保留 `create-order` 供**可选点餐闭环**，
     且**默认 dry-run、下单前打印明细、须显式确认**；`cancel-order` / `draw-lottery` /
     `auto-bind-coupons` / `delivery-create-address` 等一律不调。
   - **省钱复盘**：逐单调 `query-order` 取券与优惠，算出**累计省下金额与省钱率**。
   - **官方常点**：用 `query-meals` 的 `frequent` 字段，拿到官方标记的「我的常点」。
   - **千人千面视觉**：人格 → 深色潮酷配色 + 玻璃拟态 + 霓虹光晕 + 徽章墙 + 金句；
     分享产物由「方图」升级为**竖版长图**（1080×自适应，朋友圈/小红书比例）。
   - **点餐不再单薄（有图·有价）**：`query-meals` 顶层 `meals` 一次拿全商品**图+价+名**；
     `src/images.py` 把商品图**内嵌**进分享卡——HTML 转 `data:` URI **单文件自包含**（脱网可见），
     PNG 用 matplotlib `imshow` 嵌图；**缺图/断网一律优雅降级回纯文字**。
   - **可视化点餐（回应「交互看不到图」）**：终端与选择卡片渲染不了图片，遂把菜单渲染成网页
     （`src/menu_view.py` / `menu` 子命令）——117 款商品图+价+折扣、类目筛选、搜索、点选购物车，
     底部实时汇总，一键复制**点餐话术**粘贴回对话即可点单（也可复制 `code:qty` 喂给 `eat --items ...`）。
   - **文案层（WorkBuddy 在环）**：视觉结构走规则（可复现），**除数值外的全部文字**可交给
     WorkBuddy 生成——`brief` 导出素材 + 全部文字默认值 + 输出 schema，WorkBuddy 产出
     `copy_pack.json`，`--copy` 注入渲染。覆盖：人格称号 / 标题句 / 标语 / 标签 / 金句 / 建议 /
     徽章描述 / CTA，以及 `labels`（**全部区块标题、指标名、KPI 名、表头、页脚、元信息行**）、
     `radar`（雷达维度名）、`badge_title`（徽章名）。**无需外部 Key**，不注入即回退规则模板。
   - **数值永不出自模型**：金额/单量/热量/积分一律规则计算；`labels` 的 `{占位符}` 由程序填充，
     模型只改文字、必须保留占位符（缺失时自动回退默认模板，保证数字不丢）。
   - 称号可由 WorkBuddy 按数据命名（如「满减操盘手」），但**配色仍锚定规则人格**，视觉不错乱。
   - **Token 读取 bug（真机发现并修复）**：联网时报「已回退样例」，但配置文件里明明带真实 Token。
     根因是 `_token_from_config()` 先扫到项目占位符 `${MCD_MCP_TOKEN}` 就直接返回 `None`，
     未继续扫描下一个配置；修复为「占位符环境变量为空时 `continue` 继续扫描」。修复后 **20/20 工具全绿**。
   - **PNG 无 emoji 字体**：matplotlib 无彩色 emoji 字体，长图里 emoji 变豆腐块；
     遂在 PNG 渲染链路**剥离 emoji**（HTML/Markdown 保留彩色 emoji），并把底部留白改为**动态定高**。
   - **隐私**：仓库内所有样例数据重制为**脱敏示例**；Token 只走环境变量。

## 三、WorkBuddy 在其中的作用

| 环节 | WorkBuddy 做了什么 |
|---|---|
| 环境侦察 | 读取 MCP 配置、探测端点、核对客户端类型支持 |
| 竞赛情报 | 实测 35 个工具能力、抓取官网作品与排行，产出情报分析并给出方向建议 |
| 接口联调 | 直接用 HTTP 调 `order-list` / `query-order` / `query-meals` / `calculate-price` / `create-order` 等工具，逐字段确认真实结构（含下单硬依赖链） |
| 代码生成 | 生成并迭代 12 个 Python 模块与 CLI |
| 数据工程 | 订单归一化、套餐拆件、营养匹配、六域 20 工具采集编排、脱敏样例数据（含战报样例） |
| 视觉设计 | 千人千面主题引擎、暗黑潮酷 HTML 卡片、动态定高的竖版长图 PNG、商品图内嵌（自包含 HTML / matplotlib 嵌图） |
| 文案生成 | WorkBuddy 在环写**除数值外的全部文字**（含人格称号/区块标题/指标名/雷达维度/徽章名）：`brief` 取素材 → 产出 `copy_pack.json` → `--copy` 注入（无需外部 Key） |
| 文档产出 | 生成 README / MCP_INTEGRATION / CONTEST_DECLARATION / SKILL / 本文件 |
| 验证 | 离线 `demo` + 13 项自测、联网全链路（20 工具采集 + 六大画像 + 人格 + 卡片）、`eat --dry-run` 点餐算价实跑、真实下单并复核、含图成品（HTML 自包含 / PNG 1080×2732）实跑通过 |

## 四、可复现的验证命令

```bash
# 离线自测（无需 Token）
python tests/test_smoke.py
python -m src.cli demo

# 联网全链路（需 MCD_MCP_TOKEN）
export MCD_MCP_TOKEN=<你的 Token>
python -m src.cli archive --html card.html --png card.png

# 文案在环（WorkBuddy 写文案，无需外部 Key）
python -m src.cli brief --out copy_brief.json
#   （WorkBuddy 读取 brief 生成 copy_pack.json 后）
python -m src.cli archive --copy copy_pack.json --html card.html --png card.png

# 点餐闭环（默认安全，只算价不下单）
python -m src.cli stores
python -m src.cli menu --store 1990262        # 可视化菜单：带图带价，点选导出 code:qty
python -m src.cli eat --dry-run
# 真实下单（会产生真实订单与费用，需自行确认）
# python -m src.cli eat --yes --items <商品code>:1 --share out.png
```

## 五、小结

本项目从「配置 MCP」→「情报分析选方向」→「可跑通的参赛作品」，全流程在 WorkBuddy
中完成，包含对 MCP 35 个工具的实测、对 33 个竞品的情报分析，以及真实接口联调与多次
工程修正，属于 WorkBuddy 深度参与创作的原创作品。
