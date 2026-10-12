# WorkBuddy 开发对话上下文 · workbuddy.md

> 本文记录使用 **WorkBuddy** 开发「麦麦战绩 McProfile」过程中的关键对话与决策，
> 用于核验是否符合 WorkBuddy 联动活动奖励条件。

> ⚠️ **仓库形态说明（2026-10-12）**：本仓库为「纯 Skill 包」——产品源代码是
> `SKILL.md` 单文件（宿主 agent 照其指令直接调官方 `mcd-mcp` 完成全部功能）。
> 早期开发的本地实现（`src/` / `tests/` / `data/`）、CLI（`src/cli.py` / `menu_view.py`）
> 与离线落地页（`site/`）、样例产物（`examples/`）均已移除，不依赖任何脚本或本地代码。
> 对外使用方式只有 Skill（见 `README.md`）。
> 下文「可复现的验证命令」中 `python -m src.cli ...` 属开发历史，当前仓库不提供 CLI。

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
   - 决策：**避开红海，做「订单后复盘」这一白地**——即「麦麦战绩」。

3. **数据侦察（真实联调）**
   - `order-list` → 实测返回 **10 条真实历史订单**，字段含
     `orderId / createTime / storeName / orderStatus / realTotalAmount` 与
     `orderProductList[].comboItemList[]`（套餐成分拆解）。
   - `query-my-account` → 积分账户（可用 1320.1 / 累计 34703.1）。
   - `query-my-coupons` / `query-my-prizes` / `mall-order-list` → 券、奖品、商城订单均可用。
   - 进一步把订单域扩展到 **权益 / 商城 / 场景 / 营销 / 营养**（合订单共六域），合计锁定
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
   - `src/cli.py`：命令行入口，共 16 个子命令（archive / orders / savings / account / campaign / store / tools / card / demo / brief / **doctor** / stores / menu / eat / **preheat** / **solve**）。

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
     （`src/menu_view.py` / `menu` 子命令）——菜单（样例数据 47 款）商品图+价+折扣、类目筛选、搜索、点选购物车，
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
| **方向复盘（第二轮）** | 用户提「不够酷、玩不出花样」→ 复看竞品情报，指出 70% 挤在省钱+营养且价格多为估算；给出差异化方案：**把 `calculate-price` 当价格预言机**（McSolve）+ 活动×券冲突（McPreheat） |
| **算法联调** | 实测券面文案反推规则（满减/折扣/免费/买一送一/件数折扣含中文数字）、修正目标函数退化、并发验价与保序、失败披露 |
| **文案在环 + 护栏** | 95 条硬编码文案外置为文本键；端到端实测揪出两处**静默放行**（未知键不报、labels 不查数值）并补齐三道护栏与渲染级回退 |
| **发布上线** | 生成零门槛落地页（`site/`）并发布为在线链接 https://mcsolve.app.workbuddy.host/ |

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

### v2.0 新增（可离线复现，无需 Token）

```bash
# 吃之前：最优解（全程只读，不产生订单）
python -m src.cli --offline solve --items 板烧鸡腿堡 巨无霸 --top 30
# 吃之前：活动倒计时 + 券到期冲突 + 备战度
python -m src.cli --offline preheat

# 文案在环（三个场景分别导出素材）
python -m src.cli --offline brief --for solve      # 或 --for preheat / --for archive
python -m src.cli --offline solve --items 板烧鸡腿堡 --copy copy_pack_solve.json
#   → 键名写错 / 丢占位符 / 编数字 三类错误会被逐条打印并自动回退默认文案

# 全量测试（103 项）
python -m pytest tests/ -q
```

在线体验（免登录）：https://mcsolve.app.workbuddy.host/

## 四点五、第二轮起：从「吃之后」扩展到「吃之前 → 吃之后」完整闭环

> 第一轮交付的是 `archive`（吃之后的复盘）。用户随后提出「总觉得不够酷、玩不出花样」
> 「要差异化竞争，发力点放在麦当劳 MCP 提供的工具上」，WorkBuddy 据此做了四轮迭代，
> 最终把产品从**单点复盘**扩展成**闭环**，并以 `solve` / `preheat` 为招牌（v2.0）。

### 1. 方向选择：避开红海，且用「只有 MCP 能给」的能力

- 复看 33 个在册作品：**70% 挤在「省钱」+「营养」**，且价格大多是**按菜单价估算**。
- 决策：**不比谁的建议更像人话，而比谁的价格是真的**——全场只有 `calculate-price`
  能给出**真实实付价**，而它是**免费、只读、不产生订单、可无限次调用**的。
- 于是把它从「下单前的最后一步」重新定位为**「价格预言机 / 模拟器」**（McSolve）：
  本地穷举 → 剪枝排序 → 只对 Top N 调官方验价 → 取**官方认证**的最优解。
- 第二条钩子来自 `campaign-calendar` × `query-my-coupons` 的交叉：**有些券等不到活动那天**。

### 2. McSolve 的关键工程决策（均由 WorkBuddy 实测后修正）

| 问题 | 修法 |
|---|---|
| 目标函数退化成「劝人只点 1 件」 | 主指标改为**省钱率**（`discount/original`），同率时取实付更低者 |
| 中文数字「三」（三件任选6折）解析不到 | 券规则正则支持中文数字 |
| 「买一送一」无条件下发折扣 | 必须组合含该商品且 `count >= 2` 才生效 |
| 组合爆炸 | `--add` 硬上限 4、`MAX_ENUM=20000`；超限**整层收敛**而非半层截断（结果无偏） |
| 进度回调打错字段 | 传 `paid` 而非 `discount`（此前终端恒显示 ¥0.00） |
| 「省了钱却要多掏」看着像自相矛盾 | 保留两份口径并加**口径说明**：折扣力度相对原价，多花多得相对直觉点法 |
| 验价失败 | 如实披露 `fail_count`，**不谎称「没有解」** |

### 3. McPreheat 的关键工程决策

| 问题 | 修法 |
|---|---|
| 倒计时恒为 0 | 严格取**未来**日期；**不信任 `stage` 字段**（实测不可靠） |
| 有冲突券却评 S | 重配权重：miss −25 / urgent −10 / 当天无券 −20，加分仅 +5（扣分压得住加分） |
| 日期解析不出就说「没有活动」 | 新增 `unparsed_count` **披露**，明确说「拿到了 N 条，但日期格式未能解析」 |
| 临期券口径混淆 | 「即将到期（7 天内）」与 `account` 的「30 天内到期」各自标注，不强行统一 |

### 4. 文案层：把硬编码文字全部交还给 WorkBuddy

- 用户要求「文案不要代码写死，充分利用大模型的能力」，于是把 solve / preheat 的硬编码文案**全量外置**到 `src/textpack.py` 的 `TEXT_REGISTRY`
  （`sv.*` 53 键 / `ph.*` 67 键），并新增 `brief --for archive|solve|preheat` 导出素材。
- 原则：**模型只改文字，数值永不出自模型**。
- 但端到端实测发现护栏有两个**静默放行**的洞，已补齐为三道（出错条目**真回退**默认文案）：
  1. 键名写错（`sv.hero_title`）→ 静默失效无提示 → 现在告警 + 用编辑距离**猜相近键**；
  2. 数值泄漏**只查自由文本、不查 `labels`**（而 labels 才是主战场）→ 统一口径；
  3. 顶层字段名拼错（`solve.grad_word`）→ 静默失效 → 现在告警。
- 新增 `CopyPack.bind_facts()` + **两阶段校验**：solve 算完传真实 facts；
  preheat / archive 用 `_post_check_numbers()` 在算完后二次校验。
- 顺带补功能缺口：`_str_map` 曾**吞掉 dict**，导致 S/A/B/C 四档评级词只能写一个通用词 →
  新增 `pick_grade_word()`，支持 `{"S":…,"A":…}` 映射写法。

### 5. 落地与交付

- `site/index.html`：**零门槛落地页**，免登录免 Token 即可玩求解器与实时倒计时；
  用 `tests/test_site_parity.py`（抽取页面内联 JS 与 Python 比对）防止两份实现漂移。
- 已发布上线：**https://mcsolve.app.workbuddy.host/**
- 测试从 59 → 119 项，全绿；`git` 已推送到 `dengbin21/mcd-profile`。

### 6. 首用体验：让「没 Token」不再是一行 403

- 用户问「别人装好这个 Skill 后怎么用」时描述的预期是：**没 Token 就提示去配，有 Token 直接走点餐**。
  实测发现当时完全不是这么回事——没配 Token 时 mcd-mcp 只回 `403 Forbidden`，
  既不说明缺什么，也不说去哪申请、填到哪里。这是「产品能不能被别人用起来」的硬门槛。
- CLI 侧：
  - 新增 `doctor` 子命令（环境自检）：Token 找没找到 + **从哪个文件找到的** + 连不连得上 +
    依赖的 20 个只读工具缺哪几个；Token 只显示首尾各 4 位，输出可安全贴进 issue。
  - `McpAuthError` 单独成类：401/403 翻译成「申请/续期 Token + 跑 doctor」；
    其余 HTTP 错误保持原样——不为「友好」掩盖真实问题（500 就是 500）。
  - `main()` 前置检查：联网命令无 Token 时打印「去哪申请 / 填到哪 / 怎么自检」并退出码 2。
- Skill 侧：`SKILL.md` 补「没连上时怎么引导用户」——**先自检再决定走玩法还是引导配置**，
  明确禁止用历史数据或常识凑答案，也禁止在用户配置期间编造菜单与价格。
- 四个场景实测：无 Token / Token 无效（401）/ 本机真实 Token（35 个工具，20 个依赖全在）/ 离线自检。
- 测试 112 → 119（新增 7 项首用体验测试）。

### 7. 真实数据验收：预热台被官方接口打了三次脸

用「我要吃麦当劳」这条真实链路跑通预热台时（`doctor` → 选店 → `preheat`），
拿本机真实券包一比对，发现卡片上的结论是错的——三处都是**只在真实数据上才会暴露**的问题：

1. **区间到期被误判为已过期（P0）**：`query-my-coupons` 的 `availableTime` 返回
   `2026.10.05-2026.10.11`，解析器只取前三个数字段 → 当成 10-05 到期。
   于是这张**明天才到期、正好撑得到活动**的券被写成「已过期、等不到那天」，
   备战度还被白扣 25 分。修法：新增 `parse_until()` 把区间**分段抠全并取结束日**，
   活动日期仍用 `parse_when()` 取开始日——两处语义不同，不能共用一种取法。
2. **「今日」到期的券静默消失（P1）**：官方把今天到期的券写成「今日」，解析失败后
   不进任何清单——最紧急的一张券从卡片上人间蒸发。修法：认「今日/今天」，
   其余读不懂的标 `unparsed` 并新增 `coupon_unparsed_count` 计数披露。
3. **备战度语义被算反（P1）**：临期券每张 -10 且不封顶 → 手里 10 张券（9 张临期）
   直接扣到 0 分「裸奔进场，建议先清券」，可这人恰恰是全场弹药最足的。
   修法：`URGENT_CAP = 3`，临期扣分封顶。修完从 C(0/100) 变成 B(55/100)。

顺带收敛两处一致性：`analysis._parse_expire` 原本用 `re.search` 取第一处（同一个区间坑），
改为复用 `parse_until`，避免「同一张券在档案里已过期、在预热台里还活着」；
「能撑到活动当天」清单不再把压线券抄第二遍（活动只剩 1 天时两节 10/10 完全重叠），
改为只列真正安全的 + 注明「另有 N 张压线券」。

- 落地页 `site/index.html` 里**独立实现了一份**预热台（`pd` 抄的是旧解析器、评分也没封顶），
  已同步改成 `pdAll/pd/pu` 三件套 + `URGENT_CAP`；并在 `test_site_parity.py` 新增
  `test_site_date_parsing_matches_python`，把 JS 的 `pd/pu` 与 Python 的
  `parse_when/parse_until` 对 **10 种日期写法**逐条比对——同一份页面数据喂给两边。
  已反向验证过这道护栏有效：故意把 `pu` 改回取首段，测试立刻红。
- 测试 126 → 133（新增 7 项回归：区间取结束日、今日到期可见、读不懂要披露、
  临期扣分封顶、存活清单不重复、页面日期解析同口径；MD 与 HTML 同口径也一并断言）。

## 五、小结

本项目从「配置 MCP」→「情报分析选方向」→「可跑通的参赛作品」→「闭环 + 上线」，
全流程在 WorkBuddy 中完成，包含对 MCP 35 个工具的实测、对 33 个竞品的情报分析、
真实接口联调与多次工程修正，以及把硬编码文案交还模型（`brief` → `copy_pack` → `--copy`）
并加三道护栏的完整设计，属于 WorkBuddy 深度参与创作的原创作品。
