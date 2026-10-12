"""点餐链路（ordering）：选店 → 选餐 → 算价 → 【确认护栏】 → 下单 → 验证。

严格遵守官方调用顺序（实测得出）：
    query-nearby-stores / delivery-query-stores   取门店（storeCode + beCode）
      → query-meals                               取商品 code
      → query-meal-detail                         补商品名称 / 组成
      → calculate-price                           算价，并拿到 takeWayList[].code
      → create-order                              下单（takeWayCode 取自上一跳）
      → query-order                               复核订单状态

安全护栏（真实下单不可逆）：
- ``place()`` 必须显式 ``confirm=True`` 才会真正调用 ``create-order``；
- 上层 CLI 默认 dry-run，只有用户敲了确认才走到 ``place(confirm=True)``。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .mcp_client import McdMcpClient, McpError
from .models import (
    CartItem, MealInfo, MenuItem, OrderQuote, PlacedOrder, TakeWay,
)


@dataclass
class Menu:
    """门店菜单。

    ``items`` 是「带图带价」的完整商品表（来自 query-meals 顶层 ``meals`` 字典）；
    ``categories`` 保留类目顺序（code 列表），``frequent_code`` 是「我的常点」。
    """

    categories: list[tuple[str, list[str]]] = field(default_factory=list)  # (分类名, [code])
    frequent_code: str = ""
    items: dict[str, MenuItem] = field(default_factory=dict)               # code -> MenuItem


@dataclass
class OrderingSession:
    """一次点餐的会话上下文。"""

    store_code: str = ""
    store_name: str = ""
    order_type: int = 1          # 1 到店 / 2 外送
    be_type: int = 1             # 1 到店自取 / 2 麦乐送 / 5 得来速 / 6 团餐
    be_code: str = ""
    address_id: str = ""
    take_way_code: str = ""      # 由 calculate-price 的 takeWayList 决定
    cart: list[CartItem] = field(default_factory=list)

    @property
    def mode_text(self) -> str:
        return {1: "到店取餐", 2: "麦乐送到家", 5: "得来速", 6: "企业团餐"}.get(self.be_type, "到店取餐")


# ---------------------------------------------------------------------- #
# 菜单 / 商品
# ---------------------------------------------------------------------- #
def _money(v, default: float = 0.0) -> float:
    """菜单价格字段统一转成「元」（顶层 meals 已是元；容错字符串/None）。"""
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return default


def load_menu(client: McdMcpClient, session: OrderingSession) -> Menu:
    """读取门店菜单。

    官方 ``query-meals`` 返回三块：``meals``（code→{name,image,currentPrice,
    originalPrice,canWithOrder}，带图带价）、``categories``（类目→code，带 tags）、
    ``frequent``（我的常点）。**三者都解析**，才能拿到带图带价、又带类目/常点的完整菜单。
    """
    data = client.call_tool("query-meals", {
        "storeCode": session.store_code, "orderType": session.order_type, "beType": session.be_type,
    })
    menu = Menu()
    if not isinstance(data, dict):
        return menu

    # ① 顶层 meals 字典：带图带价的完整商品表
    raw_items = data.get("meals")
    if isinstance(raw_items, dict):
        for code, v in raw_items.items():
            if not isinstance(v, dict):
                continue
            menu.items[str(code)] = MenuItem(
                code=str(code),
                name=v.get("name", "") or "",
                image=v.get("image", "") or "",
                price=_money(v.get("currentPrice")),
                original_price=_money(v.get("originalPrice")),
                can_order=bool(v.get("canWithOrder", True)),
            )

    # ② categories：类目顺序 + 商品标签（如「人气」）
    for cat in data.get("categories") or []:
        cname = cat.get("name", "商品")
        codes: list[str] = []
        for m in cat.get("meals") or []:
            code = str(m.get("code", ""))
            if not code:
                continue
            codes.append(code)
            tags = list(m.get("tags") or [])
            it = menu.items.get(code)
            if it is None:
                it = MenuItem(code=code)
                menu.items[code] = it
            if tags:
                it.tags = tags
            if not it.category:
                it.category = cname
        if codes:
            menu.categories.append((cname, codes))

    # ③ frequent：我的常点
    freq = data.get("frequent") or {}
    menu.frequent_code = str(freq.get("code", "") or "")
    if menu.frequent_code and menu.frequent_code in menu.items:
        menu.items[menu.frequent_code].tags = list(
            set(menu.items[menu.frequent_code].tags) | set(freq.get("tags") or ["我的常点"])
        )
    return menu


def describe(client: McdMcpClient, session: OrderingSession, code: str) -> MealInfo:
    """补全一个商品的名称与套餐组成（query-meal-detail）。"""
    data = client.call_tool("query-meal-detail", {
        "storeCode": session.store_code, "orderType": session.order_type,
        "beType": session.be_type, "code": code,
    })
    info = MealInfo(code=code)
    if isinstance(data, dict):
        info.name = data.get("name", "")
        info.image = data.get("image", "") or ""
        comps: list[str] = []
        for r in data.get("rounds") or []:
            for c in r.get("choices") or []:
                if c.get("name"):
                    comps.append(c["name"])
        info.components = comps
    return info


def menu_probe_fields(menu: Menu) -> dict:
    """给联调/自测看菜单解析质量的轻量统计。"""
    with_img = sum(1 for it in menu.items.values() if it.image)
    with_price = sum(1 for it in menu.items.values() if it.price)
    return {
        "items": len(menu.items),
        "with_image": with_img,
        "with_price": with_price,
        "categories": len(menu.categories),
        "frequent": menu.frequent_code,
    }


# ---------------------------------------------------------------------- #
# 算价（下单前置：拿 takeWayCode）
# ---------------------------------------------------------------------- #
def quote(client: McdMcpClient, session: OrderingSession, cart: list[CartItem],
          menu: Menu | None = None) -> OrderQuote:
    """调用 calculate-price，返回实付/原价/优惠 + 取餐方式列表。价格单位：分→元。"""
    if not cart:
        raise McpError("购物车为空，无法算价")
    items = []
    for i in cart:
        item = {"productCode": i.product_code, "quantity": i.quantity}
        # 券 id 是可选透传字段：带了就传给官方（如 McSolve 想指定某张券核销）
        if i.coupon_id:
            item["couponId"] = i.coupon_id
        items.append(item)
    data = client.call_tool("calculate-price", {
        "storeCode": session.store_code, "orderType": session.order_type,
        "beType": session.be_type, "items": items,
    })
    q = OrderQuote(items=list(cart), raw=data if isinstance(data, dict) else {})
    if isinstance(data, dict):
        q.paid = _fen_to_yuan(data.get("price"))
        q.original = _fen_to_yuan(data.get("originalPrice") or data.get("productOriginalPrice"))
        q.discount = _fen_to_yuan(data.get("discount"))
        for tw in data.get("takeWayList") or []:
            q.take_way_list.append(TakeWay(code=str(tw.get("code", "")), name=tw.get("title", "")))
        # 单次遍历完成：名称回填 + 编码校验 + 价/图补全
        names = {str(p.get("productCode")): p.get("productName", "") for p in data.get("productList") or []}
        for it in q.items:
            official = names.get(it.product_code, "")
            mi = menu.items.get(it.product_code) if menu is not None else None
            # 安全护栏：同一编码在菜单与官方算价里的名字必须一致，否则视为编码错位
            if official and mi and mi.name and official != mi.name:
                q.mismatches.append((it.product_code, mi.name, official))
            if not it.name:
                it.name = official or (mi.name if mi else "")
            if mi is not None:
                if not it.price and mi.price:
                    it.price = mi.price
                if not it.image and mi.image:
                    it.image = mi.image
    return q


# ---------------------------------------------------------------------- #
# 下单（真实、不可逆 —— 必须 confirm）
# ---------------------------------------------------------------------- #
def place(client: McdMcpClient, session: OrderingSession, cart: list[CartItem],
          take_way_code: str = "", *, confirm: bool = False,
          need_tableware: bool = False, remark: str = "") -> PlacedOrder:
    """真实创建订单。**必须显式 confirm=True**，否则直接拒绝。"""
    if not confirm:
        raise McpError("安全护栏：未确认（confirm=False），已拒绝下单。请先核对明细并显式确认。")
    if not cart:
        raise McpError("购物车为空，无法下单")
    args: dict = {
        "storeCode": session.store_code,
        "orderType": session.order_type,
        "beType": session.be_type,
        "items": [{"productCode": i.product_code, "quantity": i.quantity} for i in cart],
        "needTableware": need_tableware,
    }
    if session.order_type == 1 and take_way_code:
        args["takeWayCode"] = take_way_code
    if session.be_code:
        args["beCode"] = session.be_code
    if session.order_type == 2:
        if session.address_id:
            args["addressId"] = session.address_id
        if remark:
            args["remark"] = remark
    data = client.call_tool("create-order", args)
    placed = PlacedOrder(ok=True, store_name=session.store_name, store_code=session.store_code)
    if isinstance(data, dict):
        placed.order_id = str(
            data.get("orderId") or data.get("orderNo") or data.get("tradeOrderId")
            or (data.get("order") or {}).get("orderId", "")
        )
        placed.status = data.get("orderStatus") or data.get("status") or data.get("orderStatusText", "") or ""
        placed.create_time = data.get("createTime", "") or ""
        placed.paid = _fen_to_yuan(data.get("price") or data.get("realTotalAmount"))
    placed.take_way = take_way_code
    if not placed.order_id:
        placed.message = "已提交，但返回中未解析到订单号，请到官方 App 确认。"
    return placed


def verify(client: McdMcpClient, order_id: str) -> dict:
    """下单后复核订单状态。"""
    data = client.call_tool("query-order", {"orderId": order_id})
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------- #
# 工具
# ---------------------------------------------------------------------- #
def _fen_to_yuan(v) -> float:
    try:
        return round(float(v) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0
