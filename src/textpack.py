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
from dataclasses import asdict, dataclass, field
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
    "brand": {"default": "麦当劳 MCP · 麦麦档案", "desc": "卡片顶部品牌行"},
    "sec.md_title": {"default": "麦麦档案 · McProfile", "desc": "Markdown 文档主标题"},
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
    "cta": {"default": "🍟 我也要一份我的麦麦档案", "desc": "底部号召语（cta 字段缺省时用）"},

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
    "lbl.report_menu_stat": {"default": "菜单共 {n} 款商品（带图 {img} · 带价 {p}）",
                             "desc": "战报：菜单解析统计"},

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
    "ft.produced": {"default": "由麦麦档案 McProfile 生成", "desc": "页脚：生成来源"},
    "ft.tools": {"default": "本次调用 {n} 个官方 MCP 工具", "desc": "页脚：工具调用"},
    "ft.offline": {"default": "离线演示模式", "desc": "页脚：离线模式"},
    "ft.line1": {"default": "{tools} · 仅供个人复盘，不构成医疗/营养建议",
                 "desc": "页脚第一行（PNG）"},
    "ft.line2": {"default": "麦麦档案 McProfile · 基于麦当劳官方 MCP 生成",
                 "desc": "页脚第二行（PNG）"},
    "ft.disclaimer_short": {"default": "仅供个人复盘，不构成营养或医疗建议",
                            "desc": "卡片免责声明（短）"},
    "ft.disclaimer": {"default": "本档案由「麦麦档案 McProfile」基于麦当劳官方 MCP 生成，"
                                "仅供个人复盘参考，不构成医疗或营养建议；"
                                "餐品与价格以麦当劳官方渠道为准。",
                      "desc": "Markdown 免责声明（长）"},
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
                t = ov
        try:
            return t.format(**kw)
        except Exception:  # 覆写模板占位符缺失 → 回退默认，保证数值不丢
            try:
                return default.format(**kw)
            except Exception:
                return default


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
        )

    # ---- 写 ----
    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def active(self) -> bool:
        """是否有任何字段被模型覆写。"""
        return bool(self.headline or self.persona_label or self.slogan or self.tags
                    or self.quips or self.advice or self.badge_desc or self.cta
                    or self.labels or self.radar or self.badge_title)


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
        "task": "为「麦麦档案 McProfile」生成全部展示文字（WorkBuddy 在环，无需外部 Key）",
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
