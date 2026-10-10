"""数据采集：把 mcd-mcp 的「订单后 + 权益 + 商城 + 场景 + 营销」工具汇聚成一份档案原始数据。

覆盖工具（按域）：
- 订单域   order-list, query-order
- 权益域   query-my-account, query-my-coupons, query-my-prizes,
           query-lottery-info, available-coupons
- 商城域   mall-order-list, mall-order-detail, mall-points-products
- 场景域   query-nearby-stores, delivery-query-addresses, delivery-query-stores,
           query-meals, query-meal-detail, query-store-coupons, calculate-price
- 营销域   campaign-calendar, now-time-info

设计原则：
1. 只调用「只读」工具——档案是复盘，绝不替你下单/取消/抽奖/领券；
2. 任一工具失败不致命（记入 errors 与 tool_calls），其余照常；
3. 全部失败时回退本地脱敏样例快照，保证离线可复现。
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import (
    AvailableCoupon, CampaignEvent, Coupon, DeliveryAddress, MealInfo, Order,
    PriceQuote, Prize, RawArchive, RedeemableProduct, StoreInfo, ToolCall,
    enrich_order, parse_account, parse_address, parse_available_coupon,
    parse_campaign, parse_coupon, parse_lottery, parse_mall_order, parse_order,
    parse_prize, parse_redeem_product, parse_store,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ORDERS_SAMPLE = DATA_DIR / "orders_sample.json"
ARCHIVE_SAMPLE = DATA_DIR / "archive_sample.json"
SCENE_SAMPLE = DATA_DIR / "scene_sample.json"
MARKETING_SAMPLE = DATA_DIR / "marketing_sample.json"

MAX_ENRICH = 40          # 最多用 query-order 补全多少张订单
MAX_MALL_DETAIL = 6      # 最多补全多少张商城订单详情


# ---------------------------------------------------------------------- #
# 结构拆包工具
# ---------------------------------------------------------------------- #
def _as_order_list(data) -> list:
    """order-list 返回 {'list': [...]}，兼容直接返回列表。"""
    if isinstance(data, dict):
        return data.get("list") or []
    if isinstance(data, list):
        return data
    return []


def _as_mall_list(data) -> list:
    """mall-order-list 返回 ``[{hasNext, lastId, list:[...]}]``（包一层），需拆包。"""
    if isinstance(data, list) and data and isinstance(data[0], dict) and "list" in data[0]:
        return data[0].get("list") or []
    if isinstance(data, dict):
        return data.get("list") or []
    if isinstance(data, list):
        return data
    return []


def _fav_store_params(orders: list[Order]) -> tuple[str, str, str]:
    """从订单推断「最常去的门店」及其下单场景参数 (storeCode, orderType, beType)。"""
    from collections import Counter
    valid = [o for o in orders if not o.is_refunded and o.store_code]
    if not valid:
        return "", "1", "1"
    code = Counter(o.store_code for o in valid).most_common(1)[0][0]
    same = [o for o in valid if o.store_code == code]
    order_type = next((o.order_type for o in same if o.order_type in {"1", "2"}), "1")
    be_type = next((o.be_type for o in same if o.be_type in {"1", "5", "2", "6"}), "1")
    return code, order_type, be_type


# ---------------------------------------------------------------------- #
# 采集入口
# ---------------------------------------------------------------------- #
def collect(client=None, use_remote: bool = True) -> RawArchive:
    """采集档案数据。优先联网；无 client 或失败时回退样例快照。"""
    if use_remote and client is not None:
        try:
            return _collect_remote(client)
        except Exception as exc:  # noqa: BLE001
            arch = _collect_sample()
            arch.errors.append(f"联网采集失败，已回退样例：{exc}")
            arch.source = "snapshot"
            return arch
    return _collect_sample()


def _collect_remote(client) -> RawArchive:
    arch = RawArchive(source="remote")
    log: dict[str, dict] = {}

    def rec(tool: str, ok: bool, n: int = 0, note: str = "") -> None:
        e = log.setdefault(tool, {"ok": True, "count": 0, "note": ""})
        e["ok"] = e["ok"] and ok
        e["count"] += n
        if not ok and note:
            e["note"] = note

    def safe(tool: str, fn, args: dict | None = None, count_flag: bool = True) -> object | None:
        try:
            data = client.call_tool(tool, args)
        except Exception as exc:  # noqa: BLE001
            arch.errors.append(f"{tool}: {exc}")
            rec(tool, False, 0, str(exc)[:120])
            return None
        try:
            n = fn(data)
        except Exception as exc:  # noqa: BLE001 —— 解析失败亦记账，不致命
            arch.errors.append(f"{tool}(解析): {exc}")
            rec(tool, False, 0, f"解析失败: {str(exc)[:80]}")
            return data
        rec(tool, True, int(n) if (count_flag and n) else 0)
        return data

    # ---- 1) 订单域 ------------------------------------------------------ #
    def _take_orders(d):
        items = _as_order_list(d)
        arch.orders.extend(parse_order(o) for o in items)
        return len(items)

    safe("order-list", _take_orders)

    # 用 query-order 逐单补全「券 / 优惠 / 餐方式 / 门店地址」
    enriched = 0
    for o in arch.orders[:MAX_ENRICH]:
        if not o.order_id:
            continue
        def _enr(d, _o=o):
            if isinstance(d, dict):
                enrich_order(_o, d)
                return 1
            return 0
        if safe("query-order", _enr, {"orderId": o.order_id}) is not None:
            enriched += 1
    # 上面对同一工具多次记账，这里合并为「补全了多少单」
    if "query-order" in log:
        log["query-order"]["count"] = enriched

    # ---- 2) 权益域 ------------------------------------------------------ #
    safe("query-my-account", lambda d: setattr(arch, "account", parse_account(d)) or (1 if d else 0))
    safe("query-my-coupons", lambda d: (arch.coupons.extend(
        parse_coupon(c) for c in (d.get("coupons") or [])) or len(arch.coupons)) if isinstance(d, dict) else 0)
    safe("query-my-prizes", lambda d: (arch.prizes.extend(
        parse_prize(p) for p in (d.get("prizes") or [])) or len(arch.prizes)) if isinstance(d, dict) else 0)
    safe("query-lottery-info", lambda d: (setattr(arch, "lottery", parse_lottery(d)) or 1) if isinstance(d, dict) else 0)
    safe("available-coupons", lambda d: (arch.available_coupons.extend(
        parse_available_coupon(c) for c in (d or [])) or len(arch.available_coupons)) if isinstance(d, list) else 0)

    # ---- 3) 商城域 ------------------------------------------------------ #
    def _take_mall(d):
        items = _as_mall_list(d)
        arch.mall_orders.extend(parse_mall_order(o) for o in items)
        return len(items)

    safe("mall-order-list", _take_mall)

    # 商城订单详情：补全 createTime / 实付积分
    if arch.mall_orders:
        for mo in arch.mall_orders[:MAX_MALL_DETAIL]:
            if not mo.order_id:
                continue
            def _md(d, _mo=mo):
                if isinstance(d, dict):
                    _mo.create_time = d.get("createTime", "") or _mo.create_time
                    _mo.real_points = str(d.get("realTotalPoints", "")) or _mo.real_points
                    return 1
                return 0
            safe("mall-order-detail", _md, {"orderId": mo.order_id})
    if "mall-order-detail" in log and log["mall-order-detail"]["ok"]:
        log["mall-order-detail"]["count"] = min(len(arch.mall_orders), MAX_MALL_DETAIL)

    # 积分商城可兑换商品
    safe("mall-points-products", lambda d: (arch.redeem_products.extend(
        parse_redeem_product(p) for p in (d or [])) or len(arch.redeem_products)) if isinstance(d, list) else 0)

    # ---- 4) 场景域 ------------------------------------------------------ #
    def _take_stores(d):
        items = _as_order_list(d)
        arch.nearby_stores.extend(parse_store(s) for s in items)
        return len(items)

    safe("query-nearby-stores", _take_stores, {"beType": 1, "searchType": 1})  # searchType=1：收藏餐厅

    def _take_addr(d):
        items = (d or {}).get("addresses") or []
        arch.addresses.extend(parse_address(a) for a in items)
        return len(items)

    safe("delivery-query-addresses", _take_addr)

    # 用第一个地址查可配送门店
    if arch.addresses:
        aid = arch.addresses[0].address_id
        def _dqs(d):
            items = _as_order_list(d)
            for s in items:
                info = parse_store(s)
                if info.code and info.code not in {x.code for x in arch.nearby_stores}:
                    arch.nearby_stores.append(info)
            return len(items)
        safe("delivery-query-stores", _dqs, {"addressId": aid, "beType": 2})

    # 最爱门店：菜单 + 常点 + 门店可用券 + 算价
    sc, order_type, be_type = _fav_store_params(arch.orders)
    if sc:
        params = {"storeCode": sc, "orderType": int(order_type), "beType": int(be_type)}

        def _take_meals(d):
            if not isinstance(d, dict):
                return 0
            freq = d.get("frequent") or {}
            if freq.get("code"):
                arch.frequent_meal = MealInfo(code=str(freq["code"]), tags=freq.get("tags", []) or [])
            n = 0
            for cat in d.get("categories") or []:
                for m in cat.get("meals") or []:
                    arch.favorite_store_meals.append(
                        MealInfo(code=str(m.get("code", "")), tags=m.get("tags", []) or []))
                    n += 1
            return n

        safe("query-meals", _take_meals, params)

        # 常点的名称与组成（第二跳）
        if arch.frequent_meal and arch.frequent_meal.code:
            def _mdet(d):
                if isinstance(d, dict) and d.get("name"):
                    arch.frequent_meal.name = d.get("name", "")
                    comps = []
                    for r in d.get("rounds") or []:
                        comps.extend(c.get("name", "") for c in (r.get("choices") or []) if c.get("name"))
                    arch.frequent_meal.components = comps
                    return 1
                return 0
            safe("query-meal-detail", _mdet, {**params, "code": arch.frequent_meal.code})

        def _take_store_coupons(d):
            items = _as_order_list(d)
            titles = []
            for c in items:
                t = c.get("title", "")
                if t and t not in titles:
                    titles.append(t)
            arch.store_coupons = titles
            return len(items)

        safe("query-store-coupons", _take_store_coupons, params)

        # 算价：按官方「我的常点」预估当前价格
        if arch.frequent_meal and arch.frequent_meal.code:
            def _price(d):
                if isinstance(d, dict) and d.get("price") is not None:
                    arch.price_quote = PriceQuote(
                        product_name=arch.frequent_meal.name or arch.frequent_meal.code,
                        price=float(d.get("price") or 0),
                        original_price=float(d.get("originalPrice") or 0),
                        discount=float(d.get("discount") or 0),
                    )
                    return 1
                return 0
            safe("calculate-price", _price, {**params, "items": [{"productCode": arch.frequent_meal.code, "quantity": 1}]})

    # ---- 5) 营销域 ------------------------------------------------------ #
    def _take_campaigns(d):
        if not isinstance(d, dict):
            return 0
        current = (d.get("currentTime") or "")[:10]
        n = 0
        for day in d.get("dailyList") or []:
            date = day.get("date", "")
            if day.get("today"):
                stage = "today"
            elif date and current and date < current:
                stage = "past"
            else:
                stage = "future"
            for ev in day.get("events") or []:
                ce = parse_campaign(date, ev, stage)
                if ce.title:
                    arch.campaigns.append(ce)
                    n += 1
        return n

    safe("campaign-calendar", _take_campaigns)
    safe("now-time-info", lambda d: (setattr(arch, "server_time", (d or {}).get("formatted", "")) or 1) if isinstance(d, dict) else 0)

    # ---- 汇总日志 ------------------------------------------------------- #
    order = ["order-list", "query-order", "query-my-account", "query-my-coupons",
             "query-my-prizes", "query-lottery-info", "available-coupons",
             "mall-order-list", "mall-order-detail", "mall-points-products",
             "query-nearby-stores", "delivery-query-addresses", "delivery-query-stores",
             "query-meals", "query-meal-detail", "query-store-coupons", "calculate-price",
             "campaign-calendar", "now-time-info"]
    arch.tool_calls = [
        ToolCall(name=t, ok=log[t]["ok"], count=log[t]["count"], note=log[t]["note"])
        for t in order if t in log
    ]

    if not arch.orders and not arch.account:
        raise RuntimeError("所有订单后工具均无数据")
    return arch


# ---------------------------------------------------------------------- #
# 离线样例
# ---------------------------------------------------------------------- #
def _collect_sample() -> RawArchive:
    """离线样例：读取随项目附带的脱敏样例数据。"""
    arch = RawArchive(source="snapshot")
    try:
        arch.orders = [parse_order(o) for o in json.loads(ORDERS_SAMPLE.read_text(encoding="utf-8"))]
    except Exception as exc:  # noqa: BLE001
        arch.errors.append(f"orders_sample: {exc}")
    try:
        data = json.loads(ARCHIVE_SAMPLE.read_text(encoding="utf-8"))
        arch.account = parse_account(data.get("account", {}))
        arch.coupons = [parse_coupon(c) for c in data.get("coupons", [])]
        arch.prizes = [parse_prize(p) for p in data.get("prizes", [])]
        arch.mall_orders = [parse_mall_order(o) for o in data.get("mallOrders", [])]
        if data.get("lottery"):
            arch.lottery = parse_lottery(data["lottery"])
        arch.available_coupons = [parse_available_coupon(c) for c in data.get("availableCoupons", [])]
        arch.redeem_products = [parse_redeem_product(p) for p in data.get("redeemProducts", [])]
    except Exception as exc:  # noqa: BLE001
        arch.errors.append(f"archive_sample: {exc}")
    try:
        scene = json.loads(SCENE_SAMPLE.read_text(encoding="utf-8"))
        arch.nearby_stores = [parse_store(s) for s in scene.get("stores", [])]
        arch.addresses = [parse_address(a) for a in scene.get("addresses", [])]
        arch.store_coupons = scene.get("storeCoupons", [])
        if scene.get("frequentMeal"):
            fm = scene["frequentMeal"]
            arch.frequent_meal = MealInfo(code=fm.get("code", ""), name=fm.get("name", ""),
                                          tags=fm.get("tags", []), components=fm.get("components", []))
        if scene.get("priceQuote"):
            pq = scene["priceQuote"]
            arch.price_quote = PriceQuote(product_name=pq.get("productName", ""),
                                          price=pq.get("price", 0), original_price=pq.get("originalPrice", 0),
                                          discount=pq.get("discount", 0))
        arch.favorite_store_meals = [MealInfo(code=m.get("code", ""), tags=m.get("tags", []))
                                     for m in scene.get("menu", [])]
    except Exception as exc:  # noqa: BLE001
        arch.errors.append(f"scene_sample: {exc}")
    try:
        mk = json.loads(MARKETING_SAMPLE.read_text(encoding="utf-8"))
        arch.campaigns = [CampaignEvent(**c) for c in mk.get("campaigns", [])]
        arch.server_time = mk.get("serverTime", "")
    except Exception as exc:  # noqa: BLE001
        arch.errors.append(f"marketing_sample: {exc}")
    return arch
