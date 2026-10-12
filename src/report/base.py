"""report 共享基座：金额格式 / 图片引用 / 文案覆写 / 规则建议。

三种渲染器（Markdown / HTML / PNG）共用的逻辑都集中在这里：
- :func:`_resolver` 文案解析（CopyPack 覆写 → 规则模板回退）；
- ``_eff_*`` 系列「有效值」函数（模型文案优先、规则兜底）；
- :func:`build_advice` 规则建议（CopyPack 未提供 advice 时的回退）。
"""
from __future__ import annotations

from .. import images
from ..archive import Archive
from ..textpack import CopyPack, TextResolver
from ..theme import Badge, Theme, build_badges, build_quips

# 工具中文名（用于覆盖清单可读化）
TOOL_DESC = {
    "order-list": "历史订单列表",
    "query-order": "订单详情（券/优惠/餐方式）",
    "query-my-account": "积分账户",
    "query-my-coupons": "手持券资产",
    "query-my-prizes": "抽奖奖品",
    "query-lottery-info": "积分抽奖活动",
    "available-coupons": "可领取券（麦麦省）",
    "mall-order-list": "商城订单列表",
    "mall-order-detail": "商城订单详情",
    "mall-points-products": "积分可兑换商品",
    "query-nearby-stores": "附近/收藏门店",
    "delivery-query-addresses": "外送地址",
    "delivery-query-stores": "地址可配送门店",
    "query-meals": "门店菜单（含我的常点）",
    "query-meal-detail": "餐品组成",
    "query-store-coupons": "门店可用券",
    "calculate-price": "算价（含取餐方式）",
    "campaign-calendar": "营销活动日历",
    "now-time-info": "服务器时间",
    "list-nutrition-foods": "官方营养库",
    "create-order": "创建订单（点餐闭环）",
}


def yuan(x: float) -> str:
    return f"¥{x:,.2f}"


def img_ref(item) -> str:
    """取用于渲染的图片来源：优先本地已下载（可自包含 / 可嵌入），其次 URL。"""
    return getattr(item, "image_local", "") or getattr(item, "image", "")


def img_src(item) -> str:
    """HTML ``<img src>``：本地文件 → data-uri（单文件自包含）；远程 → 原样；无图 → 空串。"""
    return images.to_data_uri(img_ref(item))


def resolver(copy: CopyPack | None) -> TextResolver:
    return TextResolver(copy)


def eff_label(a: Archive, copy: CopyPack | None) -> str:
    """人格称号：模型命名优先（展示层）；配色仍锚定规则标签 a.persona.label。"""
    if copy and copy.persona_label:
        return copy.persona_label
    return a.persona.label


def eff_slogan(a: Archive, copy: CopyPack | None, th: Theme) -> str:
    if copy and copy.slogan:
        return copy.slogan
    return th.slogan or a.persona.one_liner


def eff_tags(a: Archive, copy: CopyPack | None) -> list[str]:
    return copy.tags if (copy and copy.tags) else list(a.persona.tags)


def eff_quips(a: Archive, copy: CopyPack | None) -> list[str]:
    return copy.quips if (copy and copy.quips) else build_quips(a)


def eff_advice(a: Archive, copy: CopyPack | None) -> list[str]:
    return copy.advice if (copy and copy.advice) else build_advice(a)


def eff_badges(a: Archive, copy: CopyPack | None) -> list[Badge]:
    """徽章：模型可改**名字**（badge_title）与**描述**（badge_desc，按原名索引）。"""
    badges = build_badges(a)
    if copy and (copy.badge_desc or copy.badge_title):
        badges = [Badge(b.emoji,
                        (copy.badge_title.get(b.title) or b.title),
                        (copy.badge_desc.get(b.title) or b.desc)) for b in badges]
    return badges


def eff_radar(a: Archive, copy: CopyPack | None) -> dict[str, int]:
    """雷达维度：模型可改**维度名**（radar 原名 -> 新名）。"""
    if copy and copy.radar:
        return {copy.radar.get(k, k): v for k, v in a.persona.radar.items()}
    return dict(a.persona.radar)


def fmt_expiring(coupons: list[tuple[str, str]], limit: int = 4) -> str:
    shown = "、".join(f"{t}({d})" for t, d in coupons[:limit])
    if len(coupons) > limit:
        shown += f" 等共 {len(coupons)} 张"
    return shown


def build_advice(a: Archive) -> list[str]:
    """规则建议（CopyPack 未提供 advice 时的回退文案）。"""
    c, h, b = a.consumption, a.health, a.benefit
    s, act = a.savings, a.activity
    out: list[str] = []
    if h.lights.get("red", 0) or h.avg_sodium > 900:
        out.append(f"你平均每单钠 {h.avg_sodium:.0f} mg，偏高——薯条换玉米杯、饮料换无糖可乐，能明显降钠。")
    if h.lights.get("green", 0) >= sum(h.lights.values()) * 0.5 and h.lights:
        out.append("超过一半的订单是绿灯，饮食节奏不错，继续保持。")
    if h.bigmac_equiv >= 20:
        out.append(f"累计热量约 {h.bigmac_equiv} 个巨无霸，试试把一份小食换成沙拉/玉米杯。")
    if s.discount_rate and s.discount_rate >= 0.2:
        out.append(f"你的省钱率高达 {s.discount_rate*100:.0f}%，是妥妥的优惠猎人。")
    if b.coupons_expiring:
        out.append(f"有 {len(b.coupons_expiring)} 张券将在 30 天内到期，别浪费。")
    if b.available_coupon_count:
        out.append(f"麦麦省还有 {b.available_coupon_count} 张券可领，顺手领一下。")
    if b.redeem_affordable:
        cheapest = f"（如「{b.redeem_cheapest[0]}」）" if b.redeem_cheapest else ""
        out.append(f"你有 {b.available_point:.0f} 积分，够兑 {b.redeem_affordable} 种商城好物{cheapest}。")
    if act.upcoming:
        out.append(f"近期有 {len(act.upcoming)} 项官方活动，比如「{act.upcoming[0].title}」，可以留意。")
    if c.fav_item:
        out.append(f"最常点「{c.fav_item[0]}」，下次试试官方『随心配』把主食+小食组合，通常更省。")
    return out
