"""五维画像分析：消费 / 健康 / 权益 / 省钱 / 习惯 / 活动。

这是「麦麦档案」的分析核心——把原始订单与权益数据，翻译成可读、可分享的洞察。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .models import CampaignEvent, MealInfo, Order, RawArchive
from .nutrition import DAILY_REFERENCE, NutritionIndex


# ====================================================================== #
# 消费画像
# ====================================================================== #
@dataclass
class Consumption:
    order_count: int = 0            # 有效订单数（不含退款）
    refunded_count: int = 0
    total_spend: float = 0.0
    avg_ticket: float = 0.0
    max_order: tuple[str, float] | None = None      # (门店/日期, 金额)
    min_order: tuple[str, float] | None = None
    fav_store: tuple[str, int] | None = None
    fav_item: tuple[str, int] | None = None
    store_dist: list[tuple[str, int]] = field(default_factory=list)
    item_dist: list[tuple[str, int]] = field(default_factory=list)
    meal_dist: dict[str, int] = field(default_factory=dict)
    date_start: str = ""
    date_end: str = ""


def analyze_consumption(orders: list[Order]) -> Consumption:
    valid = [o for o in orders if not o.is_refunded]
    refunded = [o for o in orders if o.is_refunded]
    c = Consumption(refunded_count=len(refunded))
    if not valid:
        return c

    c.order_count = len(valid)
    c.total_spend = round(sum(o.amount for o in valid), 2)
    c.avg_ticket = round(c.total_spend / len(valid), 2)

    def tag(o: Order) -> str:
        return f"{o.date} {o.store_name}"

    hi = max(valid, key=lambda o: o.amount)
    lo = min(valid, key=lambda o: o.amount)
    c.max_order = (tag(hi), hi.amount)
    c.min_order = (tag(lo), lo.amount)

    store_counter = Counter(o.store_name for o in valid)
    c.store_dist = store_counter.most_common()
    c.fav_store = store_counter.most_common(1)[0] if store_counter else None

    item_counter: Counter[str] = Counter()
    for o in valid:
        for name in o.product_names():
            item_counter[name] += 1
    c.item_dist = item_counter.most_common()
    c.fav_item = item_counter.most_common(1)[0] if item_counter else None

    meal_counter = Counter(o.meal_slot() for o in valid)
    c.meal_dist = dict(meal_counter.most_common())

    dates = sorted(o.date for o in valid)
    c.date_start, c.date_end = (dates[0], dates[-1]) if dates else ("", "")
    return c


# ====================================================================== #
# 健康画像
# ====================================================================== #
@dataclass
class OrderHealth:
    date: str
    store_name: str
    kcal: float
    protein: float
    fat: float
    carbohydrate: float
    sodium: float
    matched: int = 0
    total_items: int = 0

    @property
    def light(self) -> str:
        if self.kcal <= 700 and self.sodium <= 800:
            return "green"
        if self.kcal <= 1000 and self.sodium <= 1200:
            return "yellow"
        return "red"


@dataclass
class Health:
    total_kcal: float = 0.0
    total_protein: float = 0.0
    total_fat: float = 0.0
    total_carbohydrate: float = 0.0
    total_sodium: float = 0.0
    avg_kcal: float = 0.0
    avg_sodium: float = 0.0
    coverage: float = 0.0                       # 订单商品被营养库命中的比例
    days: int = 0                               # 覆盖的天数
    per_order: list[OrderHealth] = field(default_factory=list)
    lights: dict[str, int] = field(default_factory=dict)
    bigmac_equiv: float = 0.0                   # 累计热量 ≈ 几个巨无霸
    unmatched: list[str] = field(default_factory=list)
    top_sodium: list[tuple[str, float]] = field(default_factory=list)


def analyze_health(orders: list[Order], index: NutritionIndex) -> Health:
    h = Health()
    valid = [o for o in orders if not o.is_refunded]
    bigmac = index.match("巨无霸")
    bigmac_kcal = bigmac.energyKcal if bigmac else 550.0

    matched_total = item_total = 0
    sodium_counter: Counter[str] = Counter()
    days = set()

    for o in valid:
        oh = OrderHealth(date=o.date, store_name=o.store_name, kcal=0, protein=0,
                         fat=0, carbohydrate=0, sodium=0)
        for name, qty in o.flat_items():
            item_total += 1
            food = index.match(name)
            if food is None:
                h.unmatched.append(name)
                continue
            matched_total += 1
            oh.kcal += food.energyKcal * qty
            oh.protein += food.protein * qty
            oh.fat += food.fat * qty
            oh.carbohydrate += food.carbohydrate * qty
            oh.sodium += food.sodium * qty
            sodium_counter[name] += food.sodium * qty
        oh.matched, oh.total_items = matched_total, item_total
        h.per_order.append(oh)
        days.add(o.date)

        h.total_kcal += oh.kcal
        h.total_protein += oh.protein
        h.total_fat += oh.fat
        h.total_carbohydrate += oh.carbohydrate
        h.total_sodium += oh.sodium

    n = len(valid)
    if n:
        h.avg_kcal = round(h.total_kcal / n, 1)
        h.avg_sodium = round(h.total_sodium / n, 1)
    h.coverage = round(matched_total / item_total * 100, 1) if item_total else 0.0
    h.days = len(days)
    h.bigmac_equiv = round(h.total_kcal / bigmac_kcal, 1) if bigmac_kcal else 0.0
    h.lights = dict(Counter(oh.light for oh in h.per_order))
    h.top_sodium = sodium_counter.most_common(5)
    # 去重未命中清单
    seen: list[str] = []
    for x in h.unmatched:
        if x not in seen:
            seen.append(x)
    h.unmatched = seen
    return h


def daily_ratio(health: Health, key: str) -> float:
    """累计摄入相当于每日参考值的倍数。"""
    ref = DAILY_REFERENCE.get(key, 0)
    if not ref:
        return 0.0
    val = {
        "energyKcal": health.total_kcal, "protein": health.total_protein,
        "fat": health.total_fat, "carbohydrate": health.total_carbohydrate,
        "sodium": health.total_sodium,
    }.get(key, 0.0)
    return round(val / ref, 1)


# ====================================================================== #
# 省钱画像（依赖 query-order 的券与优惠明细）
# ====================================================================== #
@dataclass
class Savings:
    enriched_orders: int = 0         # 拿到了优惠明细的订单数
    total_original: float = 0.0      # 累计原价
    total_paid: float = 0.0          # 累计实付
    total_discount: float = 0.0      # 累计省下
    discount_rate: float = 0.0       # 省钱率 = 省下 / 原价
    coupon_used: int = 0             # 用券总次数
    coupon_top: list[tuple[str, int]] = field(default_factory=list)  # 最常用券
    best_deal: tuple[str, float] | None = None   # 单笔省最多 (描述, 金额)


def analyze_savings(orders: list[Order]) -> Savings:
    s = Savings()
    valid = [o for o in orders if not o.is_refunded]
    coupon_counter: Counter[str] = Counter()
    best: tuple[str, float] | None = None
    for o in valid:
        detail = bool(o.discount_amount or o.original_amount or o.coupon_names)
        if detail:
            s.enriched_orders += 1
            s.total_original += o.original_amount or o.amount
            s.total_discount += o.discount_amount
        s.total_paid += o.amount
        for name in o.coupon_names:
            coupon_counter[name] += 1
            s.coupon_used += 1
        if o.discount_amount and (best is None or o.discount_amount > best[1]):
            label = "、".join(o.coupon_names) or "优惠"
            best = (f"{o.date} {o.store_name}（{label}）", o.discount_amount)
    s.total_original = round(s.total_original, 2)
    s.total_paid = round(s.total_paid, 2)
    s.total_discount = round(s.total_discount, 2)
    s.discount_rate = round(s.total_discount / s.total_original, 3) if s.total_original else 0.0
    s.coupon_top = coupon_counter.most_common()
    s.best_deal = best
    return s


# ====================================================================== #
# 习惯画像（官方「我的常点」+ 订单节律）
# ====================================================================== #
@dataclass
class Habit:
    frequent_name: str = ""                 # 官方标记的「我的常点」
    frequent_components: list[str] = field(default_factory=list)
    peak_slot: str = ""                     # 最活跃时段
    slot_dist: dict[str, int] = field(default_factory=dict)
    weekday_dist: dict[str, int] = field(default_factory=dict)   # 周一~周日
    avg_items: float = 0.0                  # 单均商品件数
    order_span_days: int = 0                # 消费跨度（天）


_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def analyze_habit(orders: list[Order], frequent: MealInfo | None = None) -> Habit:
    from datetime import date
    h = Habit()
    if frequent:
        h.frequent_name = frequent.name or frequent.code
        h.frequent_components = list(frequent.components)
    valid = [o for o in orders if not o.is_refunded]
    if not valid:
        return h
    slots = Counter(o.meal_slot() for o in valid)
    h.slot_dist = dict(slots.most_common())
    h.peak_slot = slots.most_common(1)[0][0] if slots else ""
    wd = Counter()
    item_total = 0
    for o in valid:
        try:
            y, m, d = (int(x) for x in o.date.split("-"))
            wd[_WEEKDAYS[date(y, m, d).weekday()]] += 1
        except (ValueError, IndexError):
            pass
        item_total += sum(line.quantity for line in o.lines)
    h.weekday_dist = {w: wd[w] for w in _WEEKDAYS if w in wd}
    h.avg_items = round(item_total / len(valid), 2)
    dates = sorted(o.date for o in valid)
    try:
        y1, m1, d1 = (int(x) for x in dates[0].split("-"))
        y2, m2, d2 = (int(x) for x in dates[-1].split("-"))
        h.order_span_days = (date(y2, m2, d2) - date(y1, m1, d1)).days + 1
    except (ValueError, IndexError):
        pass
    return h


# ====================================================================== #
# 活动画像（campaign-calendar）
# ====================================================================== #
@dataclass
class Activity:
    current: list[CampaignEvent] = field(default_factory=list)     # 今天
    upcoming: list[CampaignEvent] = field(default_factory=list)    # 未来
    past_count: int = 0
    server_time: str = ""


def analyze_activity(campaigns: list[CampaignEvent], server_time: str = "") -> Activity:
    a = Activity(server_time=server_time)
    for c in campaigns:
        if c.stage == "today":
            a.current.append(c)
        elif c.stage == "future":
            a.upcoming.append(c)
        else:
            a.past_count += 1
    return a


# ====================================================================== #
# 权益画像
# ====================================================================== #
@dataclass
class Benefit:
    available_point: float = 0.0
    accumulative_point: float = 0.0
    used_point: float = 0.0
    expired_point: float = 0.0
    coupon_count: int = 0
    coupons_expiring: list[tuple[str, str]] = field(default_factory=list)  # (标题, 到期)
    mall_order_count: int = 0
    mall_points_spent: float = 0.0
    prize_count: int = 0
    prize_available: int = 0
    # —— 拓展：抽奖 / 可领券 / 积分兑换力 ——
    lottery_activity: str = ""
    lottery_prize_count: int = 0
    lottery_eligible: bool = False
    available_coupon_count: int = 0
    redeem_count: int = 0                 # 积分商城可兑换商品数
    redeem_affordable: int = 0            # 用现有积分够兑的数量
    redeem_cheapest: tuple[str, str] | None = None   # 最便宜的兑换项 (名称, 积分)
    store_coupon_count: int = 0           # 最爱门店可用券数


def _parse_expire(text: str):
    """把 '2026.10.16 23:59' 解析为可比较的 (y,m,d)。"""
    import re
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def analyze_benefit(arch: RawArchive, today: tuple[int, int, int] | None = None) -> Benefit:
    b = Benefit()
    if arch.account:
        b.available_point = arch.account.available_point
        b.accumulative_point = arch.account.accumulative_point
        b.used_point = arch.account.used_point
        b.expired_point = arch.account.expired_point
    b.coupon_count = len(arch.coupons)
    if today is not None:
        for cp in arch.coupons:
            d = _parse_expire(cp.available_until)
            if d is None:
                continue
            # 30 天内到期视为临期
            from datetime import date
            try:
                delta = (date(*d) - date(*today)).days
            except ValueError:
                continue
            if 0 <= delta <= 30:
                b.coupons_expiring.append((cp.title, cp.available_until))
    b.prize_count = len(arch.prizes)
    b.prize_available = sum(1 for p in arch.prizes if "可用" in (p.status_text or ""))
    b.mall_order_count = len(arch.mall_orders)
    for mo in arch.mall_orders:
        try:
            b.mall_points_spent += float(mo.points)
        except (TypeError, ValueError):
            pass
    b.mall_points_spent = round(b.mall_points_spent, 1)

    # —— 抽奖活动 ——
    if arch.lottery:
        b.lottery_activity = arch.lottery.activity_name
        b.lottery_prize_count = len(arch.lottery.prize_names)
        b.lottery_eligible = arch.lottery.eligible

    # —— 可领取券 ——
    b.available_coupon_count = len(arch.available_coupons)

    # —— 积分兑换力 ——
    b.redeem_count = len(arch.redeem_products)
    for p in arch.redeem_products:
        try:
            pt = float(p.points)
        except (TypeError, ValueError):
            continue
        if pt > 0 and pt <= b.available_point:
            b.redeem_affordable += 1
        if pt > 0 and (b.redeem_cheapest is None or pt < float(b.redeem_cheapest[1])):
            b.redeem_cheapest = (p.name, p.points)

    b.store_coupon_count = len(arch.store_coupons)
    return b
