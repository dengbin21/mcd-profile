"""麦门人格引擎：按订单特征生成人格标签与画像雷达。

纯规则、可解释：每个标签都由可复算的行为特征支撑，便于用户信服与分享。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .analysis import Consumption, Health, Savings
from .models import Order


# 关键词 → 口味维度
_BEEF = ("巨无霸", "安格斯", "双牛", "双层吉士", "吉士汉堡", "培根")
_CHICKEN = ("鸡腿", "鸡排", "脆汁鸡", "麦乐鸡", "鸡翅", "板烧", "麦辣鸡")
_FISH = ("麦香鱼", "鳕鱼", "鱼")
_FRIED = ("薯条", "薯饼", "鸡块", "麦乐鸡", "鸡翅", "脆汁鸡", "鸡排", "扭扭薯", "油条")
_COFFEE = ("咖啡", "美式", "玛奇朵", "卡布奇诺", "奶铁", "拿铁", "鲜萃", "浓缩")
_DESSERT = ("派", "新地", "麦旋风", "冰淇淋", "圆筒", "甜筒", "糍粑")
_COMBO = ("套餐", "随心配", "买一送一", "三件", "四件", "组合", "6折", "任选", "拼盘", "半价")
_NEW = ("月堡", "限定", "联名", "新品", "龙焰", "三文鱼", "咸蛋黄", "寒露", "玫瑰红糖", "扭扭薯")


@dataclass
class Persona:
    label: str = ""
    emoji: str = ""
    one_liner: str = ""
    tags: list[str] = field(default_factory=list)
    radar: dict[str, int] = field(default_factory=dict)   # 维度名 -> 0~100


def _count(orders: list[Order], keywords: tuple[str, ...]) -> int:
    n = 0
    for o in orders:
        for name in o.product_names() + [i[0] for i in o.flat_items()]:
            if any(k in name for k in keywords):
                n += 1
                break
    return n


def build_persona(orders: list[Order], cons: Consumption, health: Health,
                  savings: Savings | None = None) -> Persona:
    valid = [o for o in orders if not o.is_refunded]
    n = max(len(valid), 1)

    slots = cons.meal_dist
    breakfast = slots.get("早餐", 0) / n
    late = slots.get("深夜", 0) / n
    dinner = slots.get("晚餐", 0) / n

    beef = _count(valid, _BEEF) / n
    chicken = _count(valid, _CHICKEN) / n
    fish = _count(valid, _FISH) / n
    fried = _count(valid, _FRIED) / n
    coffee = _count(valid, _COFFEE) / n
    dessert = _count(valid, _DESSERT) / n
    combo = _count(valid, _COMBO) / n
    new = _count(valid, _NEW) / n

    store_count = len(cons.store_dist)
    top_store_share = (cons.fav_store[1] / n) if cons.fav_store else 0

    # 省钱力：组合点单占比 + 实际省钱率（来自券/优惠明细）
    discount_rate = savings.discount_rate if savings else 0.0
    savings_power = max(combo, min(1.0, discount_rate * 3))

    # 雷达（0~100）
    radar = {
        "早餐魂": _pct(breakfast),
        "夜宵力": _pct(late),
        "肉食力": _pct(max(beef, chicken, fish)),
        "甜品力": _pct(dessert),
        "咖啡力": _pct(coffee),
        "省钱力": _pct(savings_power),
    }

    # 候选人格（分数越高越优先）
    cands: list[tuple[float, str, str, str]] = [
        (breakfast * 100, "🌅", "早餐仪式感大师", "你的麦当劳一天，是从清晨第一口麦满分开始的。"),
        (late * 100, "🌙", "深夜加餐党", "夜再深，总有一家麦记的灯为你亮着。"),
        (savings_power * 100 + 20, "🎯", "优惠猎人", "在你手里，没有一单是原价买的。"),
        (beef * 100, "🍔", "巨无霸原教旨主义者", "牛肉厚堡才是你心中的正统麦门。"),
        (chicken * 100, "🍗", "炸鸡信徒", "一份脆汁鸡，能治愈一整天的班味。"),
        (dessert * 100, "🍦", "甜品收割机", "正餐可以商量，甜品绝不将就。"),
        (coffee * 100, "☕", "咖啡续命师", "你的血液里，有一半是鲜萃。"),
        (new * 100, "🚀", "尝鲜先锋", "每次上新，你都是第一个打卡的人。"),
    ]
    if store_count >= 5:
        cands.append((60 + store_count * 3, "🗺️", "麦当劳巡礼者", f"你的足迹遍及 {store_count} 家餐厅，四海皆为麦门。"))
    if top_store_share >= 0.5:
        cands.append((top_store_share * 80, "🏠", "专一老熟客", "认准一家店，点餐不用看菜单。"))

    cands.sort(key=lambda x: x[0], reverse=True)
    _, emoji, label, one_liner = cands[0]

    # 行为标签
    tags: list[str] = []
    if breakfast >= 0.3:
        tags.append("早餐刚需")
    if late >= 0.15:
        tags.append("夜宵选手")
    if combo >= 0.5:
        tags.append("券券精明")
    if discount_rate >= 0.25:
        tags.append("省钱高手")
    if dessert >= 0.3:
        tags.append("甜品博爱")
    if coffee >= 0.3:
        tags.append("咖啡因驱动")
    if beef + chicken + fish >= 0.7:
        tags.append("无肉不欢")
    if new >= 0.2:
        tags.append("新品雷达")
    if store_count >= 5:
        tags.append("巡店达人")
    else:
        tags.append("就近锁定")
    if health.lights.get("green", 0) >= len(health.per_order) * 0.5:
        tags.append("吃得挺克制")
    else:
        tags.append("放纵系")

    return Persona(label=label, emoji=emoji, one_liner=one_liner, tags=tags, radar=radar)


def _pct(ratio: float) -> int:
    return max(0, min(100, int(round(ratio * 130))))
