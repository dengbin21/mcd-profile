"""领域模型：把 mcd-mcp 各工具返回的原始数据归一化为档案可用的结构。

覆盖域：
- 订单（order-list / query-order）
- 权益（query-my-account / query-my-coupons / query-my-prizes）
- 商城（mall-order-list / mall-order-detail / mall-points-products）
- 营销（available-coupons / campaign-calendar / now-time-info）
- 场景（query-nearby-stores / query-meals / delivery-query-addresses ...）
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------- #
# 订单
# ---------------------------------------------------------------------- #
@dataclass
class ComboItem:
    """套餐内单个组成商品（来自 comboItemList）。"""

    name: str
    quantity: int = 1


@dataclass
class OrderLine:
    """订单行：一个商品（可能是单品，也可能是套餐）。"""

    product_code: str
    product_name: str
    quantity: int = 1
    combo: list[ComboItem] = field(default_factory=list)

    @property
    def is_combo(self) -> bool:
        return bool(self.combo)


@dataclass
class Order:
    order_id: str
    created_at: str               # "2026-10-09 08:46:54"
    store_code: str
    store_name: str
    order_status: str             # 订单已完成 / 整单退款 / ...
    amount: float                 # 实付金额（元）
    be_type: str = "1"
    order_type: str = "1"
    lines: list[OrderLine] = field(default_factory=list)

    # ---- query-order 补全的详情字段（order-list 不含）----
    original_amount: float = 0.0      # 原价
    discount_amount: float = 0.0      # 优惠总额
    coupon_names: list[str] = field(default_factory=list)  # 用到的券
    take_way: str = ""                # 堂食 / 外带 / 麦乐送
    store_address: str = ""

    # ---- 便捷派生 ----
    @property
    def is_refunded(self) -> bool:
        return "退款" in self.order_status

    @property
    def date(self) -> str:
        return self.created_at.split(" ")[0]

    @property
    def hour(self) -> int:
        try:
            return int(self.created_at.split(" ")[1].split(":")[0])
        except (IndexError, ValueError):
            return -1

    def meal_slot(self) -> str:
        h = self.hour
        if 5 <= h < 10:
            return "早餐"
        if 10 <= h < 14:
            return "午餐"
        if 14 <= h < 17:
            return "下午茶"
        if 17 <= h < 21:
            return "晚餐"
        return "深夜"

    def flat_items(self) -> list[tuple[str, int]]:
        """展开为可计营养的 (名称, 数量) 列表：套餐拆成组合商品，单品用其名称。"""
        out: list[tuple[str, int]] = []
        for line in self.lines:
            if line.combo:
                for c in line.combo:
                    out.append((c.name, c.quantity))
            else:
                out.append((line.product_name, line.quantity))
        return out

    def product_names(self) -> list[str]:
        """订单涉及的顶层商品名（含套餐名），用于统计复购/口味。"""
        return [line.product_name for line in self.lines]


# ---------------------------------------------------------------------- #
# 权益
# ---------------------------------------------------------------------- #
@dataclass
class Account:
    available_point: float = 0.0
    accumulative_point: float = 0.0
    used_point: float = 0.0
    expired_point: float = 0.0


@dataclass
class Coupon:
    title: str
    available_until: str = ""     # 到期时间文本
    is_delivery: bool = False
    coupon_id: str = ""           # 券标识（官方卡包接口通常不返回，防御性保留）


@dataclass
class Prize:
    name: str
    type_text: str = ""
    status_text: str = ""
    record_time: str = ""


@dataclass
class MallOrder:
    spu_name: str
    points: str
    status_title: str
    order_id: str = ""
    spu_id: str = ""
    create_time: str = ""
    real_points: str = ""


@dataclass
class LotteryInfo:
    """积分抽奖活动（query-lottery-info）。"""

    activity_name: str = ""
    status_text: str = ""
    end_time: str = ""
    draw_point: str = ""
    available_point: float = 0.0
    eligible: bool = False
    prize_names: list[str] = field(default_factory=list)


@dataclass
class AvailableCoupon:
    """麦麦省可领取券（available-coupons）。"""

    name: str
    status: str = ""
    label: str = ""


@dataclass
class RedeemableProduct:
    """积分商城可兑换商品（mall-points-products）。"""

    spu_id: str
    name: str
    points: str = ""
    price: str = ""
    category: str = ""
    shop_id: str = ""
    selling: str = ""


# ---------------------------------------------------------------------- #
# 场景（门店 / 地址 / 餐品 / 活动）
# ---------------------------------------------------------------------- #
@dataclass
class StoreInfo:
    """门店信息（query-nearby-stores / delivery-query-stores）。"""

    code: str
    name: str
    address: str = ""
    distance: str = ""


@dataclass
class DeliveryAddress:
    """外送地址（delivery-query-addresses），保留脱敏文本。"""

    address_id: str
    contact: str = ""
    phone: str = ""
    full_address: str = ""


@dataclass
class MealInfo:
    """餐品（query-meals：code + 标签；query-meal-detail：名称 + 组成 + 图片）。"""

    code: str
    name: str = ""
    tags: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    in_store: bool = True
    image: str = ""              # 商品图 URL
    price: float = 0.0           # 现价（元）
    original_price: float = 0.0  # 原价（元）


@dataclass
class MenuItem:
    """菜单商品（query-meals 顶层 ``meals`` 字典：名称 / 图片 / 价格 一次到手）。

    这是菜单里「带图带价」的完整商品，用于菜单展示与选餐；
    ``query-meal-detail`` 只在需要套餐组成 / 改菜时才补全。
    """

    code: str
    name: str = ""
    image: str = ""
    price: float = 0.0            # 现价（元）
    original_price: float = 0.0   # 原价（元）
    tags: list[str] = field(default_factory=list)
    category: str = ""
    can_order: bool = True        # 官方 canWithOrder

    @property
    def discount(self) -> float:
        return round(self.original_price - self.price, 2) if self.original_price > self.price else 0.0

    @property
    def discount_rate(self) -> float:
        return round(self.discount / self.original_price, 3) if self.original_price else 0.0


@dataclass
class CampaignEvent:
    """营销活动（campaign-calendar）。"""

    date: str
    title: str
    content: str = ""
    stage: str = "future"      # past / today / future


@dataclass
class PriceQuote:
    """算价结果（calculate-price）。"""

    product_name: str = ""
    price: float = 0.0          # 分
    original_price: float = 0.0
    discount: float = 0.0
    take_way_list: list["TakeWay"] = field(default_factory=list)   # 取餐方式（下单必填 takeWayCode）


# ---------------------------------------------------------------------- #
# 点餐链路（ordering）
# ---------------------------------------------------------------------- #
@dataclass
class TakeWay:
    """取餐方式（来自 calculate-price 的 takeWayList）。"""

    code: str
    name: str = ""


@dataclass
class CartItem:
    """购物车单品。"""

    product_code: str
    name: str = ""
    quantity: int = 1
    price: float = 0.0          # 单价（元，来自菜单）
    is_combo: bool = False
    image: str = ""             # 商品图 URL
    image_local: str = ""       # 已下载到本地的缩略图路径（供 PNG 嵌入 / HTML 内联）
    coupon_id: str = ""         # 该单品要核销的券 id（可选；算价时透传 calculate-price）


@dataclass
class OrderQuote:
    """购物车算价结果。"""

    paid: float = 0.0           # 实付（元）
    original: float = 0.0       # 原价（元）
    discount: float = 0.0       # 优惠（元）
    items: list[CartItem] = field(default_factory=list)
    take_way_list: list[TakeWay] = field(default_factory=list)
    # 安全护栏：菜单名与官方算价名不一致的商品（code, 菜单名, 官方名），
    # 非空时 CLI 会拒绝下单，防止编码错位导致「点了 A 送到 B」。
    mismatches: list[tuple[str, str, str]] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def discount_rate(self) -> float:
        return round(self.discount / self.original, 3) if self.original else 0.0


@dataclass
class PlacedOrder:
    """真实下单结果（create-order）。"""

    ok: bool = False
    order_id: str = ""
    status: str = ""
    create_time: str = ""
    store_name: str = ""
    store_code: str = ""
    paid: float = 0.0
    take_way: str = ""
    message: str = ""


@dataclass
class MealReport:
    """本次点餐战报——点餐闭环的产物，用于分享档案顶部。"""

    store_name: str = ""
    store_code: str = ""
    created_at: str = ""
    take_way: str = ""
    items: list[CartItem] = field(default_factory=list)
    original_amount: float = 0.0
    paid_amount: float = 0.0
    discount_amount: float = 0.0
    kcal: float = 0.0
    sodium: float = 0.0
    protein: float = 0.0
    order_id: str = ""
    status: str = ""
    placed: bool = False        # 是否真实下单成功（False=仅算价预览）

    @property
    def discount_rate(self) -> float:
        return round(self.discount_amount / self.original_amount, 3) if self.original_amount else 0.0

    @property
    def bigmac_equiv(self) -> float:
        return round(self.kcal / 550.0, 1) if self.kcal else 0.0

    @property
    def item_count(self) -> int:
        return sum(i.quantity for i in self.items)


# ---------------------------------------------------------------------- #
# 工具调用日志（用于「工具覆盖清单」）
# ---------------------------------------------------------------------- #
@dataclass
class ToolCall:
    name: str
    ok: bool = True
    count: int = 0             # 该工具贡献的记录数
    note: str = ""


# ---------------------------------------------------------------------- #
# 汇总
# ---------------------------------------------------------------------- #
@dataclass
class RawArchive:
    """一次采集得到的全量原始数据（可用于离线复现）。"""

    # 订单域
    orders: list[Order] = field(default_factory=list)
    # 权益域
    account: Account | None = None
    coupons: list[Coupon] = field(default_factory=list)
    prizes: list[Prize] = field(default_factory=list)
    lottery: LotteryInfo | None = None
    available_coupons: list[AvailableCoupon] = field(default_factory=list)
    # 商城域
    mall_orders: list[MallOrder] = field(default_factory=list)
    redeem_products: list[RedeemableProduct] = field(default_factory=list)
    # 场景域
    nearby_stores: list[StoreInfo] = field(default_factory=list)
    addresses: list[DeliveryAddress] = field(default_factory=list)
    favorite_store_meals: list[MealInfo] = field(default_factory=list)
    frequent_meal: MealInfo | None = None      # 官方「我的常点」
    store_coupons: list[str] = field(default_factory=list)   # 门店可用券标题
    price_quote: PriceQuote | None = None
    # 营销域
    campaigns: list[CampaignEvent] = field(default_factory=list)
    server_time: str = ""
    # 元信息
    source: str = "snapshot"      # remote / snapshot / mixed
    errors: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)


# ---------------------------------------------------------------------- #
# 解析函数
# ---------------------------------------------------------------------- #
def _to_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def parse_order(raw: dict) -> Order:
    lines: list[OrderLine] = []
    for p in raw.get("orderProductList", []) or []:
        combo = [
            ComboItem(name=c.get("name") or c.get("itemName", ""),
                      quantity=int(c.get("quantity", c.get("itemQuantity", 1)) or 1))
            for c in (p.get("comboItemList") or [])
        ]
        lines.append(
            OrderLine(
                product_code=str(p.get("productCode", "")),
                product_name=p.get("productName", ""),
                quantity=int(p.get("quantity", 1) or 1),
                combo=combo,
            )
        )
    return Order(
        order_id=str(raw.get("orderId", "")),
        created_at=raw.get("createTime", ""),
        store_code=str(raw.get("storeCode", "")),
        store_name=raw.get("storeName", ""),
        order_status=raw.get("orderStatus", ""),
        amount=_to_float(raw.get("realTotalAmount")),
        be_type=str(raw.get("beType", "1")),
        order_type=str(raw.get("orderType", "1")),
        lines=lines,
        # 若原始数据已含详情字段（如样例），一并带入
        original_amount=_to_float(raw.get("totalAmount")),
        discount_amount=_to_float(raw.get("totalDiscountAmount")),
        coupon_names=[c.get("couponName", "") for c in (raw.get("couponList") or []) if c.get("couponName")],
        take_way=raw.get("takeWay", "") or "",
        store_address=raw.get("storeAddress", "") or "",
    )


def enrich_order(order: Order, detail: dict) -> Order:
    """用 query-order 的详情补全一张订单：券、优惠、餐方式、门店地址。"""
    if not isinstance(detail, dict):
        return order
    order.original_amount = _to_float(detail.get("totalAmount")) or order.original_amount
    order.discount_amount = _to_float(detail.get("totalDiscountAmount"))
    order.take_way = detail.get("takeWay", "") or ""
    order.store_address = detail.get("storeAddress", "") or ""
    order.coupon_names = [
        c.get("couponName", "") for c in (detail.get("couponList") or []) if c.get("couponName")
    ]
    return order


def parse_account(raw: dict) -> Account:
    return Account(
        available_point=_to_float(raw.get("availablePoint")),
        accumulative_point=_to_float(raw.get("accumulativePoint")),
        used_point=_to_float(raw.get("usedPoint")),
        expired_point=_to_float(raw.get("expiredPoint")) + _to_float(raw.get("lastMouthExpirePoint")),
    )


def parse_coupon(raw: dict) -> Coupon:
    until = ""
    labels = (raw.get("instructions") or {}).get("availableTime") or []
    for lb in labels:
        if lb.get("text"):
            until = lb["text"]
            break
    labels2 = (raw.get("instructions") or {}).get("labels") or []
    is_delivery = any("外送" in (lb.get("text") or "") for lb in labels2)
    # 券标识（couponId / id / code / couponCode / voucherCode / productCode）——
    # 官方卡包接口实测通常不返回，但**一旦返回就保留**，供算价/下单按需透传。
    coupon_id = next(
        (str(raw[k]) for k in ("couponId", "id", "code", "couponCode", "voucherCode",
                               "productCode") if raw.get(k)),
        "",
    )
    return Coupon(title=raw.get("title", ""), available_until=until, is_delivery=is_delivery,
                  coupon_id=coupon_id)


def parse_prize(raw: dict) -> Prize:
    return Prize(
        name=raw.get("name", ""),
        type_text=raw.get("prizeTypeText", ""),
        status_text=raw.get("statusText", ""),
        record_time=raw.get("recordTime", ""),
    )


def parse_mall_order(raw: dict) -> MallOrder:
    goods = raw.get("goods") or [{}]
    g = goods[0]
    name = g.get("spuName") or g.get("skuName") or ""
    if g.get("skuName"):
        name = f"{name}·{g['skuName']}"
    return MallOrder(
        spu_name=name,
        points=str(g.get("points", "")),
        status_title=raw.get("orderStatusTitle", ""),
        order_id=str(raw.get("orderId", "")),
        spu_id=str(g.get("spuId", "")),
    )


def parse_lottery(raw: dict) -> LotteryInfo:
    prizes = [p.get("name", "") for p in (raw.get("prizes") or []) if p.get("name")]
    return LotteryInfo(
        activity_name=raw.get("activityName", ""),
        status_text=raw.get("activityStatusText", ""),
        end_time=raw.get("endTime", ""),
        draw_point=str(raw.get("drawPoint", "")),
        available_point=_to_float(raw.get("availablePoint")),
        eligible=bool((raw.get("drawDecision") or {}).get("resourceEligible")),
        prize_names=prizes,
    )


def parse_available_coupon(raw: dict) -> AvailableCoupon:
    return AvailableCoupon(
        name=raw.get("couponName", ""),
        status=raw.get("couponStatus", ""),
        label=raw.get("label", ""),
    )


def parse_redeem_product(raw: dict) -> RedeemableProduct:
    return RedeemableProduct(
        spu_id=str(raw.get("spuId", "")),
        name=raw.get("spuName", ""),
        points=str(raw.get("point", "")),
        price=str(raw.get("price", "")),
        category=raw.get("catName", ""),
        shop_id=str(raw.get("shopId", "")),
        selling=raw.get("selling", ""),
    )


def parse_store(raw: dict) -> StoreInfo:
    return StoreInfo(
        code=str(raw.get("storeCode", raw.get("code", ""))),
        name=raw.get("storeName", raw.get("name", "")),
        address=raw.get("address", ""),
        distance=raw.get("distanceText", "") or (f"{raw.get('distance')}m" if raw.get("distance") else ""),
    )


def parse_address(raw: dict) -> DeliveryAddress:
    return DeliveryAddress(
        address_id=str(raw.get("addressId", "")),
        contact=raw.get("contactName", ""),
        phone=raw.get("phone", ""),
        full_address=raw.get("fullAddress", ""),
    )


def parse_campaign(date: str, raw: dict, stage: str) -> CampaignEvent:
    art = raw.get("articleDto") or {}
    return CampaignEvent(
        date=date,
        title=art.get("title") or raw.get("activityTitle", "") or raw.get("bannerTitle", ""),
        content=(art.get("content") or "").strip(),
        stage=stage,
    )
