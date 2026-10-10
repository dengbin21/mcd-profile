"""Markdown 档案渲染器：终端可读、可直接写文件。"""
from __future__ import annotations

from ..analysis import daily_ratio
from ..archive import POTENTIAL_TOOLS, Archive
from ..textpack import CopyPack, TextResolver
from ..theme import theme_for
from .base import (
    TOOL_DESC, eff_advice, eff_badges, eff_label, eff_quips,
    eff_radar, eff_slogan, eff_tags, fmt_expiring, img_ref, resolver, yuan,
)


def _report_markdown(a: Archive, R: TextResolver) -> list[str]:
    """本次点餐战报（点餐闭环产物）。"""
    r = a.order_report
    if r is None:
        return []
    L: list[str] = []
    L.append(f"## 🎬 {R('sec.report')}")
    L.append("")
    head = f"**{r.store_name or '门店'}**"
    if r.created_at:
        head += f"　·　{r.created_at}"
    if r.take_way:
        head += f"　·　{r.take_way}"
    L.append(head)
    L.append("")
    if r.items:
        L.append(f"| {R('lbl.tbl_item')} | {R('lbl.tbl_qty')} |")
        L.append("|---|---|")
        for it in r.items:
            name = it.name or it.product_code
            if img_ref(it):
                name = f"[{name}]({img_ref(it)})"
            L.append(f"| {name} | ×{it.quantity} |")
        L.append("")
    L.append(f"- 实付 **{yuan(r.paid_amount)}**"
             + (f"（原价 {yuan(r.original_amount)}，省下 **{yuan(r.discount_amount)}**"
                f"，省钱率 {r.discount_rate*100:.0f}%）" if r.discount_amount else ""))
    if r.kcal:
        L.append(f"- 这一单热量 **{r.kcal:.0f} kcal**（≈ {r.bigmac_equiv} 个巨无霸）、钠 {r.sodium:.0f} mg")
    if r.placed and r.order_id:
        L.append(f"- " + R("lbl.report_placed_note", oid=r.order_id, status=r.status or ""))
    else:
        L.append(f"- " + R("lbl.report_preview_note"))
    L.append("")
    return L


def render_markdown(a: Archive, copy: CopyPack | None = None) -> str:
    c, h, b, p = a.consumption, a.health, a.benefit, a.persona
    s, hb, act = a.savings, a.habit, a.activity
    th = theme_for(p)
    R = resolver(copy)
    theme_name = R("lbl.theme_name") or th.name
    slogan = eff_slogan(a, copy, th)
    tags = eff_tags(a, copy)
    L: list[str] = []
    L.append(f"# {R('sec.md_title')}")
    L.append("")
    L.append("> " + R("lbl.meta_line", theme=theme_name, n=a.meta['tools_called'],
                      m=a.meta['order_total'], start=c.date_start, end=c.date_end))
    L.append("")
    if copy and copy.headline:
        L.append(f"> **{copy.headline}**")
        L.append("")
    L.append(f"## {p.emoji} {R('sec.persona')}：**{eff_label(a, copy)}**")
    L.append("")
    L.append(f"> {slogan}")
    L.append("")
    if tags:
        L.append(f"**{R('lbl.tags')}：** " + " · ".join(f"`{t}`" for t in tags))
        L.append("")

    # —— 本次点餐战报 ——
    L += _report_markdown(a, R)

    # —— 成就徽章墙 ——
    badges = eff_badges(a, copy)
    if badges:
        L.append(f"## 🏅 {R('sec.badges')}")
        L.append("")
        L.append("　".join(f"{bg.emoji} **{bg.title}**" for bg in badges))
        L.append("")
        L.append("　".join(f"　　`{bg.desc}`" for bg in badges if bg.desc))
        L.append("")

    # —— 金句 ——
    quips = eff_quips(a, copy)
    if quips:
        L.append(f"## 💬 {R('sec.quips')}")
        L.append("")
        for q in quips:
            L.append(f"- {q}")
        L.append("")

    # —— 消费画像 ——
    L.append(f"## 💰 {R('sec.consumption')}")
    L.append("")
    L.append(f"| {R('lbl.tbl_metric')} | {R('lbl.tbl_value')} |")
    L.append("|---|---|")
    L.append(f"| {R('lbl.total_spend')} | **{yuan(c.total_spend)}** |")
    L.append(f"| {R('lbl.orders')} | {R('lbl.orders_note', n=c.order_count, r=c.refunded_count)} |")
    L.append(f"| {R('lbl.avg_ticket')} | {yuan(c.avg_ticket)} |")
    if c.max_order:
        L.append(f"| {R('lbl.max_order')} | {yuan(c.max_order[1])}　{c.max_order[0]} |")
    if c.min_order:
        L.append(f"| {R('lbl.min_order')} | {yuan(c.min_order[1])}　{c.min_order[0]} |")
    if c.fav_store:
        L.append(f"| {R('lbl.fav_store')} | {c.fav_store[0]}（{c.fav_store[1]} 单） |")
    if c.fav_item:
        L.append(f"| {R('lbl.fav_item')} | {c.fav_item[0]}（{c.fav_item[1]} 次） |")
    L.append("")
    if c.meal_dist:
        L.append(f"**{R('lbl.slots')}：** " + " / ".join(f"{k} {v} 单" for k, v in c.meal_dist.items()))
        L.append("")
    if c.item_dist:
        top = "、".join(f"{n}×{v}" for n, v in c.item_dist[:5])
        L.append(f"**{R('lbl.top5')}：** {top}")
        L.append("")

    # —— 省钱画像 ——
    if s.enriched_orders:
        L.append(f"## 🎯 {R('sec.savings')}")
        L.append("")
        L.append(f"| {R('lbl.tbl_metric')} | {R('lbl.tbl_value')} |")
        L.append("|---|---|")
        L.append(f"| {R('lbl.total_original')} | {yuan(s.total_original)} |")
        L.append(f"| {R('lbl.total_paid_m')} | {yuan(s.total_paid)} |")
        L.append(f"| **{R('lbl.total_discount')}** | **{yuan(s.total_discount)}** |")
        L.append(f"| {R('lbl.discount_rate')} | **{s.discount_rate*100:.1f}%** |")
        L.append(f"| {R('lbl.coupon_used')} | {s.coupon_used} 次 |")
        if s.coupon_top:
            L.append(f"| {R('lbl.coupon_top')} | {s.coupon_top[0][0]}（{s.coupon_top[0][1]} 次） |")
        if s.best_deal:
            L.append(f"| {R('lbl.best_deal_m')} | 省 {yuan(s.best_deal[1])}　{s.best_deal[0]} |")
        L.append("")
        L.append("> " + R("lbl.savings_note", a=s.enriched_orders, b=c.order_count))
        L.append("")

    # —— 健康画像 ——
    L.append(f"## 🩺 {R('sec.health')}")
    L.append("")
    L.append("> " + R("lbl.health_cov", cov=h.coverage, days=h.days))
    L.append("")
    L.append(f"| {R('lbl.tbl_metric')} | {R('lbl.tbl_cumulative')} | {R('lbl.tbl_daily')} |")
    L.append("|---|---|---|")
    L.append(f"| {R('lbl.kcal')} | {h.total_kcal:.0f} kcal | {daily_ratio(h,'energyKcal')} 天 |")
    L.append(f"| {R('lbl.protein')} | {h.total_protein:.0f} g | {daily_ratio(h,'protein')} 天 |")
    L.append(f"| {R('lbl.fat')} | {h.total_fat:.0f} g | {daily_ratio(h,'fat')} 天 |")
    L.append(f"| {R('lbl.carb')} | {h.total_carbohydrate:.0f} g | {daily_ratio(h,'carbohydrate')} 天 |")
    L.append(f"| {R('lbl.sodium')} | {h.total_sodium:.0f} mg | {daily_ratio(h,'sodium')} 天 |")
    L.append("")
    L.append(R("lbl.bigmac_line", n=h.bigmac_equiv, k=f"{h.avg_kcal:.0f}", na=f"{h.avg_sodium:.0f}"))
    L.append("")
    lights = h.lights
    L.append(R("lbl.lights_md", g=lights.get('green', 0), y=lights.get('yellow', 0), r=lights.get('red', 0)))
    L.append("")
    if h.top_sodium:
        L.append(f"**{R('lbl.sodium_top')}：** " + "、".join(f"{n}({v:.0f}mg)" for n, v in h.top_sodium[:3]))
        L.append("")

    # —— 习惯画像 ——
    if hb.frequent_name or hb.slot_dist:
        L.append(f"## 🧭 {R('sec.habit')}")
        L.append("")
        if hb.frequent_name:
            comps = hb.frequent_components
            shown = "、".join(comps[:6]) + ("…" if len(comps) > 6 else "")
            comp = f"（{shown}）" if comps else ""
            L.append(f"- **{R('lbl.frequent')}：** {hb.frequent_name}{comp}")
        if hb.peak_slot:
            L.append(f"- **{R('lbl.peak_slot')}：** {hb.peak_slot}　"
                     + "、".join(f"{k}{v}单" for k, v in hb.slot_dist.items()))
        if hb.weekday_dist:
            L.append(f"- **{R('lbl.weekday')}：** " + "　".join(f"{k} {v}" for k, v in hb.weekday_dist.items()))
        if hb.avg_items:
            L.append(f"- **{R('lbl.avg_items')}：** {hb.avg_items} 件")
        if hb.order_span_days:
            L.append(f"- **{R('lbl.span')}：** {hb.order_span_days} 天")
        L.append("")

    # —— 权益画像 ——
    L.append(f"## 🎫 {R('sec.benefit')}")
    L.append("")
    L.append(f"| {R('lbl.tbl_metric')} | {R('lbl.tbl_value')} |")
    L.append("|---|---|")
    L.append(f"| {R('lbl.available_point')} | {b.available_point:.0f} |")
    L.append(f"| {R('lbl.point_acc_used')} | {b.accumulative_point:.0f} / {b.used_point:.0f} |")
    L.append(f"| {R('lbl.coupon_count')} | {b.coupon_count} 张 |")
    if b.coupons_expiring:
        L.append(f"| {R('lbl.expiring')} | {fmt_expiring(b.coupons_expiring)} |")
    if b.store_coupon_count:
        L.append(f"| {R('lbl.store_coupon')} | {b.store_coupon_count} 张 |")
    if b.available_coupon_count:
        L.append(f"| {R('lbl.available_coupon')} | {b.available_coupon_count} 张 |")
    L.append(f"| {R('lbl.mall_orders')} | {b.mall_order_count} 单（花 {b.mall_points_spent:.0f} 积分） |")
    if b.prize_count:
        L.append(f"| {R('lbl.prize')} | {b.prize_count} 个（{b.prize_available} 个可用） |")
    if b.lottery_activity:
        L.append(f"| {R('lbl.lottery')} | {b.lottery_activity}（{b.lottery_prize_count} 个奖品） |")
    if b.redeem_count:
        cheapest = f"，最低 {b.redeem_cheapest[1]} 积分换「{b.redeem_cheapest[0]}」" if b.redeem_cheapest else ""
        L.append(f"| {R('lbl.redeem')} | {b.redeem_count} 种商品（现有积分够兑 {b.redeem_affordable} 种{cheapest}） |")
    L.append("")

    # —— 活动日历 ——
    if act.current or act.upcoming:
        L.append(f"## 📅 {R('sec.activity')}")
        L.append("")
        if act.current:
            L.append(f"**{R('lbl.activity_now')}**")
            for e in act.current[:5]:
                L.append(f"- {e.title}")
            L.append("")
        if act.upcoming:
            L.append(f"**{R('lbl.activity_upcoming')}**")
            for e in act.upcoming[:6]:
                L.append(f"- `{e.date}` {e.title}")
            L.append("")

    # —— 门店足迹 ——
    if a.raw.nearby_stores or a.raw.addresses:
        L.append(f"## 🗺️ {R('sec.stores')}")
        L.append("")
        if a.raw.nearby_stores:
            names = "、".join(st.name for st in a.raw.nearby_stores[:5])
            L.append(f"- **{R('lbl.stores_nearby', n=len(a.raw.nearby_stores))}** {names}")
        if a.raw.addresses:
            L.append(f"- **{R('lbl.addresses')}** {len(a.raw.addresses)} 个")
        L.append("")

    # —— 工具覆盖清单 ——
    L.append(f"## 🧩 {R('sec.mcp')}")
    L.append("")
    if a.raw.tool_calls:
        L.append(R("lbl.mcp_summary", n=a.meta['tools_called'], ok=a.meta['tools_ok']))
        L.append("")
        L.append(f"| {R('lbl.tbl_tool')} | {R('lbl.tbl_usage')} | {R('lbl.tbl_status')} | {R('lbl.tbl_out')} |")
        L.append("|---|---|---|---|")
        for t in a.raw.tool_calls:
            mark = "✅" if t.ok else "⚠️"
            out = f"{t.count} 条" if t.count else "—"
            if not t.ok:
                out = t.note or "不可用"
            desc = TOOL_DESC.get(t.name, "")
            L.append(f"| `{t.name}` | {desc} | {mark} | {out} |")
        L.append("")
    else:
        L.append("> " + R("lbl.mcp_offline"))
        L.append("> " + "、".join(f"`{t}`" for t in POTENTIAL_TOOLS) + "。")
        L.append("")

    # —— 建议 ——
    advice = eff_advice(a, copy)
    if advice:
        L.append(f"## 🎯 {R('sec.advice')}")
        L.append("")
        for tip in advice:
            L.append(f"- {tip}")
        L.append("")

    L.append("---")
    L.append("")
    L.append("*" + R("ft.disclaimer") + "*")
    return "\n".join(L)
