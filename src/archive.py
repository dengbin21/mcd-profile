"""档案聚合：采集 → 分析 → 人格，产出一个完整的 McProfile 对象。

同时汇总「工具覆盖清单」——本次到底调用了官方 35 个工具中的哪些、各自产出多少条，
让「用了多少 MCP 能力」这件事本身可被看见、可被复盘。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from .analysis import (
    Activity, Benefit, Consumption, Habit, Health, Savings,
    analyze_activity, analyze_benefit, analyze_consumption, analyze_habit,
    analyze_health, analyze_savings,
)
from .models import CartItem, MealReport, RawArchive, ToolCall
from .nutrition import NutritionIndex, fetch_foods, load_snapshot
from .persona import Persona, build_persona
from .sources import DATA_DIR, collect

MEAL_REPORT_SAMPLE = DATA_DIR / "meal_report_sample.json"

# 本作品「合理可用」的只读工具集（写操作与团餐专用工具刻意不纳入）。
POTENTIAL_TOOLS: list[str] = [
    # 订单
    "order-list", "query-order",
    # 权益
    "query-my-account", "query-my-coupons", "query-my-prizes",
    "query-lottery-info", "available-coupons",
    # 商城
    "mall-order-list", "mall-order-detail", "mall-points-products",
    # 场景
    "query-nearby-stores", "delivery-query-addresses", "delivery-query-stores",
    "query-meals", "query-meal-detail", "query-store-coupons", "calculate-price",
    # 营销
    "campaign-calendar", "now-time-info",
    # 营养
    "list-nutrition-foods",
    # 点餐闭环（唯一写操作：仅在用户显式确认后调用）
    "create-order",
]


@dataclass
class Archive:
    consumption: Consumption
    health: Health
    benefit: Benefit
    savings: Savings
    habit: Habit
    activity: Activity
    persona: Persona
    raw: RawArchive
    nutrition_source: str = "snapshot"
    meta: dict = field(default_factory=dict)
    order_report: MealReport | None = None     # 本次点餐战报（点餐闭环产物）

    @property
    def errors(self) -> list[str]:
        return self.raw.errors


def _today_tuple(arch: RawArchive) -> tuple[int, int, int]:
    """优先用官方 now-time-info 的服务器时间做「今天」，保证与官方一致。"""
    ts = arch.server_time
    if ts:
        try:
            y, m, d = ts.split(" ")[0].split("-")
            return int(y), int(m), int(d)
        except (ValueError, IndexError):
            pass
    return date.today().timetuple()[:3]


def build_archive(client=None, use_remote: bool = True,
                  order_report: MealReport | None = None,
                  order_ctx=None) -> Archive:
    """采集 + 分析，返回完整档案。

    当传入 ``order_report``（本次点餐战报）时，档案将变为「战报 + 历史画像」合体。
    ``order_ctx`` 为 ``(session, quote, placed)``，用于在采集内部（复用营养库）生成战报，
    免去调用方二次采集营养库。
    """
    raw = collect(client, use_remote=use_remote)
    foods, nsrc = fetch_foods(client if use_remote else None, use_remote=use_remote)
    index = NutritionIndex(foods)

    # 营养库与业务工具分开采集，这里补一条覆盖记录，让清单完整
    if nsrc == "remote" and not any(t.name == "list-nutrition-foods" for t in raw.tool_calls):
        raw.tool_calls.append(ToolCall(name="list-nutrition-foods", ok=True, count=len(foods)))

    # 点餐闭环：用营养库把「这一单」组装成战报，并把 create-order 计入工具覆盖
    if order_report is None and order_ctx is not None:
        session, quote, placed = order_ctx
        order_report = build_meal_report(
            session, quote, placed=placed, index=index, server_time=raw.server_time,
        )
    if order_ctx is not None:
        placed = order_ctx[2]
        if placed is not None and not any(t.name == "create-order" for t in raw.tool_calls):
            raw.tool_calls.append(ToolCall(
                name="create-order", ok=placed.ok, count=1,
                note="" if placed.ok else (placed.message or "下单未成功"),
            ))

    cons = analyze_consumption(raw.orders)
    health = analyze_health(raw.orders, index)
    benefit = analyze_benefit(raw, today=_today_tuple(raw))
    savings = analyze_savings(raw.orders)
    habit = analyze_habit(raw.orders, raw.frequent_meal)
    activity = analyze_activity(raw.campaigns, raw.server_time)
    # benefit / habit 一并交给人格引擎：无消费记录时也有「常点/券包/新兵」的诚实兜底
    persona = build_persona(raw.orders, cons, health, savings,
                            benefit=benefit, frequent_name=habit.frequent_name)

    called = [t.name for t in raw.tool_calls]
    ok = [t.name for t in raw.tool_calls if t.ok]
    return Archive(
        consumption=cons, health=health, benefit=benefit, savings=savings,
        habit=habit, activity=activity, persona=persona, raw=raw,
        nutrition_source=nsrc,
        order_report=order_report,
        meta={
            "order_total": len(raw.orders),
            "data_source": raw.source,
            "has_account": raw.account is not None,
            "tools_called": len(called),
            "tools_ok": len(ok),
            # POTENTIAL_TOOLS 已含 list-nutrition-foods（21 个），不要再 +1
            "tools_potential": len(POTENTIAL_TOOLS),
            "server_time": raw.server_time,
        },
    )


def build_meal_report(session, quote, placed=None, index=None, server_time: str = "") -> MealReport:
    """把「算价结果 +（可选）下单结果」组装成本次点餐战报。"""
    take_way = ""
    for tw in quote.take_way_list:
        if tw.code == session.take_way_code:
            take_way = tw.name
            break
    mr = MealReport(
        store_name=session.store_name, store_code=session.store_code,
        created_at=server_time or "", take_way=take_way,
        items=list(quote.items),
        original_amount=quote.original, paid_amount=quote.paid, discount_amount=quote.discount,
        order_id=(placed.order_id if placed else ""),
        status=(placed.status if placed else ""),
        placed=bool(placed and placed.ok),
    )
    # 用官方营养库算这一单的热量 / 钠 / 蛋白
    if index is not None:
        for it in mr.items:
            if not it.name:
                continue
            food = index.match(it.name)
            if food is None:
                continue
            mr.kcal += food.energyKcal * it.quantity
            mr.sodium += food.sodium * it.quantity
            mr.protein += food.protein * it.quantity
    return mr


def load_meal_report_sample() -> MealReport | None:
    """读取随项目附带的脱敏「本次点餐战报」样例，供离线 demo 展示合体档案。"""
    try:
        d = json.loads(MEAL_REPORT_SAMPLE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    mr = MealReport(
        store_name=d.get("storeName", ""), store_code=d.get("storeCode", ""),
        created_at=d.get("createdAt", ""), take_way=d.get("takeWay", ""),
        items=[CartItem(product_code=i.get("productCode", ""), name=i.get("name", ""),
                        quantity=int(i.get("quantity", 1) or 1)) for i in d.get("items", [])],
        original_amount=float(d.get("originalAmount", 0) or 0),
        paid_amount=float(d.get("paidAmount", 0) or 0),
        discount_amount=float(d.get("discountAmount", 0) or 0),
        order_id=d.get("orderId", ""), status=d.get("status", ""),
        placed=bool(d.get("placed", False)),
    )
    index = NutritionIndex(load_snapshot())
    for it in mr.items:
        food = index.match(it.name) if it.name else None
        if food is None:
            continue
        mr.kcal += food.energyKcal * it.quantity
        mr.sodium += food.sodium * it.quantity
        mr.protein += food.protein * it.quantity
    return mr
