"""千人千面主题引擎：把「麦门人格」翻译成配色 / 徽章 / 金句。

设计目标：**同一份档案，不同的人打开是不同的那一张海报**。
- `theme_for(persona)`  —— 人格 → 一整套深色潮酷配色（含光晕、Slogan）
- `build_badges(archive)` —— 行为 → 成就徽章墙（可炫耀的「战果」）
- `build_quips(archive)`  —— 数据 → 千人千面的金句（够种草、够上镜）

本模块不反向依赖 `archive`（仅类型标注用），避免循环导入。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # noqa: F401 —— 仅用于类型标注
    from .archive import Archive
    from .persona import Persona


# ====================================================================== #
# 主题配色
# ====================================================================== #
@dataclass(frozen=True)
class Theme:
    """一套「暗黑潮酷」主题：深底 + 高饱和强调色 + 霓虹光晕。"""

    key: str
    name: str
    bg: str            # 背景主色（深）
    bg2: str           # 背景渐变次色
    panel: str         # 玻璃拟态面板底色
    primary: str       # 主强调色
    accent: str        # 次强调色
    glow: str          # 外发光（rgba）
    slogan: str = ""   # 人格 Slogan
    ink: str = "#F6F4EF"      # 主文字
    muted: str = "#98938B"    # 次文字


# 主色一律高饱和霓虹，底色一律近黑——保证截图在朋友圈/小红书里"跳"出来。
THEMES: dict[str, Theme] = {
    "优惠猎人": Theme("deal", "优惠猎人", "#171205", "#241A06", "rgba(255,199,44,.08)",
                    "#FFC72C", "#FFE38A", "rgba(255,199,44,.55)",
                    "在我手里，没有一单是原价。"),
    "深夜加餐党": Theme("night", "深夜加餐党", "#080D1C", "#0E1630", "rgba(77,124,254,.10)",
                    "#4D7CFE", "#89A8FF", "rgba(77,124,254,.55)",
                    "夜再深，总有一家麦记的灯为你亮着。"),
    "巨无霸原教旨主义者": Theme("beef", "巨无霸原教旨主义者", "#1B0806", "#2A0C08", "rgba(226,58,46,.10)",
                    "#E23A2E", "#FF7A6B", "rgba(226,58,46,.55)",
                    "牛肉厚堡，才是我心中的正统麦门。"),
    "甜品收割机": Theme("dessert", "甜品收割机", "#1B0818", "#2A0C24", "rgba(232,91,199,.10)",
                    "#E85BC7", "#FF9BE2", "rgba(232,91,199,.55)",
                    "正餐可以商量，甜品绝不将就。"),
    "咖啡续命师": Theme("coffee", "咖啡续命师", "#150F09", "#22160C", "rgba(201,138,75,.10)",
                    "#C98A4B", "#E8B579", "rgba(201,138,75,.55)",
                    "我的血液里，有一半是鲜萃。"),
    "尝鲜先锋": Theme("new", "尝鲜先锋", "#04140F", "#08271E", "rgba(23,195,162,.10)",
                    "#17C3A2", "#5FE6C6", "rgba(23,195,162,.55)",
                    "每次上新，我都是第一个打卡的人。"),
    "早餐仪式感大师": Theme("breakfast", "早餐仪式感大师", "#1A1006", "#2A1A08", "rgba(255,138,61,.10)",
                    "#FF8A3D", "#FFB176", "rgba(255,138,61,.55)",
                    "我的麦当劳一天，从清晨第一口麦满分开始。"),
    "炸鸡信徒": Theme("chicken", "炸鸡信徒", "#1A0D06", "#2A1408", "rgba(255,107,44,.10)",
                    "#FF6B2C", "#FF9B66", "rgba(255,107,44,.55)",
                    "一份脆汁鸡，能治愈一整天的班味。"),
    "麦当劳巡礼者": Theme("tour", "麦当劳巡礼者", "#06131A", "#0A2130", "rgba(43,167,217,.10)",
                    "#2BA7D9", "#6FD0F2", "rgba(43,167,217,.55)",
                    "我的足迹遍及多城，四海皆为麦门。"),
    "专一老熟客": Theme("loyal", "专一老熟客", "#08140D", "#0C2415", "rgba(47,163,94,.10)",
                    "#2FA35E", "#6BD79A", "rgba(47,163,94,.55)",
                    "认准一家店，点餐不用看菜单。"),
}

DEFAULT_THEME = Theme("classic", "麦门门徒", "#0E0C08", "#1C170E", "rgba(255,199,44,.08)",
                      "#FFC72C", "#DA291C", "rgba(255,199,44,.5)",
                      "每一单，都是对麦门的一次朝圣。")


def theme_for(persona: "Persona | None", archive: "Archive | None" = None) -> Theme:
    """按人格标签取主题；标签未命中时，用雷达最强维度兜底。"""
    if persona is not None:
        if persona.label in THEMES:
            return THEMES[persona.label]
        # 兜底：看雷达哪个维度最突出，映射到相近主题
        if persona.radar:
            top = max(persona.radar.items(), key=lambda kv: kv[1])[0]
            guess = {
                "省钱力": "优惠猎人", "夜宵力": "深夜加餐党", "肉食力": "巨无霸原教旨主义者",
                "甜品力": "甜品收割机", "咖啡力": "咖啡续命师", "早餐魂": "早餐仪式感大师",
            }.get(top)
            if guess in THEMES:
                return THEMES[guess]
    return DEFAULT_THEME


# ====================================================================== #
# 成就徽章
# ====================================================================== #
@dataclass
class Badge:
    emoji: str
    title: str
    desc: str = ""


def build_badges(archive: "Archive") -> list[Badge]:
    """从档案数据里，挑出这个人「值得炫耀」的成就，组成徽章墙。"""
    c = archive.consumption
    h = archive.health
    s = archive.savings
    b = archive.benefit
    hb = archive.habit
    out: list[Badge] = []

    # —— 消费类 ——
    if c.avg_ticket >= 40:
        out.append(Badge("🍔", f"客单 ¥{c.avg_ticket:.0f}", "开局就是豪华配置"))
    if c.order_count >= 20:
        out.append(Badge("🔥", f"{c.order_count} 单", "麦门高频选手"))
    if c.fav_store and c.fav_store[1] >= 5:
        out.append(Badge("🏠", f"常客×{c.fav_store[1]}", c.fav_store[0]))

    # —— 省钱类 ——
    if s.total_discount >= 100:
        out.append(Badge("💸", f"省下 ¥{s.total_discount:.0f}", "优惠猎人的战绩"))
    if s.discount_rate >= 0.3:
        out.append(Badge("🎯", f"省钱率 {s.discount_rate*100:.0f}%", "比谁都懂凑单"))
    if s.coupon_used >= 10:
        out.append(Badge("🎟️", f"用券 {s.coupon_used} 次", "券券精算师"))

    # —— 健康类 ——
    if h.bigmac_equiv >= 10:
        out.append(Badge("🌋", f"≈{h.bigmac_equiv:.0f} 个巨无霸", "热量核弹持有者"))
    if h.lights.get("green", 0) >= 5:
        out.append(Badge("🥗", f"{h.lights['green']} 顿绿灯", "吃得很克制"))
    if h.lights.get("red", 0) >= 5:
        out.append(Badge("🛢️", f"{h.lights['red']} 顿红灯", "放纵但快乐"))

    # —— 习惯 / 口味类 ——
    top_slot = hb.peak_slot
    if top_slot == "早餐":
        out.append(Badge("🌅", "早八战士", "一天从麦满分开始"))
    elif top_slot == "深夜":
        out.append(Badge("🌙", "深夜食堂", "凌晨的麦记见证者"))
    elif top_slot == "下午茶":
        out.append(Badge("☕", "下午茶贵族", "三点一线准时上线"))
    if hb.frequent_name:
        out.append(Badge("⭐", "有官方常点", hb.frequent_name))
    if len(c.item_dist) >= 10:
        out.append(Badge("🎨", f"尝鲜 {len(c.item_dist)} 款", "麦门集邮王"))
    if len(c.store_dist) >= 5:
        out.append(Badge("🗺️", f"打卡 {len(c.store_dist)} 家店", "城市麦门地图"))

    # —— 权益类 ——
    if b.coupon_count >= 20:
        out.append(Badge("🎫", f"{b.coupon_count} 张券在手", "行走的券库"))
    if b.available_point >= 1000:
        out.append(Badge("💎", f"{b.available_point:.0f} 积分", "富甲一方"))
    if b.redeem_affordable >= 10:
        out.append(Badge("🛍️", f"可兑 {b.redeem_affordable} 种", "积分花得出去"))

    return out[:9]  # 徽章墙最多 9 枚，排满 3×3 最好看


# ====================================================================== #
# 千人千面金句
# ====================================================================== #
def build_quips(archive: "Archive") -> list[str]:
    """按数据生成几句「可截图」的金句，兼顾种草感与传播性。"""
    c = archive.consumption
    h = archive.health
    s = archive.savings
    hb = archive.habit
    p = archive.persona
    out: list[str] = []

    if s.total_discount >= 50:
        out.append(f"这一年我在麦当劳省下 ¥{s.total_discount:.0f}，够再吃 {int(s.total_discount/30) or 1} 顿豪华套餐。")
    if h.bigmac_equiv >= 5:
        out.append(f"我吃下的热量约等于 {h.bigmac_equiv:.0f} 个巨无霸——快乐是真的，热量也是真的。")
    if hb.frequent_name:
        out.append(f"我的官方常点是「{hb.frequent_name}」，闭眼点都不会错。")
    if c.fav_item:
        out.append(f"复购最多的是「{c.fav_item[0]}」，它懂我。")
    if p.one_liner:
        out.append(p.one_liner)
    return out[:4]
