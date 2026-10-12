"""文案层（WorkBuddy 在环）：把「结构化事实」交给模型写文案，再回填渲染。

> 模块原名 ``copy.py``，因会遮蔽标准库 ``copy``（``dataclasses`` 内部
> ``import copy`` 会误命中本文件）而更名为 ``textpack``；对外接口不变。

设计动机
--------
档案的**视觉结构**是规则驱动的（主题配色 / 徽章触发 / 雷达打分），保证稳定、可复现；
但**文字表达**若全用固定句式，不同用户会「撞脸」。于是把文案抽成一层：

- 默认（无 ``CopyPack``）：走规则模板（``TEXT_REGISTRY`` 默认值 / ``theme.build_quips`` /
  ``report.build_advice``）；
- 在环（``--copy copy_pack.json``）：由 **WorkBuddy（宿主 agent）** 读取
  ``build_copy_brief()`` 导出的素材，生成**全部文字**后注入，覆盖规则模板。

覆盖范围（**除数值外的全部文字**）
------------------------------
1. **表达性文案**：人格称号 / 标题句 / 标语 / 标签 / 金句 / 建议 / 徽章描述 / CTA；
2. **结构与指标文字**（``labels``）：全部区块标题、指标名、KPI 名、表头、页脚、元信息行；
3. **动态名称**：雷达维度名（``radar``）、徽章名（``badge_title``）。

> **数值永不出自模型**：所有数字由规则计算；``labels`` 里的 ``{占位符}`` 由程序填充，
> 模型只改文字、必须保留占位符。
>
> **不需要任何外部模型 Key**——写文案的「模型」就是运行本作品的 WorkBuddy 本体。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # noqa: F401 —— 仅用于类型标注
    from .archive import Archive


# ====================================================================== #
# 文本注册表：所有「可由模型覆写」的**文字**的单一事实源。
#   key 约定：
#     "sec.*"  区块 / 卡片标题
#     "lbl.*"  指标名 / KPI 名 / 表头 / 元信息 / 行内短语
#     "ft.*"   页脚
#     "cta"    默认号召语
#   default 中可含 {占位符}，渲染时由规则数值填充（**数值永不出自模型**）。
# ====================================================================== #
TEXT_REGISTRY: dict[str, dict[str, str]] = {
    # ---- 品牌 / 标题 ----
    "brand": {"default": "麦当劳 MCP · 麦麦战绩", "desc": "卡片顶部品牌行"},
    "sec.md_title": {"default": "麦麦战绩 · McProfile", "desc": "Markdown 文档主标题"},
    "sec.persona": {"default": "你的麦门人格", "desc": "人格区块标题"},
    "sec.report": {"default": "本次点餐战报", "desc": "点餐战报区块标题"},
    "sec.badges": {"default": "成就徽章墙", "desc": "徽章墙区块标题"},
    "sec.quips": {"default": "麦门金句", "desc": "金句区块标题"},
    "sec.consumption": {"default": "消费画像", "desc": "消费画像标题"},
    "sec.savings": {"default": "省钱画像", "desc": "省钱画像标题"},
    "sec.health": {"default": "健康画像", "desc": "健康画像标题"},
    "sec.habit": {"default": "习惯画像", "desc": "习惯画像标题"},
    "sec.benefit": {"default": "权益画像", "desc": "权益画像标题"},
    "sec.activity": {"default": "近期活动（官方活动日历）", "desc": "活动日历标题"},
    "sec.stores": {"default": "门店与地址", "desc": "门店足迹标题"},
    "sec.mcp": {"default": "MCP 工具覆盖清单", "desc": "工具覆盖清单标题"},
    "sec.advice": {"default": "下个月的小建议", "desc": "建议区块标题"},
    "sec.radar": {"default": "麦门战力雷达", "desc": "雷达区块标题"},
    "sec.health_benefit": {"default": "健康 & 权益", "desc": "卡片健康&权益标题"},
    "sec.taste": {"default": "口味偏好与门店足迹", "desc": "卡片口味足迹标题"},
    "sec.savings_hl": {"default": "省钱亮点", "desc": "卡片省钱亮点标题"},
    "sec.mcp_cap": {"default": "MCP 能力覆盖", "desc": "卡片能力覆盖标题"},
    "cta": {"default": "🍟 我也要一份我的麦麦战绩", "desc": "底部号召语（cta 字段缺省时用）"},

    # ---- 元信息 ----
    "lbl.theme_name": {"default": "", "desc": "主题显示名（留空则用规则主题名）"},
    "lbl.meta_line": {"default": "主题：**{theme}**　|　本次调用 **{n}** 个官方工具　|　"
                                 "共 **{m}** 笔历史订单　|　区间 **{start} ~ {end}**",
                      "desc": "Markdown 顶部元信息行"},
    "lbl.html_meta": {"default": "{start} ~ {end}　·　{n} 单　·　数据来自 mcd-mcp",
                      "desc": "卡片日期/单量小结"},
    "lbl.date_range": {"default": "{start} ~ {end}", "desc": "日期区间（PNG 头部）"},
    "lbl.tags": {"default": "标签", "desc": "标签行前缀"},

    # ---- 表格表头 ----
    "lbl.tbl_metric": {"default": "指标", "desc": "表头：指标"},
    "lbl.tbl_value": {"default": "数值", "desc": "表头：数值"},
    "lbl.tbl_item": {"default": "餐品", "desc": "表头：餐品"},
    "lbl.tbl_qty": {"default": "数量", "desc": "表头：数量"},
    "lbl.tbl_cumulative": {"default": "累计", "desc": "表头：累计"},
    "lbl.tbl_daily": {"default": "折合每日参考值", "desc": "表头：每日参考值"},
    "lbl.tbl_tool": {"default": "MCP 工具", "desc": "表头：工具名"},
    "lbl.tbl_usage": {"default": "用途", "desc": "表头：工具用途"},
    "lbl.tbl_status": {"default": "状态", "desc": "表头：状态"},
    "lbl.tbl_out": {"default": "本次产出", "desc": "表头：本次产出"},

    # ---- 点餐战报 ----
    "lbl.report_done": {"default": "已真实下单", "desc": "战报状态：已下单"},
    "lbl.report_preview": {"default": "算价预览", "desc": "战报状态：预览"},
    "lbl.report_paid": {"default": "本单实付", "desc": "战报指标：实付"},
    "lbl.report_saved": {"default": "本单省下", "desc": "战报指标：省下"},
    "lbl.report_kcal_unit": {"default": "本单热量 kcal", "desc": "战报指标：热量（卡片）"},
    "lbl.report_order_no": {"default": "订单号", "desc": "战报：订单号前缀"},
    "lbl.report_placed_note": {"default": "✅ **已真实下单**：订单号 `{oid}`（{status}），"
                                          "可凭此号在官方渠道查询/取消。",
                               "desc": "Markdown 已下单说明"},
    "lbl.report_preview_note": {"default": "🧾 本战报为**算价预览**（未真实下单）。",
                                "desc": "Markdown 预览说明"},

    # ---- KPI 卡 ----
    "lbl.kpi_spend": {"default": "累计消费", "desc": "KPI：累计消费"},
    "lbl.kpi_save": {"default": "累计省下", "desc": "KPI：累计省下"},
    "lbl.kpi_save_rate": {"default": "累计省下 · {rate}%", "desc": "KPI：累计省下(含比例)"},
    "lbl.kpi_orders": {"default": "麦当劳订单", "desc": "KPI：订单数（卡片）"},
    "lbl.kpi_order_cnt": {"default": "订单数", "desc": "KPI：订单数（PNG）"},
    "lbl.kpi_avg": {"default": "平均客单", "desc": "KPI：平均客单"},
    "lbl.kpi_bigmac": {"default": "≈巨无霸", "desc": "KPI：巨无霸折算"},
    "lbl.kpi_kcal": {"default": "累计热量", "desc": "KPI：累计热量"},
    "lbl.kpi_point": {"default": "可用积分", "desc": "KPI：可用积分"},

    # ---- 消费画像 ----
    "lbl.total_spend": {"default": "累计消费", "desc": "消费：累计消费"},
    "lbl.orders": {"default": "有效订单", "desc": "消费：有效订单"},
    "lbl.orders_note": {"default": "{n} 单（另有 {r} 单退款）", "desc": "消费：订单数说明"},
    "lbl.avg_ticket": {"default": "平均客单价", "desc": "消费：平均客单价"},
    "lbl.max_order": {"default": "最贵一单", "desc": "消费：最贵一单"},
    "lbl.min_order": {"default": "最省一单", "desc": "消费：最省一单"},
    "lbl.fav_store": {"default": "最爱门店", "desc": "消费：最爱门店"},
    "lbl.fav_item": {"default": "复购最多", "desc": "消费：复购最多"},
    "lbl.slots": {"default": "时段分布", "desc": "消费：时段分布"},
    "lbl.top5": {"default": "常点 TOP5", "desc": "消费：常点 TOP5"},
    "lbl.reorder_quote": {
        "default": "再来一单：{name} 官方现价 ¥{paid}（原价 ¥{orig}）",
        "desc": "消费：常点单品的官方算价（calculate-price 产出，非估算）",
    },

    # ---- 省钱画像 ----
    "lbl.total_original": {"default": "累计原价", "desc": "省钱：累计原价"},
    "lbl.total_paid_m": {"default": "累计实付", "desc": "省钱：累计实付"},
    "lbl.total_discount": {"default": "累计省下", "desc": "省钱：累计省下"},
    "lbl.discount_rate": {"default": "省钱率", "desc": "省钱：省钱率"},
    "lbl.coupon_used": {"default": "用券次数", "desc": "省钱：用券次数"},
    "lbl.coupon_top": {"default": "最常用券", "desc": "省钱：最常用券"},
    "lbl.best_deal_m": {"default": "最划算一单", "desc": "省钱：最划算一单"},
    "lbl.savings_note": {"default": "以上基于 {a}/{b} 笔订单的优惠明细（其余订单官方未返回明细）。",
                         "desc": "省钱：口径说明"},

    # ---- 健康画像 ----
    "lbl.health_cov": {"default": "营养映射覆盖率 **{cov}%**（未收录的新品/周边不计入）；"
                                 "覆盖 **{days}** 个消费日。",
                       "desc": "健康：覆盖率说明"},
    "lbl.kcal": {"default": "热量", "desc": "健康：热量"},
    "lbl.protein": {"default": "蛋白质", "desc": "健康：蛋白质"},
    "lbl.fat": {"default": "脂肪", "desc": "健康：脂肪"},
    "lbl.carb": {"default": "碳水", "desc": "健康：碳水"},
    "lbl.sodium": {"default": "钠", "desc": "健康：钠"},
    "lbl.bigmac_line": {"default": "**≈ {n} 个巨无霸的热量。** 平均每单 {k} kcal、钠 {na} mg。",
                        "desc": "健康：巨无霸折算句"},
    "lbl.lights_md": {"default": "红黄绿灯：🟢 {g} 单　🟡 {y} 单　🔴 {r} 单",
                      "desc": "健康：红黄绿灯（MD）"},
    "lbl.lights_png": {"default": "绿灯 {g}    黄灯 {y}    红灯 {r}",
                       "desc": "健康：红黄绿灯（PNG）"},
    "lbl.lights_note": {"default": "（单餐红黄绿灯）", "desc": "健康：灯注（卡片）"},
    "lbl.lights_note_png": {"default": "单餐红黄绿灯", "desc": "健康：灯注（PNG）"},
    "lbl.sodium_top": {"default": "钠含量 TOP", "desc": "健康：钠含量 TOP"},

    # ---- 习惯画像 ----
    "lbl.frequent": {"default": "官方「我的常点」", "desc": "习惯：官方常点"},
    "lbl.peak_slot": {"default": "最活跃时段", "desc": "习惯：最活跃时段"},
    "lbl.weekday": {"default": "消费星期分布", "desc": "习惯：星期分布"},
    "lbl.avg_items": {"default": "单均商品", "desc": "习惯：单均商品"},
    "lbl.span": {"default": "消费跨度", "desc": "习惯：消费跨度"},
    "lbl.menu_size": {
        "default": "最爱门店在售 {n} 款（{tagged} 款带官方标签）",
        "desc": "习惯：最爱门店菜单规模（query-meals 产出）",
    },

    # ---- 权益画像 ----
    "lbl.available_point": {"default": "可用积分", "desc": "权益：可用积分"},
    "lbl.point_acc_used": {"default": "累计获得 / 已用", "desc": "权益：积分累计/已用"},
    "lbl.coupon_count": {"default": "手持券", "desc": "权益：手持券"},
    "lbl.expiring": {"default": "⚠️ 30 天内到期", "desc": "权益：临期券"},
    "lbl.store_coupon": {"default": "最爱门店可用券", "desc": "权益：门店可用券"},
    "lbl.available_coupon": {"default": "麦麦省可领券", "desc": "权益：可领券"},
    "lbl.mall_orders": {"default": "积分商城订单", "desc": "权益：商城订单"},
    "lbl.prize": {"default": "抽奖奖品", "desc": "权益：抽奖奖品"},
    "lbl.lottery": {"default": "积分抽奖", "desc": "权益：积分抽奖"},
    "lbl.redeem": {"default": "积分可兑换", "desc": "权益：积分可兑换"},

    # ---- 活动 / 门店 ----
    "lbl.activity_now": {"default": "今日进行中：", "desc": "活动：今日进行中"},
    "lbl.activity_upcoming": {"default": "即将到来：", "desc": "活动：即将到来"},
    "lbl.stores_nearby": {"default": "相关门店（{n} 家）：", "desc": "门店：相关门店"},
    "lbl.addresses": {"default": "外送地址：", "desc": "门店：外送地址"},

    # ---- MCP 工具覆盖 ----
    "lbl.mcp_summary": {"default": "本次共调用 **{n}** 个官方 MCP 工具（成功 {ok} 个）。",
                        "desc": "MCP：汇总句"},
    "lbl.mcp_offline": {"default": "当前离线演示模式，未实时调用 MCP。联网运行时会调用：",
                        "desc": "MCP：离线说明"},
    "lbl.mcp_line_png": {"default": "本次调用 {n} 个官方工具 · 成功 {ok} 个 · "
                                    "覆盖订单 / 权益 / 商城 / 门店 / 营养 / 点餐 六大域",
                         "desc": "MCP：能力覆盖句（PNG）"},
    "lbl.mcp_offline_png": {"default": "离线演示模式（未实时调用 MCP）· 联网后可覆盖 "
                                       "订单 / 权益 / 商城 / 门店 / 营养 / 点餐 六大域",
                            "desc": "MCP：离线能力句（PNG）"},

    # ---- 卡片 KV 行 ----
    "lbl.kv_kcal": {"default": "累计热量", "desc": "卡片KV：累计热量"},
    "lbl.kv_bigmac": {"default": "≈", "desc": "卡片KV：巨无霸前缀"},
    "lbl.kv_sodium": {"default": "累计钠", "desc": "卡片KV：累计钠"},
    "lbl.kv_expiring": {"default": "临期券", "desc": "卡片KV：临期券"},
    "lbl.kv_frequent": {"default": "官方常点", "desc": "卡片KV：官方常点"},
    "lbl.kv_point": {"default": "可用积分", "desc": "卡片KV：可用积分"},
    "lbl.kv_coupon": {"default": "手持券", "desc": "卡片KV：手持券"},

    # ---- 卡片：口味足迹 / 省钱亮点 ----
    "lbl.taste_top": {"default": "常点 TOP", "desc": "卡片：常点 TOP"},
    "lbl.taste_store": {"default": "常去门店", "desc": "卡片：常去门店"},
    "lbl.sav_total": {"default": "累计省下 ¥{amt}（{rate}%）", "desc": "卡片：省钱合计"},
    "lbl.sav_coupon": {"default": "用券 {n} 次", "desc": "卡片：用券次数"},
    "lbl.sav_best": {"default": "单笔最多省 ¥{amt}", "desc": "卡片：单笔最多省"},
    "lbl.sav_fav_coupon": {"default": "最爱券「{name}」", "desc": "卡片：最爱券"},

    # ---- 页脚 ----
    "ft.produced": {"default": "由麦麦战绩 McProfile 生成", "desc": "页脚：生成来源"},
    "ft.tools": {"default": "本次调用 {n} 个官方 MCP 工具", "desc": "页脚：工具调用"},
    "ft.offline": {"default": "离线演示模式", "desc": "页脚：离线模式"},
    "ft.line1": {"default": "{tools} · 仅供个人复盘，不构成医疗/营养建议",
                 "desc": "页脚第一行（PNG）"},
    "ft.line2": {"default": "麦麦战绩 McProfile · 基于麦当劳官方 MCP 生成",
                 "desc": "页脚第二行（PNG）"},
    "ft.disclaimer_short": {"default": "仅供个人复盘，不构成营养或医疗建议",
                            "desc": "卡片免责声明（短）"},
    "ft.disclaimer": {"default": "本档案由「麦麦战绩 McProfile」基于麦当劳官方 MCP 生成，"
                                "仅供个人复盘参考，不构成医疗或营养建议；"
                                "餐品与价格以麦当劳官方渠道为准。",
                      "desc": "Markdown 免责声明（长）"},

    # ================================================================== #
    # 麦麦最优解 · McSolve（sv.*）
    # ================================================================== #
    "sv.md_title": {"default": "麦麦最优解 · McSolve", "desc": "Markdown 主标题"},
    "sv.kicker": {"default": "麦麦最优解", "desc": "卡片顶部小标"},
    "sv.sub": {"default": "官方接口验过价的最低组合", "desc": "卡片副标题"},
    "sv.no_solution": {"default": "本次没有求出可行组合，试试放宽预算或减少必选商品。",
                       "desc": "无解提示（MD）"},
    "sv.no_solution_html": {"default": "没有求出可行组合", "desc": "无解提示（HTML）"},
    "sv.grade_line": {"default": "评级 **{grade}** —— {word}", "desc": "评级行（MD）"},
    "sv.store_line": {"default": "门店：{store}", "desc": "门店行（MD）"},
    "sv.sec_solution": {"default": "最优解", "desc": "区块：最优解"},
    "sv.sec_items": {"default": "这一单点什么", "desc": "区块：本单餐品"},
    "sv.sec_vs": {"default": "你的直觉点法 vs 算法最优解", "desc": "区块：人机对比"},
    "sv.sec_process": {"default": "求解过程", "desc": "区块：求解过程"},
    "sv.sec_rules": {"default": "参考的券规则", "desc": "区块：券规则"},
    "sv.sec_nutrition": {"default": "这一单的营养", "desc": "区块：营养"},
    "sv.lbl_original": {"default": "原价", "desc": "指标：原价"},
    "sv.lbl_paid": {"default": "实付", "desc": "指标：实付"},
    "sv.lbl_discount": {"default": "官方优惠", "desc": "指标：官方优惠"},
    "sv.discount_note": {"default": "¥{discount}（省钱率 {rate}%）", "desc": "省钱率说明"},
    "sv.lbl_count": {"default": "件数", "desc": "表头：件数"},
    "sv.lbl_pay": {"default": "实付", "desc": "表头：实付"},
    "sv.lbl_avg": {"default": "均价", "desc": "表头：均价"},
    "sv.lbl_baseline": {"default": "直觉点法", "desc": "对比：直觉点法"},
    "sv.lbl_best": {"default": "算法最优解", "desc": "对比：算法最优解"},
    "sv.vs_baseline_col": {"default": "直觉点法 · {n} 件", "desc": "对比列头：直觉点法"},
    "sv.vs_best_col": {"default": "算法最优解 · {n} 件", "desc": "对比列头：最优解"},
    "sv.vs_avg_line": {"default": "均价 ¥{avg}", "desc": "对比列：均价"},
    "sv.vs_save": {"default": "同样的东西，白省 ¥{saved}", "desc": "结论：白省"},
    "sv.vs_more": {"default": "多花 ¥{extra}，多得 {n} 件，均价从 ¥{a} 降到 ¥{b}"
                             "（降 {drop}%）",
                   "desc": "结论：多花多得"},
    "sv.vs_more_html": {"default": "多花 ¥{extra}，多得 {n} 件<br>单件均价直降 {drop}%",
                        "desc": "结论：多花多得（HTML）"},
    "sv.vs_note": {"default": "口径：上面的「省钱率」是相对原价；这里的多花 ¥{extra} "
                              "是相对「只点必选」的实付。两者量纲不同——多掏一点钱，换回更多件。",
                   "desc": "量纲口径说明（MD）"},
    "sv.vs_note_html": {"default": "口径：上方「省钱率」是相对原价；这里的多花 ¥{extra} "
                                  "是相对「只点必选」的实付。量纲不同——多掏一点，换回更多件。",
                        "desc": "量纲口径说明（HTML）"},
    "sv.enum_line": {"default": "本地枚举候选：**{n}** 种", "desc": "求解：枚举数"},
    "sv.valid_line": {"default": "其中通过预算：**{n}** 种", "desc": "求解：通过预算"},
    "sv.kcal_line": {"default": "热量约束：≤ **{kcal} kcal**（按营养库匹配，覆盖见营养区块）",
                     "desc": "求解：热量上限"},
    "sv.kcal_line_html": {"default": "热量约束 ≤ {kcal} kcal（按营养库匹配，覆盖见下方营养区块）",
                          "desc": "求解：热量上限（HTML）"},
    "sv.verify_line": {"default": "官方 `calculate-price` 验价：**{n}** 次（成功 {ok}）",
                       "desc": "求解：验价次数"},
    "sv.fail_line": {"default": "⚠️ 其中 **{n}** 次验价失败（网络或接口异常），已跳过——"
                               "**最优解是在成功验价的组合里挑出来的**",
                     "desc": "求解：验价失败披露"},
    "sv.final_note": {"default": "最终价格以官方验价为准，本地估算只用于排序",
                      "desc": "求解：最终口径"},
    "sv.voucher_note": {"default": "口径：券的核销通常需要「券绑定的凭证商品码」，而官方卡包接口未返回该字段，"
                                   "故本次验价以官方按账号自动匹配的券价为准；若实付与你预期的券后价不符，"
                                   "请先在官方 App 确认该券可用的门店与商品。",
                        "desc": "券凭证码风险披露（MD）"},
    "sv.voucher_note_html": {"default": "口径：券的核销通常需要「券绑定的凭证商品码」（官方卡包接口未返回），"
                                        "验价以官方按账号自动匹配的券价为准；实付与券后价不符时，请到官方 App 确认券可用门店与商品。",
                             "desc": "券凭证码风险披露（HTML）"},
    "sv.fail_note_html": {"default": "有 {n} 次官方验价失败已跳过，"
                                    "最优解是在成功验价的组合中选出的。",
                          "desc": "求解：验价失败披露（HTML）"},
    "sv.rules_unknown": {"default": "另有 {n} 张券无法自动解析", "desc": "券：无法解析"},
    "sv.nut_kcal": {"default": "热量 **{kcal} kcal**", "desc": "营养：热量"},
    "sv.nut_line": {"default": "蛋白 {p} g ｜ 脂肪 {f} g ｜ 钠 {na} mg", "desc": "营养：三项"},
    "sv.nut_per_yuan": {"default": "每元热量 **{v} kcal/¥**（这单的「性价比」）",
                        "desc": "营养：每元热量"},
    "sv.nut_cov": {"default": "营养映射覆盖 {m}/{t} 件", "desc": "营养：覆盖率"},
    "sv.lbl_kcal_unit": {"default": "千卡", "desc": "营养卡：千卡"},
    "sv.lbl_protein": {"default": "蛋白", "desc": "营养卡：蛋白"},
    "sv.lbl_fat": {"default": "脂肪", "desc": "营养卡：脂肪"},
    "sv.lbl_sodium": {"default": "钠", "desc": "营养卡：钠"},
    "sv.stat_enum": {"default": "本地枚举<br>候选组合", "desc": "统计：枚举"},
    "sv.stat_verify": {"default": "官方验价<br>calculate-price", "desc": "统计：验价"},
    "sv.stat_rate": {"default": "省钱率", "desc": "统计：省钱率"},
    "sv.demo_foot": {"default": "演示模式：价格为脱敏样例数据的本地估算，非官方实时报价；"
                                "联网后由官方 `calculate-price` 逐单验价，全程只读、不产生订单",
                     "desc": "离线口径（MD）：替换 foot_price，避免「本地估算」与「来自官方」并排矛盾"},
    "sv.demo_foot_html": {"default": "演示模式：价格为脱敏样例数据的本地估算，非官方实时报价；"
                                    "联网后由官方 <code>calculate-price</code> 逐单验价，全程只读、不产生订单",
                         "desc": "离线口径（HTML）"},
    "sv.foot_price": {"default": "价格来自麦当劳官方 MCP `calculate-price`，"
                                "全程只读、不产生订单", "desc": "页脚：价格来源"},
    "sv.foot_price_html": {"default": "价格来自麦当劳官方 MCP <code>calculate-price</code>，"
                                     "全程只读、不产生订单", "desc": "页脚：价格来源（HTML）"},
    "sv.foot_nutrition": {"default": "营养值仅供复盘参考，不构成营养建议", "desc": "页脚：营养"},
    "sv.cta": {"default": "我也想算算我的 → {repo}", "desc": "页脚号召语（HTML）"},
    "sv.cta_md": {"default": "也想算算你的？ {repo}", "desc": "页脚号召语（MD）"},

    # ================================================================== #
    # 麦麦预热台 · McPreheat（ph.*）
    # ================================================================== #
    "ph.md_title": {"default": "麦麦预热台 · McPreheat", "desc": "Markdown 主标题"},
    "ph.kicker": {"default": "麦麦预热台", "desc": "卡片顶部小标"},
    "ph.sec_running": {"default": "今天正在进行", "desc": "区块：今日进行中"},
    "ph.sec_conflict": {"default": "等不到那天的券", "desc": "区块：冲突券"},
    "ph.sec_surviving": {"default": "能撑到活动当天", "desc": "区块：存活券"},
    "ph.sec_urgent": {"default": "即将到期（{n} 天内）", "desc": "区块：临期券（含窗口天数）"},
    "ph.sec_score": {"default": "备战度", "desc": "区块：备战度"},
    "ph.sec_tips": {"default": "现在该做什么", "desc": "区块：行动建议"},
    "ph.tbl_coupon": {"default": "券", "desc": "表头：券"},
    "ph.tbl_expire": {"default": "到期", "desc": "表头：到期"},
    "ph.tbl_left": {"default": "距今", "desc": "表头：距今"},
    "ph.lbl_unit_day": {"default": "天", "desc": "倒计时单位"},
    "ph.lbl_expire_in": {"default": "{n} 天后", "desc": "券：到期倒计时"},
    "ph.lbl_expired": {"default": "已过期", "desc": "券：已过期"},
    "ph.lbl_dash": {"default": "—", "desc": "占位：无数据"},
    "ph.sec_countdown": {"default": "倒计时", "desc": "区块：倒计时"},
    "ph.sec_ammo": {"default": "弹药", "desc": "区块：积分弹药"},
    "ph.sec_later": {"default": "后面还有", "desc": "区块：后续活动"},
    "ph.lbl_target": {"default": "目标活动", "desc": "倒计时：目标活动"},
    "ph.lbl_date": {"default": "日期", "desc": "倒计时：日期"},
    "ph.lbl_left": {"default": "还有", "desc": "倒计时：还剩"},
    "ph.lbl_desc": {"default": "说明", "desc": "倒计时：活动说明"},
    "ph.lbl_today": {"default": "今天", "desc": "倒计时：就是今天"},
    "ph.no_target": {"default": "当前没有可预热的活动", "desc": "无预热对象（HTML）"},
    "ph.no_target_sub": {"default": "先把券包看住", "desc": "无预热对象副标题"},
    "ph.conflict_warn": {"default": "这些券会在活动开始前作废——先用掉，"
                                    "别留给一场赶不上的活动。",
                         "desc": "冲突券区块警示句"},
    "ph.ammo_line": {"default": "可用积分 **{points}**{tip}", "desc": "积分行（MD）"},
    "ph.ammo_redeem": {"default": "够兑换 **{n}** 件商品", "desc": "积分可兑（MD）"},
    "ph.ammo_floor": {"default": "，最低门槛 {floor} 分", "desc": "积分门槛后缀"},
    "ph.ammo_html": {"default": "可用积分 <b>{points}</b>{tip}", "desc": "积分行（HTML）"},
    "ph.ammo_redeem_html": {"default": "，够兑 <b>{n}</b> 件", "desc": "积分可兑（HTML）"},
    "ph.unparsed_note_full": {"default": "⚠️ 有 **{n}** 条活动的日期格式未能解析，未计入倒计时。"
                                         "活动本身没丢，完整列表见 `campaign` 命令。",
                              "desc": "日期解析失败披露（MD，完整）"},
    "ph.unparsed_note_html": {"default": "未计入倒计时。活动本身没丢，完整列表见 campaign 命令。",
                              "desc": "日期解析失败披露（HTML 后半句）"},
    "ph.coupon_unparsed_full": {"default": "⚠️ 有 **{n}** 张券的到期时间读不懂，未参与冲突判断"
                                           "——券还在你包里，麻烦自己看一眼。",
                                "desc": "券到期文案解析失败披露（MD）"},
    "ph.coupon_unparsed_html": {"default": "有 {n} 张券的到期时间读不懂，未参与冲突判断"
                                           "——券还在包里，自己看一眼。",
                                "desc": "券到期文案解析失败披露（HTML）"},
    "ph.surviving_note": {"default": "另有 {n} 张压线券（撑得到，但到期就在眼前），见上方临期清单。",
                          "desc": "存活清单：压线券已在上文列出，这里不重复"},
    "ph.foot_md": {"default": "口径：活动来自官方 `campaign-calendar`，券到期来自 "
                              "`query-my-coupons`，时间基准 `now-time-info`。"
                              "全程只读，不领券、不抽奖、不下单。",
                   "desc": "页脚口径（MD）"},
    "ph.lbl_press": {"default": "压线过关", "desc": "券：压线标记"},
    "ph.lbl_score": {"default": "{score}/100", "desc": "备战度分数"},
    "ph.lbl_data_time": {"default": "数据时间：{t}", "desc": "数据时间行（MD）"},
    "ph.unparsed_note": {"default": "⚠️ 有 {n} 条活动的日期格式未能解析，未参与倒计时计算。",
                         "desc": "日期解析失败披露"},
    # —— 钩子句式（**最能体现模型能力**：同一份事实，说法可以完全不同）——
    "ph.hook_conflict": {"default": "距「{title}」还有 {d} 天，但你有 {n} 张券等不到那天",
                         "desc": "钩子：有冲突"},
    "ph.hook_ready": {"default": "距「{title}」还有 {d} 天，券已就位", "desc": "钩子：临期已就位"},
    "ph.hook_plain": {"default": "距「{title}」还有 {d} 天", "desc": "钩子：常规倒计时"},
    "ph.hook_today": {"default": "「{title}」就是今天，冲", "desc": "钩子：就是今天"},
    "ph.hook_running": {"default": "「{title}」正在跑，暂时没有下一场可预热",
                        "desc": "钩子：有进行中无下一场"},
    "ph.hook_none": {"default": "当前没有可预热的活动，先看住你手里的券", "desc": "钩子：无活动"},
    "ph.hook_unparsed": {"default": "拿到 {n} 条活动，但日期格式未能解析，暂时算不出倒计时",
                         "desc": "钩子：日期读不懂"},
    # —— 行动建议句式（每条都基于算出来的事实，占位符由程序填）——
    "ph.tip_expired": {"default": "「{title}」已过期，别再惦记它了", "desc": "建议：已过期"},
    "ph.tip_missing": {"default": "「{title}」还剩 {n} 天到期，撑不到「{target}」——先用掉",
                       "desc": "建议：等不到活动"},
    "ph.tip_missing_today": {"default": "「{title}」今天到期，撑不到「{target}」——今天就用掉",
                             "desc": "建议：今天到期且赶不上活动"},
    "ph.tip_urgent": {"default": "「{title}」{n} 天内到期，别压箱底", "desc": "建议：临期"},
    "ph.tip_urgent_today": {"default": "「{title}」今天到期，别压箱底", "desc": "建议：今天到期"},
    "ph.tip_no_coupon": {"default": "活动当天你一张券都不剩，等于原价进场", "desc": "建议：当天无券"},
    "ph.tip_points": {"default": "积分 {points:g} 够兑 {n} 件商品，活动当天能当现金使",
                      "desc": "建议：积分可兑"},
    "ph.tip_running": {"default": "今天本来就有活动在进行：{titles}", "desc": "建议：今日有活动"},
    "ph.tip_healthy": {"default": "券包状态健康，等活动开跑直接上", "desc": "建议：状态健康"},
    "ph.cta": {"default": "我也想看看我的 → {repo}", "desc": "页脚号召语（HTML）"},
    "ph.cta_md": {"default": "也想看看你的？ {repo}", "desc": "页脚号召语（MD）"},
    "ph.foot_tools": {"default": "数据来自官方 MCP campaign-calendar / query-my-coupons / "
                                "now-time-info", "desc": "页脚：数据来源"},
    "ph.foot_disclaimer": {"default": "倒计时基于官方活动日历与券面到期时间推算，"
                                     "以麦当劳官方渠道为准", "desc": "页脚：免责"},
}


def text_defaults() -> dict[str, str]:
    """注册表所有 key -> 默认文字（供 WorkBuddy 参考/覆写）。"""
    return {k: v["default"] for k, v in TEXT_REGISTRY.items()}


class TextResolver:
    """按 CopyPack 覆写注册表文字；缺省回退默认；自动填充 ``{占位符}``。"""

    def __init__(self, copy: "CopyPack | None" = None):
        self.copy = copy

    def __call__(self, key: str, **kw) -> str:
        default = TEXT_REGISTRY.get(key, {}).get("default", "")
        t = default
        if self.copy is not None:
            ov = self.copy.labels.get(key)
            if ov:
                # 两道闸，任一不过就用默认文案：
                # 1) 少了占位符 → str.format 会静默忽略多余参数，数值凭空消失；
                # 2) 夹带了 facts 里没有的数字 → 那是模型编的，不能上卡片。
                # validate_copy_pack 负责说清楚原因，这里负责兜住结果。
                allowed = getattr(self.copy, "facts_numbers", None)
                ok = not missing_placeholders(key, ov) and not _leaked_numbers(ov, default, allowed)
                t = ov if ok else default
        try:
            return t.format(**kw)
        except Exception:  # 覆写模板占位符异常 → 回退默认，保证数值不丢
            try:
                return default.format(**kw)
            except Exception:
                return default


def _str_map(d) -> dict:
    """把 JSON 里的场景子块规整成 ``str -> str | list[str] | dict[str, str]``。

    ``grade_word`` 允许两种写法：整词字符串（所有评级用同一句）或
    ``{评级: 词}`` 映射（S/A/B/C 各写一句，没覆盖到的回退默认）。
    """
    if not isinstance(d, dict):
        return {}
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v]
        elif isinstance(v, dict):
            out[str(k)] = {str(a): str(b) for a, b in v.items()}
        elif isinstance(v, (str, int, float)):
            out[str(k)] = str(v)
    return out


def pick_grade_word(block: dict, grade: str) -> str:
    """从场景子块里取出该评级的词：支持「整词字符串」和「{评级: 词}」两种写法。"""
    ow = (block or {}).get("grade_word") or ""
    if isinstance(ow, dict):
        return str(ow.get(grade, "") or "")
    return str(ow or "")


@dataclass
class CopyPack:
    """一整套「可由模型覆写」的展示文案；留空字段回退规则模板。"""

    source: str = "workbuddy"                            # workbuddy / rule / manual
    headline: str = ""                                   # 卡片顶部一句话总括（可选）
    persona_label: str = ""                              # 人格称号（模型命名；空则用规则标签）
    slogan: str = ""                                     # 人格主标语
    tags: list[str] = field(default_factory=list)        # 人格标签
    quips: list[str] = field(default_factory=list)       # 金句（可截图）
    advice: list[str] = field(default_factory=list)      # 下月建议
    badge_desc: dict[str, str] = field(default_factory=dict)   # 徽章 title -> 描述
    cta: str = ""                                        # 底部号召语
    labels: dict[str, str] = field(default_factory=dict)       # 文本键 -> 文字（区块标题/指标名/表头/页脚/元信息）
    radar: dict[str, str] = field(default_factory=dict)        # 雷达维度名：原名 -> 新名
    badge_title: dict[str, str] = field(default_factory=dict)  # 徽章名：原名 -> 新名
    # ---- 场景整句覆写：模型可在这里自由发挥「一句话总括」，比 labels 更松 ----
    solve: dict = field(default_factory=dict)      # {headline, grade_word, notes}
    preheat: dict = field(default_factory=dict)    # {headline, grade_word, tips[]}
    # ---- 运行时绑定（不参与序列化）：本次算出的真实数值字面量集合 ----
    # 有了它，TextResolver 才能在渲染时把「模型编的数字」挡回去；
    # 没有它（None）表示还没算出事实，只做键名/占位符校验。
    facts_numbers: set[str] | None = field(default=None, repr=False, compare=False)

    # ---- 读 ----
    @classmethod
    def load(cls, path: str | Path) -> "CopyPack":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            source=str(d.get("source") or "workbuddy"),
            headline=str(d.get("headline") or ""),
            persona_label=str(d.get("persona_label") or ""),
            slogan=str(d.get("slogan") or ""),
            tags=[str(x) for x in (d.get("tags") or [])],
            quips=[str(x) for x in (d.get("quips") or [])],
            advice=[str(x) for x in (d.get("advice") or [])],
            badge_desc={str(k): str(v) for k, v in (d.get("badge_desc") or {}).items()},
            cta=str(d.get("cta") or ""),
            labels={str(k): str(v) for k, v in (d.get("labels") or {}).items()},
            radar={str(k): str(v) for k, v in (d.get("radar") or {}).items()},
            badge_title={str(k): str(v) for k, v in (d.get("badge_title") or {}).items()},
            solve=_str_map(d.get("solve")),
            preheat=_str_map(d.get("preheat")),
        )

    def bind_facts(self, facts: dict | None) -> None:
        """把本次算出的真实数值绑定进来，开启「编数字」的渲染级回退。"""
        self.facts_numbers = _numbers_of(facts or {}) if facts else None

    @property
    def active(self) -> bool:
        """是否有任何字段被模型覆写。"""
        return bool(self.headline or self.persona_label or self.slogan or self.tags
                    or self.quips or self.advice or self.badge_desc or self.cta
                    or self.labels or self.radar or self.badge_title
                    or self.solve or self.preheat)


def build_copy_brief(a: "Archive") -> dict:
    """把档案整理成「文案素材 + 指北 + 输出 schema」，交给 WorkBuddy 写文案。

    返回的 dict 可原样 ``json.dump`` 成 ``copy_brief.json``。
    """
    # 延迟导入，避免 copy ← report/theme 的循环依赖
    from .report import build_advice
    from .theme import build_badges, build_quips, theme_for

    c, h, b, p = a.consumption, a.health, a.benefit, a.persona
    s, hb, act = a.savings, a.habit, a.activity
    th = theme_for(p)
    r = a.order_report

    facts = {
        "date_range": f"{c.date_start} ~ {c.date_end}",
        "order_count": c.order_count,
        "refunded_count": c.refunded_count,
        "total_spend": round(c.total_spend, 2),
        "avg_ticket": round(c.avg_ticket, 2),
        "fav_store": c.fav_store[0] if c.fav_store else "",
        "fav_store_count": c.fav_store[1] if c.fav_store else 0,
        "fav_item": c.fav_item[0] if c.fav_item else "",
        "fav_item_count": c.fav_item[1] if c.fav_item else 0,
        "top_items": [n for n, _ in c.item_dist[:6]],
        "meal_slots": dict(c.meal_dist),
        "total_discount": round(s.total_discount, 2),
        "discount_rate": round(s.discount_rate * 100, 1),
        "coupon_used": s.coupon_used,
        "best_deal": (f"省 ¥{s.best_deal[1]:.0f} {s.best_deal[0]}" if s.best_deal else ""),
        "bigmac_equiv": round(h.bigmac_equiv, 1),
        "total_kcal": round(h.total_kcal),
        "avg_sodium_mg": round(h.avg_sodium),
        "lights": dict(h.lights),
        "available_point": round(b.available_point),
        "coupon_count": b.coupon_count,
        "coupons_expiring": len(b.coupons_expiring),
        "available_coupon_count": b.available_coupon_count,
        "redeem_affordable": b.redeem_affordable,
        "frequent_name": hb.frequent_name,
        "peak_slot": hb.peak_slot,
        "upcoming_activity": act.upcoming[0].title if act.upcoming else "",
        "this_order": (f"{r.store_name} 实付 {r.paid_amount:.2f} 元 {len(r.items)} 件"
                       if r is not None else ""),
    }
    rule_drafts = {
        "persona_label": p.label,
        "slogan": th.slogan or p.one_liner,
        "tags": list(p.tags),
        "quips": build_quips(a),
        "advice": build_advice(a),
        "badges": [{"title": bg.title, "desc": bg.desc} for bg in build_badges(a)],
    }
    # 全部可覆写文字的默认值（含区块标题/指标名/表头/页脚/元信息）
    text_map = text_defaults()
    # 动态文字：雷达维度名、徽章名（原名即示例，可改名）
    dynamic_text = {
        "radar": {k: k for k in p.radar},
        "badge_title": {bg.title: bg.title for bg in build_badges(a)},
    }
    instructions = (
        "你是「麦门文案师」，为一份麦当劳个人消费档案写**全部展示文字**。"
        "严格基于 facts 里的真实数字，不得编造未出现的数字或事实。"
        "风格：口语、俏皮、有网感、可截图传播；目标是让读者也想晒一份自己的档案。"
        "**persona_label 是重点**：请根据本档案的数据特征，重新命名一个 3-6 字、贴合本人、"
        "独一份的人格称号（如「折扣狙击手」「券场收割机」），不要照抄 rule_drafts.persona_label "
        "那套通用称号。产出的 slogan/tags 要与这个新称号气质一致。"
        "**labels 覆盖除数值外的所有文字**：区块标题、指标名、KPI 名、表头、页脚、元信息行都可改写"
        "（key 见 text_map，默认值仅供参考）。**改写 labels 时必须保留 {占位符}**，"
        "例如 lbl.kpi_save_rate 的 {rate}、lbl.meta_line 的 {theme}/{n}/{m}/{start}/{end}——"
        "占用符由程序填入真实数值，删除会导致数字丢失。"
        "**radar 覆盖雷达维度名、badge_title 覆盖徽章名**（key 见 dynamic_text）。"
        "产出严格 JSON，字段见 schema；badge_desc 的 key 必须是 rule_drafts.badges 里的 title。"
    )
    schema = {
        "source": "workbuddy",
        "headline": "卡片顶部一句话总括（≤22 字）",
        "persona_label": "人格称号（3-6 字，按本档案数据重新命名，如「折扣狙击手」；勿照抄规则称号）",
        "slogan": "人格主标语（≤20 字，需与新称号气质一致）",
        "tags": ["3-6 个短标签，替换默认人格标签"],
        "quips": ["2-4 句金句，基于真实数字，适合截图"],
        "advice": ["3-6 条下月建议，可执行、口语"],
        "badge_desc": {"<徽章 title>": "≤10 字的一句吐槽/注释"},
        "cta": "底部号召语（≤16 字）",
        "labels": {"<text_map 里的 key>": "改写后的文字；必须保留 {占位符}，不得编造数值"},
        "radar": {"<原维度名>": "新维度名（≤6 字）"},
        "badge_title": {"<原徽章名>": "新徽章名（≤8 字）"},
    }
    return {
        "task": "为「麦麦战绩 McProfile」生成全部展示文字（WorkBuddy 在环，无需外部 Key）",
        "persona": {"label": p.label, "emoji": p.emoji, "one_liner": p.one_liner,
                    "tags": list(p.tags), "radar": dict(p.radar)},
        "theme": {"name": th.name, "slogan_rule": th.slogan},
        "facts": facts,
        "rule_drafts": rule_drafts,
        "text_map": text_map,
        "dynamic_text": dynamic_text,
        "instructions": instructions,
        "schema": schema,
    }


# ====================================================================== #
# 护栏：模型写文案时最容易犯的两个错
#   1. 删掉 {占位符} → 数字丢失（**最严重**，会让卡片显示不全）
#   2. 凭空编数字 → 事实失真（数值必须来自 facts）
# 两者都只**披露告警**，不静默放行，也不硬阻断（避免误伤正常的文字创作）。
# ====================================================================== #
_RE_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_RE_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def missing_placeholders(key: str, override: str) -> list[str]:
    """覆写文案相对默认模板丢了哪些占位符。空列表 = 安全。"""
    default = TEXT_REGISTRY.get(key, {}).get("default", "")
    need = set(_RE_PLACEHOLDER.findall(default))
    have = set(_RE_PLACEHOLDER.findall(override))
    return sorted(need - have)


def _closest_key(key: str) -> str:
    """给写错的键猜一个最像的正确键（前缀相同优先，其次编辑距离）。"""
    if not key or "." not in key:
        return ""
    prefix = key.split(".")[0] + "."
    cands = [k for k in TEXT_REGISTRY if k.startswith(prefix)] or list(TEXT_REGISTRY)
    tail = key.split(".")[-1]
    best, best_score = "", 10**9
    for c in cands:
        a, b = c.split(".")[-1], tail
        # 简易编辑距离（够用即可，候选键都是短字符串）
        dp = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            prev, dp[0] = dp[0], i
            for j, cb in enumerate(b, 1):
                cur = dp[j]
                dp[j] = min(prev + (ca != cb), dp[j] + 1, dp[j - 1] + 1)
                prev = cur
        if dp[-1] < best_score:
            best, best_score = c, dp[-1]
    return best if best_score <= max(2, len(tail) // 2) else ""


def _free_text_leaks(pack: "CopyPack", allowed_numbers: set[str] | None) -> list[str]:
    """模型**自由发挥**（没有默认模板兜底）的那几段文字里的编数字检测。"""
    if not allowed_numbers:
        return []
    free: list[tuple[str, str]] = [
        ("headline", pack.headline), ("slogan", pack.slogan), ("cta", pack.cta),
        ("solve.headline", str(pack.solve.get("headline", ""))),
        ("preheat.headline", str(pack.preheat.get("headline", ""))),
    ]
    for blk_name, blk in (("solve", pack.solve), ("preheat", pack.preheat)):
        gw = blk.get("grade_word")
        if isinstance(gw, str):
            free.append((f"{blk_name}.grade_word", gw))
        elif isinstance(gw, dict):                      # {评级: 词} 写法逐条查
            for g, w in gw.items():
                if isinstance(w, str):
                    free.append((f"{blk_name}.grade_word.{g}", w))
    for q in pack.quips:
        free.append(("quips", q))
    for x in pack.advice:
        free.append(("advice", x))
    for t in (pack.preheat.get("tips") or []):
        if isinstance(t, str):
            free.append(("preheat.tips", t))
    for t in (pack.solve.get("notes") or []):
        if isinstance(t, str):
            free.append(("solve.notes", t))
    warns: list[str] = []
    for name, text in free:
        if not text:
            continue
        for num in _leaked_numbers(text, "", allowed_numbers):
            warns.append(f"{name} 出现未知数字「{num}」（不在 facts 里，"
                         f"疑似编造，请改用 facts 数值或删掉）")
            break
    return warns


def _leaked_numbers(text: str, default_text: str, allowed: set[str] | None) -> list[str]:
    """覆写文本里「凭空出现」的数字：不在默认模板里，也不在 facts 允许集合里。

    ``allowed`` 为 None 表示没有 facts 可比对，此时不做数值检测（避免误伤）。
    """
    if allowed is None:
        return []
    base = set(_RE_NUMBER.findall(default_text or ""))
    return [n for n in _RE_NUMBER.findall(text or "") if n not in base and n not in allowed]


def validate_copy_pack(pack: "CopyPack", allowed_numbers: set[str] | None = None) -> list[str]:
    """校验模型产出的文案包，返回**人类可读的告警列表**（空 = 没问题）。

    - 键写错：模型发明了一个不存在的 key → 静默失效（最容易被忽略，必须报）；
    - 占位符丢失：必须报，因为会直接导致数值消失；
    - 数值泄漏：模型文案里出现了 facts 中不存在的数字（可能是编的）。
    """
    warns: list[str] = []

    for key, text in (pack.labels or {}).items():
        if key not in TEXT_REGISTRY:
            near = _closest_key(key)
            warns.append(f"labels.{key} 不是已知文案键，已忽略（这条改写不会生效）"
                         + (f"，是不是想写 {near}？" if near else "，请用 brief 的 text_map 里的 key"))
            continue
        lost = missing_placeholders(key, text)
        if lost:
            warns.append(f"labels.{key} 丢失占位符 {'、'.join('{' + x + '}' for x in lost)}"
                         f" → 该条已回退默认文案（否则数值会消失）")
        for num in _leaked_numbers(text, TEXT_REGISTRY[key].get("default", ""), allowed_numbers):
            warns.append(f"labels.{key} 出现未知数字「{num}」（不在 facts 里，疑似编造）"
                         f" → 已回退默认文案；请改用 {{占位符}} 或删掉该数字")
            break

    # 顶层字段名写错（如 solvd / preheat 拼错、solve 里塞了未知子键）同样静默失效
    for block, allowed_sub in (("solve", {"headline", "grade_word", "notes"}),
                               ("preheat", {"headline", "grade_word", "tips"})):
        blk = getattr(pack, block, {}) or {}
        for sub in blk:
            if sub not in allowed_sub:
                warns.append(f"{block}.{sub} 不是已知字段，已忽略（可用：{'、'.join(sorted(allowed_sub))}）")

    # 模型自由发挥的文本最容易夹带编造数字（与 labels 用同一套检测口径）
    warns.extend(_free_text_leaks(pack, allowed_numbers))
    return warns


def _numbers_of(facts: dict, extra: list[float] | None = None) -> set[str]:
    """把 facts 里的数值摊平成「允许出现的数字字面量」集合（含常见格式化变体）。"""
    out: set[str] = set()
    stack: list = [facts]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
        elif isinstance(cur, bool):
            continue
        elif isinstance(cur, (int, float)):
            for v in (cur, round(float(cur), 1), round(float(cur), 2), int(cur)):
                s = f"{v:g}" if isinstance(v, float) else str(v)
                out.add(s)
                out.add(str(int(float(s)))) if float(s) == int(float(s)) else None
    for v in extra or []:
        out.add(f"{v:g}")
    return out


# ====================================================================== #
# 麦麦预热台 · McPreheat 的文案素材
# ====================================================================== #
def build_preheat_brief(pre, *, repo_url: str = "") -> dict:
    """把「预热台」整理成文案素材，交给 WorkBuddy 写文案。"""
    facts = {
        "today": str(getattr(pre, "today", "")),
        "server_time": getattr(pre, "server_time", ""),
        "target_title": (pre.target.title if getattr(pre, "target", None) else ""),
        "days_left": getattr(pre, "days_left", None),
        "missing": [{"title": c.title, "days": c.days_to_expire, "until": c.until_text}
                    for c in getattr(pre, "missing", [])],
        "surviving": [{"title": c.title, "days": c.days_to_expire,
                       "tight": getattr(c, "tight", False)}
                      for c in getattr(pre, "surviving", [])],
        "urgent": [{"title": c.title, "days": c.days_to_expire} for c in getattr(pre, "urgent", [])],
        "running": [c.title for c in getattr(pre, "running", [])],
        "upcoming": [{"title": c.title, "date": c.date} for c in getattr(pre, "upcoming", [])],
        "unparsed_count": getattr(pre, "unparsed_count", 0),
        "coupon_unparsed_count": getattr(pre, "coupon_unparsed_count", 0),
        "score": getattr(pre, "score", 0),
        "grade": getattr(pre, "grade", ""),
        "points": getattr(pre, "points", 0.0),
        "redeemable": getattr(pre, "redeemable", 0),
        "coupon_count": len(getattr(pre, "coupons", [])),
    }
    text_map = {k: v["default"] for k, v in TEXT_REGISTRY.items() if k.startswith("ph.")}
    rule_drafts = {
        "headline": getattr(pre, "headline", ""),
        "tips": list(getattr(pre, "tips", [])),
        "grade_word": {"S": "弹药充足，稳了", "A": "大体就绪，还能补",
                       "B": "有缺口，先看冲突", "C": "裸奔进场，建议先清券"
                       }.get(getattr(pre, "grade", ""), ""),
    }
    instructions = (
        "你是「麦门文案师」，为一张「麦麦预热台」倒计时备战卡写**全部展示文字**。"
        "严格基于 facts 里的真实数字，**不得编造未出现的数字或事实**。"
        "这张卡的钩子是「活动日历 × 券到期」的交叉冲突：**有些券等不到活动那天**。"
        "风格：有紧迫感、口语、可截图；但**不要渲染焦虑或鼓励过度消费**——"
        "定位是「看见并提醒」，不是「催你赶紧吃」。"
        "**preheat.headline 是重点**：一句话把倒计时和冲突同时说出来（≤24 字），"
        "数字必须来自 facts（days_left / missing 条数）。有冲突时优先用冲突做钩子。"
        "**preheat.tips 可整段重写**（2-5 条），每条都要**落到具体某张券或某个事实上**，"
        "不要写「关注官方活动」这种通用鸡汤。"
        "**labels 覆盖除数值外的所有文字**（key 见 text_map），"
        "**改写 labels 时必须保留 {占位符}**——删掉会导致数字丢失（我们会校验）。"
        "备战度评级词用 preheat.grade_word 覆写（见 schema：可写成字符串或 {S:…, A:…} 按档位各写一句）。"
        "产出严格 JSON，字段见 schema。"
    )
    return {
        "task": "为「麦麦预热台 McPreheat」生成全部展示文字（WorkBuddy 在环，无需外部 Key）",
        "scene": "preheat",
        "facts": facts,
        "rule_drafts": rule_drafts,
        "text_map": text_map,
        "instructions": instructions,
        "schema": {
            "source": "workbuddy",
            "preheat": {
                "headline": "倒计时钩子句（≤24 字，数字须来自 facts）",
                "grade_word": ("备战度评级词（≤10 字）。两种写法："
                               "① 字符串 → 所有评级同一句；"
                               "② 对象 → {\"S\": …, \"A\": …, \"B\": …, \"C\": …} "
                               "按备战度各写一句（推荐；没写的档位回退默认）"),
                "tips": ["2-5 条行动建议，每条落到具体券/具体事实上"],
            },
            "labels": {"<text_map 里的 ph.* key>": "改写后的文字；必须保留 {占位符}"},
        },
        "repo_url": repo_url,
    }
