"""麦麦档案 McProfile —— 命令行入口。

示例：
    python -m src.cli archive                 # 生成并打印你的麦麦档案
    python -m src.cli archive --html out.html --png out.png
    python -m src.cli orders                  # 只看订单
    python -m src.cli savings                 # 只看省钱复盘
    python -m src.cli account                 # 只看积分与券
    python -m src.cli campaign                # 只看近期活动
    python -m src.cli tools                   # 只看 MCP 工具覆盖清单
    python -m src.cli demo                    # 离线演示（样例数据）
    python -m src.cli stores                  # 查看可选门店
    python -m src.cli menu --store 1990262    # 可视化点餐菜单（带图带价，点选导出点餐话术）
    python -m src.cli eat --dry-run           # 联网：选店→选餐→算价（不下单，安全）
    python -m src.cli eat --yes --items 麦辣鸡腿汉堡:1 --share out.png   # 真实下单并出分享档案

结构约定：
- 本文件只做「参数解析 + 命令编排 + 终端展示」；
- 点餐话术 / 名称解析在 :mod:`src.order_text`（纯函数）；
- MCP 调用与点餐链路在 :mod:`src.ordering`；档案聚合在 :mod:`src.archive`；
- 三种渲染器在 :mod:`src.report` 包（Markdown / HTML / PNG）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# 兼容三种调用方式：python -m src.cli / python src/cli.py / 测试导入。
# 统一用绝对导入（from src.xxx），一份导入列表即可。
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import images                                                    # noqa: E402
from src.archive import build_archive, load_meal_report_sample            # noqa: E402
from src.textpack import CopyPack, build_copy_brief                            # noqa: E402
from src.mcp_client import McdMcpClient, McpError                          # noqa: E402
from src.menu_view import render_menu_html                                  # noqa: E402
from src.models import CartItem                                             # noqa: E402
from src.order_text import (                                                # noqa: E402
    AmbiguousItem, UnknownItem, parse_items, resolve_cart,
)
from src.ordering import (                                                 # noqa: E402
    OrderingSession, describe, list_addresses, list_delivery_stores, list_stores,
    load_menu, menu_probe_fields, place as do_place, quote as calc_quote,
    verify,
)
from src.report import render_card_html, render_card_png, render_markdown   # noqa: E402


# ---------------------------------------------------------------------- #
# 公共小件
# ---------------------------------------------------------------------- #
def _client(args) -> McdMcpClient:
    token = getattr(args, "token", None) or _env_token() or _token_from_config()
    return McdMcpClient(token=token)


def _env_token() -> str | None:
    return os.environ.get("MCD_MCP_TOKEN")


def _token_from_config() -> str | None:
    for path in (ROOT / "mcp-config.example.json", Path.home() / ".codebuddy" / ".mcp.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        servers = data.get("mcpServers", data)
        for v in servers.values():
            header = (v or {}).get("headers", {}).get("Authorization", "")
            if not header.startswith("Bearer "):
                continue
            value = header.split(" ", 1)[1].strip()
            m = re.fullmatch(r"\$\{(\w+)\}", value)
            if m:
                env_val = os.environ.get(m.group(1))
                if env_val:
                    return env_val
                # 该配置文件用的是环境变量占位符但未设置：继续扫描下一个配置
                continue
            if value and "YOUR" not in value.upper():
                return value
    return None


def _use_remote(args) -> bool:
    return not getattr(args, "offline", False)


def _copy(args) -> CopyPack | None:
    """读取 --copy 指定的文案包（WorkBuddy 生成）；未指定则返回 None（走规则模板）。"""
    path = getattr(args, "copy", None)
    if not path:
        return None
    pack = CopyPack.load(path)
    if pack.active:
        print(f"[copy] 已加载模型文案：{path}（source={pack.source}）")
    else:
        print(f"[copy] 文案包为空，回退规则模板：{path}")
        return None
    return pack


def _interactive() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _prompt(msg: str) -> str:
    try:
        return input(msg)
    except (EOFError, KeyboardInterrupt):
        return ""


def _pick_index(pick, n: int, what: str) -> int:
    """选择序号：脚本可用 --pick N；交互则询问；默认第一项。"""
    if pick:
        return max(0, min(n - 1, int(pick) - 1))
    if _interactive():
        ans = _prompt(f"{what}（序号 1-{n}，回车默认 1）：").strip()
        try:
            return max(0, min(n - 1, int(ans) - 1))
        except ValueError:
            return 0
    return 0


def _write_share(a, copy: CopyPack | None, share: str | None) -> list[str]:
    """按 --share 参数写出分享档案；返回写出的文件路径列表。

    - ``.html`` / ``.png`` / ``.md`` → 只出对应格式；
    - 其他后缀 → 视为前缀，同时出 HTML + PNG；
    - 缺省 → 写到 ``examples/eat_report.*``。
    """
    wrote: list[str] = []

    def _html(out: Path):
        out.write_text(render_card_html(a, copy), encoding="utf-8")
        wrote.append(str(out))

    def _png(out: Path):
        png = render_card_png(a, out, copy)
        if png:
            wrote.append(png)

    if share:
        out = Path(share)
        suffix = out.suffix.lower()
        if suffix == ".html":
            _html(out)
        elif suffix == ".png":
            _png(out)
        elif suffix == ".md":
            out.write_text(render_markdown(a, copy), encoding="utf-8")
            wrote.append(str(out))
        else:
            _html(out.with_suffix(".html"))
            _png(out.with_suffix(".png"))
    else:
        _html(ROOT / "examples" / "eat_report.html")
        _png(ROOT / "examples" / "eat_report.png")
    return wrote


# ---------------------------------------------------------------------- #
# 档案类子命令
# ---------------------------------------------------------------------- #
def cmd_archive(args):
    copy = _copy(args)
    a = build_archive(_client(args), use_remote=_use_remote(args))
    md = render_markdown(a, copy)
    print(md)

    if a.errors:
        print("\n<!-- 采集告警：")
        for e in a.errors:
            print(f"  - {e}")
        print("-->")

    if args.html:
        out = Path(args.html)
        out.write_text(render_card_html(a, copy), encoding="utf-8")
        print(f"\n已写入分享卡片：{out}")
    if args.png:
        png = render_card_png(a, args.png, copy)
        print(f"卡片图已生成：{png}" if png else "（未安装 matplotlib，跳过 PNG）")
    if args.out:
        out = Path(args.out)
        out.write_text(md, encoding="utf-8")
        print(f"档案已写入：{out}")


def cmd_orders(args):
    a = build_archive(_client(args), use_remote=_use_remote(args))
    print(f"# 历史订单（{a.meta['data_source']}）\n")
    print("| 时间 | 门店 | 状态 | 实付(元) | 优惠(元) | 用券 | 内容 |")
    print("|---|---|---|---|---|---|---|")
    for o in a.raw.orders:
        items = "、".join(o.product_names())
        coupons = "、".join(o.coupon_names) or "-"
        print(f"| {o.created_at} | {o.store_name} | {o.order_status} | {o.amount:.2f} "
              f"| {o.discount_amount:.2f} | {coupons} | {items} |")


def cmd_savings(args):
    a = build_archive(_client(args), use_remote=_use_remote(args))
    s = a.savings
    print("# 省钱复盘\n")
    if not s.enriched_orders:
        print("（本次采集未获得订单优惠明细，可能订单较少或无券使用记录。）")
        return
    print(f"- 累计原价：¥{s.total_original:.2f}")
    print(f"- 累计实付：¥{s.total_paid:.2f}")
    print(f"- **累计省下：¥{s.total_discount:.2f}（省钱率 {s.discount_rate*100:.1f}%）**")
    print(f"- 用券次数：{s.coupon_used} 次")
    if s.coupon_top:
        print("- 最常用券：" + "、".join(f"{n}×{v}" for n, v in s.coupon_top[:5]))
    if s.best_deal:
        print(f"- 最划算一单：省 ¥{s.best_deal[1]:.2f}　{s.best_deal[0]}")


def cmd_account(args):
    a = build_archive(_client(args), use_remote=_use_remote(args))
    b = a.benefit
    print("# 权益总览\n")
    print(f"- 可用积分：**{b.available_point:.0f}**")
    print(f"- 累计获得 / 已用：{b.accumulative_point:.0f} / {b.used_point:.0f}")
    print(f"- 手持券：{b.coupon_count} 张")
    if b.coupons_expiring:
        print(f"- 30 天内到期：{len(b.coupons_expiring)} 张")
        for t, d in b.coupons_expiring[:6]:
            print(f"  - {t}（{d}）")
        if len(b.coupons_expiring) > 6:
            print(f"  - …其余 {len(b.coupons_expiring) - 6} 张")
    if b.store_coupon_count:
        print(f"- 最爱门店可用券：{b.store_coupon_count} 张")
    if b.available_coupon_count:
        print(f"- 麦麦省可领券：{b.available_coupon_count} 张")
    print(f"- 积分商城订单：{b.mall_order_count} 单，花费 {b.mall_points_spent:.0f} 积分")
    if b.prize_count:
        print(f"- 抽奖奖品：{b.prize_count} 个（可用 {b.prize_available}）")
    if b.lottery_activity:
        print(f"- 积分抽奖：{b.lottery_activity}（{b.lottery_prize_count} 个奖品，"
              f"{'可抽' if b.lottery_eligible else '暂不可抽'}）")
    if b.redeem_count:
        cheapest = f"，最低 {b.redeem_cheapest[1]} 积分换「{b.redeem_cheapest[0]}」" if b.redeem_cheapest else ""
        print(f"- 积分可兑换：{b.redeem_count} 种（够兑 {b.redeem_affordable} 种{cheapest}）")


def cmd_campaign(args):
    a = build_archive(_client(args), use_remote=_use_remote(args))
    act = a.activity
    print(f"# 近期活动（官方活动日历，服务器时间 {act.server_time or '—'}）\n")
    if not act.current and not act.upcoming:
        print("（暂无进行中或即将到来的活动。）")
        return
    if act.current:
        print("## 今日进行中")
        for e in act.current:
            print(f"- {e.title}")
    if act.upcoming:
        print("\n## 即将到来")
        for e in act.upcoming:
            print(f"- `{e.date}` {e.title}")


def cmd_store(args):
    a = build_archive(_client(args), use_remote=_use_remote(args))
    print("# 门店与地址\n")
    if a.raw.nearby_stores:
        print(f"## 相关门店（{len(a.raw.nearby_stores)}）")
        for st in a.raw.nearby_stores:
            d = f"（{st.distance}）" if st.distance else ""
            print(f"- {st.name}{d}　{st.address}")
    if a.raw.addresses:
        print(f"\n## 外送地址（{len(a.raw.addresses)}）")
        for ad in a.raw.addresses:
            print(f"- {ad.full_address}")
    if a.raw.store_coupons:
        print(f"\n## 最爱门店可用券（{len(a.raw.store_coupons)}）")
        for t in a.raw.store_coupons:
            print(f"- {t}")


def cmd_tools(args):
    a = build_archive(_client(args), use_remote=_use_remote(args))
    print("# MCP 工具覆盖清单\n")
    if not a.raw.tool_calls:
        print("（离线演示模式，未实时调用 MCP。）")
        return
    print(f"本次共调用 **{a.meta['tools_called']}** 个官方 MCP 只读工具（成功 {a.meta['tools_ok']} 个）。\n")
    print("| MCP 工具 | 状态 | 产出 |")
    print("|---|---|---|")
    for t in a.raw.tool_calls:
        mark = "✅" if t.ok else "⚠️"
        out = (f"{t.count} 条" if t.count else "—") if t.ok else (t.note or "不可用")
        print(f"| `{t.name}` | {mark} | {out} |")
    print("\n> 本作品只调用「只读」工具；下单/取消/抽奖/领券等写操作刻意不纳入。")


def cmd_card(args):
    copy = _copy(args)
    a = build_archive(_client(args), use_remote=_use_remote(args))
    html_path = args.html or (ROOT / "examples" / "profile_card.html")
    Path(html_path).write_text(render_card_html(a, copy), encoding="utf-8")
    print(f"分享卡片已写入：{html_path}")
    png = render_card_png(a, args.png or (ROOT / "examples" / "profile_card.png"), copy)
    if png:
        print(f"卡片图已生成：{png}")


def cmd_demo(args):
    """离线演示：用样例数据生成档案 + 卡片，无需 Token。"""
    copy = _copy(args)
    a = build_archive(None, use_remote=False, order_report=load_meal_report_sample())
    md = render_markdown(a, copy)
    (ROOT / "examples" / "demo_profile.md").write_text(md, encoding="utf-8")
    print("[demo] examples/demo_profile.md")
    (ROOT / "examples" / "profile_card.html").write_text(render_card_html(a, copy), encoding="utf-8")
    print("[demo] examples/profile_card.html")
    png = render_card_png(a, ROOT / "examples" / "profile_card.png", copy)
    print("[demo] examples/profile_card.png" if png else "[demo] （跳过 PNG）")
    print()
    print(md)


def cmd_brief(args):
    """导出「文案素材」，交给 WorkBuddy（宿主 agent）生成 copy_pack.json。

    这是「WorkBuddy 在环」文案生成的第一步：CLI 只负责给素材，写文案的是 WorkBuddy 本体。
    """
    if _use_remote(args):
        a = build_archive(_client(args), use_remote=True)
    else:
        a = build_archive(None, use_remote=False, order_report=load_meal_report_sample())
    brief = build_copy_brief(a)
    out = Path(args.out) if args.out else (ROOT / "examples" / "copy_brief.json")
    out.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"文案素材（brief）已导出：{out}")
    print("下一步：由 WorkBuddy 读取该文件并生成 copy_pack.json，再用 --copy 渲染档案。")


# ---------------------------------------------------------------------- #
# 点餐闭环
# ---------------------------------------------------------------------- #
def _select_store(client, args, session: OrderingSession, *, allow_delivery: bool = True) -> bool:
    """选店（eat / menu 共用）：写好 session.store_code / store_name。失败返回 False。

    - 指定 ``--store``：直接用；尽力反查真实门店名（查不到也不阻塞）。
    - 未指定：列门店（前 8 家）供交互选择，或 --pick 非交互直选。
    - 外送模式（be_type=2 且 allow_delivery）：先取默认外送地址，再查可配送门店。
    """
    if args.store:
        session.store_code = args.store
        session.store_name = args.store
        try:
            for s in list_stores(client, search_type=args.search, city=args.city,
                                 be_type=args.be_type):
                if s.code == args.store:
                    session.store_name = s.name
                    break
        except McpError:
            pass
        return True

    print("📍 正在获取门店…")
    try:
        if allow_delivery and args.be_type == 2:
            addrs = list_addresses(client)
            if not addrs:
                print("× 未找到外送地址；请先在官方 App 设置默认地址，或用 --store 指定门店。")
                return False
            session.address_id = args.address or str(addrs[0].get("addressId", ""))
            stores = list_delivery_stores(client, session.address_id, be_type=args.be_type)
        else:
            stores = list_stores(client, search_type=args.search, city=args.city,
                                be_type=args.be_type)
    except McpError as exc:
        print(f"× 获取门店失败：{exc}")
        return False
    if not stores:
        print("× 未找到门店（可用 --city 指定城市，或 --store 直接指定门店 code）。")
        return False
    for i, s in enumerate(stores[:8], 1):
        d = f"（{s.distance}）" if s.distance else ""
        print(f"  [{i}] {s.name} {d}  {s.address}")
    st = stores[_pick_index(args.pick, min(len(stores), 8), "选择门店")]
    session.store_code, session.store_name = st.code, st.name
    return True


def _print_catalog(menu) -> list:
    """按类目打印整份菜单（带价 / 折扣 / 图片 URL），并返回与「打印序号」一致的一维商品列表。

    交互选餐时按这里的序号索引；只忠实呈现官方菜单，不做任何挑选。
    """
    in_cat = {c for _, codes in menu.categories for c in codes}
    groups = list(menu.categories)
    others = [it.code for it in menu.items.values() if it.code not in in_cat and it.name]
    if others:
        groups.append(("其他", others))

    catalog: list = []
    for cname, codes in groups:
        rows = [menu.items[c] for c in codes if c in menu.items and menu.items[c].name]
        if not rows:
            continue
        print(f"\n【{cname}】")
        for it in rows:
            catalog.append(it)
            price = f"¥{it.price:.2f}" if it.price else ""
            deal = f"　原价 ¥{it.original_price:.2f}（省 ¥{it.discount:.2f}）" if it.discount else ""
            print(f"  [{len(catalog)}] {it.name}　{price}{deal}")
            if it.image:
                print(f"       🖼  {it.image}")
    return catalog


def _build_cart_from_args(args, menu, client, session) -> list[CartItem] | None:
    """把 --items 解析成购物车（按名点餐）；失败时打印候选并返回 None。"""
    try:
        rc = resolve_cart(parse_items(args.items), menu)
    except AmbiguousItem as e:
        print(f"× 「{e.key}」匹配到 {len(e.candidates)} 款，请用更完整的名字或编码：")
        for it in e.candidates:
            price = f"　¥{it.price:.2f}" if it.price else ""
            print(f"    {it.code}　{it.name}{price}")
        return None
    except UnknownItem as e:
        print(f"× 「{e.key}」没有唯一匹配（最像的是：）")
        for score, it in e.suggestions:
            print(f"    {it.code}　{it.name}　（相似度 {score:.0%}）")
        return None
    for note in rc.notes:
        print(f"  ↳ {note}")
    cart = rc.cart
    # 补全菜单信息 / 逐个查详情（编码直传时菜单可能没有该编码）
    for it in cart:
        mi = menu.items.get(it.product_code)
        if mi is not None:
            it.name = it.name or mi.name
            it.price = it.price or mi.price
            it.image = it.image or mi.image
        elif not it.name:
            try:
                info = describe(client, session, it.product_code)
                it.name, it.image = info.name, info.image
            except McpError:
                pass
    return cart


def _attach_images(cart: list[CartItem], menu) -> None:
    """给购物车项补图（取自菜单），并（尽力）下载缩略图到本地；失败静默降级。"""
    for it in cart:
        mi = menu.items.get(it.product_code)
        if mi is not None:
            it.image = it.image or mi.image
    urls = {it.product_code: it.image for it in cart if it.image}
    local = images.download_many(urls)
    for it in cart:
        it.image_local = local.get(it.product_code, "")


def cmd_eat(args):
    """点餐闭环：选店 → 选餐 → 算价 → 【确认护栏】 → （可选）真实下单 → 生成分享档案。

    默认 **安全预览**（只算价不下单）；只有 `--yes`（或交互输入「下单」）才会真正调用 create-order。
    """
    if not _use_remote(args):
        print("× 点餐需要联网（真实门店 / 菜单 / 价格）。请去掉 --offline 并提供 Token。")
        return
    client = _client(args)
    session = OrderingSession(order_type=args.order_type, be_type=args.be_type)

    # ---- 1) 选店 ----
    if not _select_store(client, args, session):
        return
    print(f"\n🏪 门店：{session.store_name}（{session.store_code}）　模式：{session.mode_text}")

    # ---- 2) 选餐 ----
    print(f"📋 正在读取「{session.store_name}」菜单…")
    try:
        menu = load_menu(client, session)
    except McpError as exc:
        print(f"× 读取菜单失败：{exc}")
        return
    stat = menu_probe_fields(menu)
    print(f"   菜单共 {stat['items']} 款商品（带图 {stat['with_image']} · 带价 {stat['with_price']} · 类目 {stat['categories']}）")

    if args.items:
        cart = _build_cart_from_args(args, menu, client, session)
        if not cart:
            return
    else:
        cart = _pick_items_interactive(menu)
        if not cart:
            return

    # 补图 + 下载缩略图（失败自动降级，不影响下单）
    _attach_images(cart, menu)

    # ---- 3) 算价（拿 takeWayCode） ----
    print("\n🧮 正在算价…")
    try:
        q = calc_quote(client, session, cart, menu=menu)
    except McpError as exc:
        print(f"× 算价失败：{exc}")
        return

    # ---- 3.5) 编码错位护栏：菜单名 ≠ 官方算价名 ⇒ 拒绝继续 ----
    if q.mismatches:
        print("\n⚠️  编码校验失败——菜单与官方算价对同一编码给出了不同商品：")
        for code, menu_name, official in q.mismatches:
            print(f"  · {code}：菜单「{menu_name}」≠ 官方「{official}」")
        print("  为防止「点了 A 下单成 B」，本次已中止（不下单、不生成档案）。")
        print("  请改用菜单页导出的 data-code（以 --items code:qty 重新点餐）。")
        return

    print("\n================ 订单明细 ================")
    for it in q.items:
        price = f"　¥{it.price:.2f}" if it.price else ""
        print(f"  · {it.name or it.product_code}{price}　×{it.quantity}")
        if it.image:
            print(f"       🖼  {it.image}")
    print("------------------------------------------")
    if q.original:
        print(f"  原价：¥{q.original:.2f}　优惠：-¥{q.discount:.2f}（{q.discount_rate*100:.0f}%）")
    print(f"  💰 实付：¥{q.paid:.2f}")
    if q.take_way_list:
        tw = q.take_way_list[0]
        print(f"  取餐方式：{tw.name}" + (f"（共 {len(q.take_way_list)} 种可选）" if len(q.take_way_list) > 1 else ""))

    # ---- 4) 确认护栏 ----
    placed = _confirm_and_place(args, client, session, q)

    # ---- 5) 生成分享档案（战报 + 历史画像合体） ----
    print("\n🎨 正在生成分享档案…")
    copy = _copy(args)
    a = build_archive(client, use_remote=True, order_ctx=(session, q, placed))
    for w in _write_share(a, copy, args.share):
        print(f"  ✔ 分享档案已写入：{w}")
    print()
    print(render_markdown(a, copy))


def _pick_items_interactive(menu) -> list[CartItem] | None:
    """交互选餐：打印整份菜单，按序号点选并逐个问数量。"""
    catalog = _print_catalog(menu)
    if not catalog:
        print("× 菜单为空，无法点餐。")
        return None
    ans = _prompt("\n输入要点的序号（可逗号分隔，如 1,3；回车默认第 1 项）：").strip()
    idxs = []
    for part in (ans or "1").replace("，", ",").split(","):
        part = part.strip()
        if part.isdigit():
            k = int(part)
            if 1 <= k <= len(catalog):
                idxs.append(k - 1)
    if not idxs:
        idxs = [0]
    cart: list[CartItem] = []
    for i in idxs:
        m = catalog[i]
        qn = _prompt(f"「{m.name}」要几份？（回车 1）：").strip()
        cart.append(CartItem(product_code=m.code, name=m.name, price=m.price, image=m.image,
                             quantity=int(qn) if qn.isdigit() and int(qn) > 0 else 1))
    return cart


def _confirm_and_place(args, client, session: OrderingSession, q):
    """真实下单的唯一入口：必须 --yes 或交互输入「下单」。返回 PlacedOrder | None。"""
    do_real = False
    if not args.dry_run:
        if args.yes:
            do_real = True
        elif _interactive():
            ans = _prompt("\n⚠️  真实下单会产生真实订单与费用。确认请输入「下单」（回车=仅预览）：").strip()
            do_real = ans in ("下单", "yes", "y", "Y")

    if not do_real:
        print("\n🧾 当前为「算价预览」，**未真实下单**（加 --yes 或交互输入「下单」才会下单）。")
        return None

    session.take_way_code = args.take_way or (q.take_way_list[0].code if q.take_way_list else "")
    try:
        placed = do_place(client, session, q.items, session.take_way_code,
                          confirm=True, need_tableware=args.tableware, remark=args.remark)
    except McpError as exc:
        print(f"\n× 下单失败：{exc}")
        print("（档案将按「算价预览」生成。）")
        return None
    print(f"\n✅ 已真实下单！订单号：{placed.order_id or '（返回未含订单号，请到官方 App 确认）'}")
    if placed.status:
        print(f"   状态：{placed.status}")
    if placed.order_id:
        try:
            v = verify(client, placed.order_id)
            st = v.get("orderStatus") or v.get("status") or ""
            if st:
                print(f"   复核状态：{st}")
        except McpError:
            pass
    print("   ⚠️ 如需撤销，可在官方 App 或调用 cancel-order 处理。")
    return placed


def cmd_eat_list(args):
    """快速查看可选门店（点餐前的便利子命令）。"""
    if not _use_remote(args):
        print("× 需要联网。")
        return
    client = _client(args)
    try:
        if args.be_type == 2:
            addrs = list_addresses(client)
            for ad in addrs:
                print(f"  [地址] {ad.get('fullAddress', '')}  id={ad.get('addressId', '')}")
            if addrs:
                stores = list_delivery_stores(client, str(addrs[0].get("addressId", "")), be_type=2)
            else:
                stores = []
        else:
            stores = list_stores(client, search_type=args.search, city=args.city, be_type=args.be_type)
    except McpError as exc:
        print(f"× 查询失败：{exc}")
        return
    print(f"# 可选门店（{len(stores)}）\n")
    for s in stores:
        d = f"（{s.distance}）" if s.distance else ""
        print(f"- `{s.code}`　{s.name} {d}　{s.address}")


def cmd_menu(args):
    """生成「可视化点餐菜单」HTML（带图带价 + 点选导出点餐话术）。

    终端与选择卡片渲染不了图片；本命令把官方菜单铺成可浏览的网页，
    点选后一键复制话术，粘贴回 WorkBuddy 对话即可点单。
    """
    if not _use_remote(args):
        print("× 生成可视化菜单需要联网（真实门店 / 菜单 / 图片）。请去掉 --offline 并提供 Token。")
        return
    client = _client(args)
    session = OrderingSession(order_type=args.order_type, be_type=args.be_type)

    # ---- 选店（eat / menu 同一套；menu 不涉及外送地址） ----
    if not _select_store(client, args, session, allow_delivery=False):
        return

    # ---- 读菜单 ----
    print(f"📋 正在读取「{session.store_name}」菜单…")
    try:
        menu = load_menu(client, session)
    except McpError as exc:
        print(f"× 读取菜单失败：{exc}")
        return
    stat = menu_probe_fields(menu)
    if not stat["items"]:
        print("× 菜单为空。")
        return

    # ---- 渲染 ----
    doc = render_menu_html(session.store_name, session.store_code, menu,
                           mode=session.mode_text, embed=args.embed)
    out = Path(args.out) if args.out else ROOT / "examples" / f"menu_{session.store_code}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"   菜单共 {stat['items']} 款（带图 {stat['with_image']} · 带价 {stat['with_price']} · 类目 {stat['categories']}）")
    print(f"  ✔ 可视化菜单已生成：{out}")
    print("    打开网页 → 点选商品 → 一键复制点餐话术 → 粘贴回 WorkBuddy 对话即可点单。")


# ---------------------------------------------------------------------- #
# 参数解析
# ---------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mcd-profile", description="麦麦档案 McProfile")
    p.add_argument("--token", help="mcd-mcp Token（默认读 MCD_MCP_TOKEN 或 mcp-config.example.json）")
    p.add_argument("--offline", action="store_true", help="强制使用离线样例数据")

    def common(sp):
        sp.add_argument("--token", default=argparse.SUPPRESS)
        sp.add_argument("--offline", action="store_true", default=argparse.SUPPRESS)

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("archive", help="生成并打印麦麦档案")
    sp.add_argument("--html", help="导出分享卡片 HTML")
    sp.add_argument("--png", help="导出分享卡片 PNG")
    sp.add_argument("--out", help="把 Markdown 档案写入文件")
    sp.add_argument("--copy", help="注入 WorkBuddy 生成的文案包 JSON（覆盖全部展示文案）")
    common(sp); sp.set_defaults(func=cmd_archive)

    sp = sub.add_parser("orders", help="查看历史订单")
    common(sp); sp.set_defaults(func=cmd_orders)

    sp = sub.add_parser("savings", help="查看省钱复盘")
    common(sp); sp.set_defaults(func=cmd_savings)

    sp = sub.add_parser("account", help="查看积分与券")
    common(sp); sp.set_defaults(func=cmd_account)

    sp = sub.add_parser("campaign", help="查看近期活动")
    common(sp); sp.set_defaults(func=cmd_campaign)

    sp = sub.add_parser("store", help="查看门店与地址")
    common(sp); sp.set_defaults(func=cmd_store)

    sp = sub.add_parser("tools", help="查看 MCP 工具覆盖清单")
    common(sp); sp.set_defaults(func=cmd_tools)

    sp = sub.add_parser("card", help="生成分享卡片（HTML+PNG）")
    sp.add_argument("--html"); sp.add_argument("--png")
    sp.add_argument("--copy", help="注入 WorkBuddy 生成的文案包 JSON")
    common(sp); sp.set_defaults(func=cmd_card)

    sp = sub.add_parser("demo", help="离线演示")
    sp.add_argument("--copy", help="注入 WorkBuddy 生成的文案包 JSON")
    common(sp); sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("brief", help="导出文案素材（交给 WorkBuddy 写文案）")
    sp.add_argument("--out", help="brief 输出路径（默认 examples/copy_brief.json）")
    common(sp); sp.set_defaults(func=cmd_brief)

    # —— 点餐闭环 ——
    sp = sub.add_parser("stores", help="查看可选门店（点餐前用）")
    sp.add_argument("--search", type=int, default=1, help="1=收藏餐厅（默认）2=按位置搜索")
    sp.add_argument("--city", default="", help="searchType=2 时的城市名")
    sp.add_argument("--be-type", type=int, default=1, help="1 到店自取 / 2 麦乐送 / 5 得来速 / 6 团餐")
    common(sp); sp.set_defaults(func=cmd_eat_list)

    sp = sub.add_parser("menu", help="生成可视化点餐菜单（带图带价 + 点选导出点餐话术）")
    sp.add_argument("--store", help="门店 code（缺省则先选店）")
    sp.add_argument("--search", type=int, default=1, help="1=收藏餐厅（默认）2=按位置搜索")
    sp.add_argument("--city", default="", help="searchType=2 时的城市名")
    sp.add_argument("--pick", type=int, help="非交互式：直接选第 N 家门店（1 起）")
    sp.add_argument("--order-type", type=int, default=1, help="1 到店 / 2 外送")
    sp.add_argument("--be-type", type=int, default=1, help="1 到店自取 / 2 麦乐送 / 5 得来速 / 6 团餐")
    sp.add_argument("--embed", action="store_true", help="把商品图转 data-uri 内嵌（单文件自包含，体积较大）")
    sp.add_argument("--out", help="输出 HTML 路径（默认 examples/menu_<store>.html）")
    common(sp); sp.set_defaults(func=cmd_menu)

    sp = sub.add_parser("eat", help="点餐闭环：选店→选餐→算价→(确认)下单→生成分享档案")
    sp.add_argument("--store", help="直接指定门店 code（跳过选店）")
    sp.add_argument("--search", type=int, default=1, help="1=收藏餐厅（默认）2=按位置搜索")
    sp.add_argument("--city", default="", help="searchType=2 时的城市名")
    sp.add_argument("--pick", type=int, help="非交互式：直接选第 N 家门店（1 起）")
    sp.add_argument("--order-type", type=int, default=1, help="1 到店 / 2 外送")
    sp.add_argument("--be-type", type=int, default=1, help="1 到店自取 / 2 麦乐送 / 5 得来速 / 6 团餐")
    sp.add_argument("--address", help="外送地址 id（be-type=2 时）")
    sp.add_argument("--items", nargs="+", metavar="CODE|名称:QTY",
                    help="直接指定商品，编码或名称均可，如 --items 9900016076:1 麦辣鸡腿汉堡:2")
    sp.add_argument("--take-way", help="取餐方式 code（默认取算价返回的第一项）")
    sp.add_argument("--dry-run", action="store_true", help="只算价不下单（默认安全，等价于不加 --yes）")
    sp.add_argument("--yes", action="store_true", help="确认真实下单（会生成真实订单与费用）")
    sp.add_argument("--tableware", action="store_true", help="是否需要餐具")
    sp.add_argument("--remark", default="", help="外送备注")
    sp.add_argument("--share", metavar="PATH",
                    help="分享档案输出：.html / .png / .md，或前缀（同时出 HTML+PNG）")
    sp.add_argument("--copy", help="注入 WorkBuddy 生成的文案包 JSON")
    common(sp); sp.set_defaults(func=cmd_eat)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
