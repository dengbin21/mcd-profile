"""HTML 分享卡渲染器：暗黑潮酷 · 千人千面（单文件自包含）。"""
from __future__ import annotations

import html
import math

from ..archive import Archive
from ..textpack import CopyPack, TextResolver
from ..theme import Theme, theme_for
from .base import (
    eff_badges, eff_label, eff_quips, eff_radar, eff_slogan, eff_tags,
    img_src, resolver,
)


def _report_html_block(a: Archive, th: Theme, R: TextResolver) -> str:
    """本次点餐战报区块（含商品缩略图 / 实付 / 省 / 热量 / 订单号）。"""
    r = a.order_report
    if r is None:
        return ""

    def _oi(it) -> str:
        src = img_src(it)
        thumb = f'<img class="thumb" src="{src}" alt="">' if src else '<span class="thumb ph">🍔</span>'
        return (f'<div class="oi">{thumb}'
                f'<span>{html.escape(it.name or it.product_code)}</span>'
                f'<b>×{it.quantity}</b></div>')

    rows = "".join(_oi(it) for it in r.items)
    badge = (f'<span class="pill done">{html.escape(R("lbl.report_done"))}</span>' if r.placed
             else f'<span class="pill">{html.escape(R("lbl.report_preview"))}</span>')
    order_no = (f'<div class="oid">{html.escape(R("lbl.report_order_no"))} <code>{html.escape(r.order_id)}</code></div>'
                if r.placed and r.order_id else "")
    save = (f'<div class="rkpi"><b>-¥{r.discount_amount:.0f}</b><span>{html.escape(R("lbl.report_saved"))}</span></div>'
            if r.discount_amount else "")
    kcal = (f'<div class="rkpi"><b>{r.kcal:.0f}</b><span>{html.escape(R("lbl.report_kcal_unit"))}</span></div>'
            if r.kcal else "")
    return f"""
  <div class="report">
    <div class="rhead"><span class="rtag">🎬 {html.escape(R("sec.report"))}</span>{badge}</div>
    <div class="rwhere">{html.escape(r.store_name or '门店')}　·　{html.escape(r.take_way or '到店')}
      {('　·　' + html.escape(r.created_at)) if r.created_at else ''}</div>
    <div class="oitems">{rows}</div>
    <div class="rkpis">
      <div class="rkpi"><b>¥{r.paid_amount:.2f}</b><span>{html.escape(R("lbl.report_paid"))}</span></div>
      {save}{kcal}
    </div>
    {order_no}
  </div>"""


def _radar_svg(radar: dict[str, int], primary: str = "#DA291C",
               accent: str = "#FFC72C", size: int = 250) -> str:
    """把人格雷达渲染成内联 SVG（六维），配色随主题。"""
    dims = list(radar.items())
    n = len(dims)
    cx = cy = size / 2
    R = size / 2 - 36

    def pt(i: int, r: float):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * math.cos(ang), cy + r * math.sin(ang)

    rings = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, R * frac) for i in range(n)))
        rings.append(f'<polygon points="{pts}" fill="none" stroke="rgba(255,255,255,.14)" stroke-width="1"/>')
    axes = []
    for i in range(n):
        x, y = pt(i, R)
        axes.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="rgba(255,255,255,.12)"/>')
    poly = " ".join(
        f"{x:.1f},{y:.1f}" for x, y in (pt(i, R * max(0.08, v / 100)) for i, (_, v) in enumerate(dims))
    )
    labels = []
    for i, (name, _) in enumerate(dims):
        x, y = pt(i, R + 22)
        anchor = "middle" if abs(x - cx) < 6 else ("start" if x > cx else "end")
        labels.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="11" fill="#b9b4ab" '
                      f'text-anchor="{anchor}" dominant-baseline="middle">{html.escape(name)}</text>')
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{accent}"/>'
        for x, y in (pt(i, R * max(0.08, v / 100)) for i, (_, v) in enumerate(dims))
    )
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            + "".join(rings) + "".join(axes)
            + f'<polygon points="{poly}" fill="{primary}" fill-opacity="0.22" stroke="{primary}" stroke-width="2.4"/>'
            + dots + "".join(labels) + "</svg>")


def render_card_html(a: Archive, copy: CopyPack | None = None) -> str:
    c, h, b, p = a.consumption, a.health, a.benefit, a.persona
    s, hb = a.savings, a.habit
    th = theme_for(p)
    R = resolver(copy)
    slogan = eff_slogan(a, copy, th)
    tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in eff_tags(a, copy))
    cta = (copy.cta if (copy and copy.cta) else R("cta"))
    headline_html = (f'<div class="headline">{html.escape(copy.headline)}</div>'
                     if copy and copy.headline else "")
    radar_svg = _radar_svg(eff_radar(a, copy), th.primary, th.accent)
    lights = h.lights
    badges = eff_badges(a, copy)
    badge_html = "".join(
        f'<div class="badge"><div class="be">{bg.emoji}</div>'
        f'<div class="bt">{html.escape(bg.title)}</div>'
        f'<div class="bd">{html.escape(bg.desc)}</div></div>' for bg in badges
    )
    quips = eff_quips(a, copy)
    quote_html = "".join(f'<div class="quote">“{html.escape(q)}”</div>' for q in quips[:2])
    report_html = _report_html_block(a, th, R)

    freq = (f'<div class="kv"><span>{html.escape(R("lbl.kv_frequent"))}</span><b>{html.escape(hb.frequent_name)}</b></div>'
            if hb.frequent_name else "")
    exp = (f'<div class="kv"><span>{html.escape(R("lbl.kv_expiring"))}</span><b style="color:{th.accent}">{len(b.coupons_expiring)} 张</b></div>'
           if b.coupons_expiring else "")
    save_kpi = ""
    if s.enriched_orders and s.total_discount:
        save_kpi = (f'<div class="kpi"><b>-¥{s.total_discount:,.0f}</b>'
                    f'<span>{html.escape(R("lbl.kpi_save_rate", rate=f"{s.discount_rate*100:.0f}"))}</span></div>')
    tools_line = (R("ft.tools", n=a.meta["tools_called"]) if a.raw.tool_calls else R("ft.offline"))

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦麦档案 · {html.escape(eff_label(a, copy))}</title>
<style>
  :root{{--bg:{th.bg};--bg2:{th.bg2};--panel:{th.panel};--primary:{th.primary};
        --accent:{th.accent};--glow:{th.glow};--ink:{th.ink};--muted:{th.muted};}}
  *{{box-sizing:border-box;}}
  body{{margin:0;min-height:100vh;color:var(--ink);padding:26px 14px;
    font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
    background:radial-gradient(120% 55% at 50% 0%,var(--glow) 0%,transparent 60%),
               linear-gradient(160deg,var(--bg),var(--bg2));}}
  .card{{max-width:720px;margin:0 auto;border-radius:24px;overflow:hidden;
    background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.10);
    backdrop-filter:blur(14px);box-shadow:0 24px 70px rgba(0,0,0,.55),0 0 40px var(--glow);}}
  .hero{{padding:30px 30px 14px;position:relative;}}
  .brand{{font-size:12px;letter-spacing:4px;color:var(--primary);font-weight:700;}}
  .persona{{display:flex;gap:16px;align-items:center;margin-top:10px;}}
  .persona .emo{{font-size:56px;line-height:1;filter:drop-shadow(0 0 18px var(--glow));}}
  .name{{font-size:34px;font-weight:900;line-height:1.05;letter-spacing:1px;
    background:linear-gradient(92deg,var(--primary),var(--accent));
    -webkit-background-clip:text;background-clip:text;color:transparent;}}
  .slogan{{color:var(--muted);font-size:13.5px;margin-top:6px;}}
  .tags{{padding:6px 30px 4px;}}
  .headline{{margin:12px 30px 0;padding:10px 14px;border-radius:12px;font-size:14px;font-weight:700;
    color:var(--ink);background:color-mix(in srgb,var(--primary) 16%,transparent);
    border:1px solid color-mix(in srgb,var(--primary) 35%,transparent);}}
  .tag{{display:inline-block;border:1px solid var(--primary);color:var(--primary);
    border-radius:99px;padding:3px 11px;font-size:12px;margin:3px 7px 3px 0;font-weight:600;
    background:color-mix(in srgb,var(--primary) 12%,transparent);}}
  .kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;padding:16px 30px;}}
  .kpi{{background:var(--panel);border:1px solid rgba(255,255,255,.07);border-radius:14px;
    padding:15px 10px;text-align:center;}}
  .kpi b{{display:block;font-size:23px;color:var(--primary);font-variant-numeric:tabular-nums;
    text-shadow:0 0 18px var(--glow);}}
  .kpi span{{font-size:11.5px;color:var(--muted);}}
  /* —— 战报 —— */
  .report{{margin:10px 30px;padding:16px 18px;border-radius:16px;border:1px solid rgba(255,255,255,.10);
    background:linear-gradient(135deg,color-mix(in srgb,var(--primary) 14%,transparent),transparent);}}
  .rhead{{display:flex;justify-content:space-between;align-items:center;}}
  .rtag{{font-weight:800;color:var(--ink);font-size:15px;}}
  .pill{{font-size:11px;padding:3px 10px;border-radius:99px;border:1px solid var(--muted);color:var(--muted);}}
  .pill.done{{border-color:var(--primary);color:var(--primary);background:color-mix(in srgb,var(--primary) 16%,transparent);}}
  .rwhere{{color:var(--muted);font-size:12.5px;margin:7px 0 10px;}}
  .oitems{{display:flex;flex-direction:column;gap:5px;font-size:13.5px;}}
  .oi{{display:flex;align-items:center;gap:10px;border-bottom:1px dashed rgba(255,255,255,.08);padding-bottom:4px;}}
  .oi>span{{flex:1;}}
  .oi b{{color:var(--accent);}}
  .thumb{{width:34px;height:34px;border-radius:8px;object-fit:cover;flex:none;
    background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.10);}}
  .thumb.ph{{display:flex;align-items:center;justify-content:center;font-size:16px;}}
  .rkpis{{display:flex;gap:22px;margin-top:12px;}}
  .rkpi b{{display:block;font-size:20px;color:var(--primary);text-shadow:0 0 16px var(--glow);}}
  .rkpi span{{font-size:11px;color:var(--muted);}}
  .oid{{margin-top:10px;font-size:12px;color:var(--muted);}}
  .oid code{{color:var(--accent);}}
  .sec{{padding:8px 30px 4px;}}
  .sec h2{{font-size:14px;letter-spacing:1px;margin:16px 0 10px;color:var(--ink);}}
  .sec h2::before{{content:"▍";color:var(--primary);margin-right:6px;}}
  .kvrow{{display:flex;flex-wrap:wrap;gap:9px 24px;font-size:13.5px;}}
  .kv{{display:flex;gap:6px;color:var(--muted);}} .kv b{{color:var(--ink);}}
  .radar{{display:flex;justify-content:center;padding:4px 0;}}
  .lights{{display:flex;gap:14px;font-size:13.5px;font-weight:700;padding:4px 0;}}
  .lights .g{{color:#3FD07A;}} .lights .y{{color:#FFC72C;}} .lights .r{{color:#FF5C4D;}}
  /* —— 徽章墙 —— */
  .badges{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:6px 0 2px;}}
  .badge{{background:var(--panel);border:1px solid rgba(255,255,255,.08);border-radius:14px;
    padding:12px 8px;text-align:center;}}
  .badge .be{{font-size:26px;filter:drop-shadow(0 0 12px var(--glow));}}
  .badge .bt{{font-size:12.5px;font-weight:700;color:var(--primary);margin-top:4px;
    font-variant-numeric:tabular-nums;}}
  .badge .bd{{font-size:10.5px;color:var(--muted);margin-top:2px;}}
  /* —— 金句 —— */
  .quotes{{padding:6px 30px 2px;}}
  .quote{{font-size:14px;color:var(--ink);border-left:3px solid var(--primary);
    padding:4px 0 4px 12px;margin:8px 0;line-height:1.6;}}
  .ft{{padding:18px 30px 26px;color:var(--muted);font-size:11px;text-align:center;line-height:1.7;}}
  .cta{{display:inline-block;margin-top:8px;padding:7px 18px;border-radius:99px;font-weight:700;
    color:var(--bg);background:linear-gradient(92deg,var(--primary),var(--accent));}}
</style></head>
<body>
<div class="card">
  <div class="hero">
    <div class="brand">{html.escape(R("brand"))}</div>
    <div class="persona">
      <div class="emo">{p.emoji}</div>
      <div><div class="name">{html.escape(eff_label(a, copy))}</div>
        <div class="slogan">{html.escape(slogan)}</div></div>
    </div>
    <div class="slogan" style="margin-top:8px;opacity:.75">
      {html.escape(R("lbl.html_meta", start=c.date_start, end=c.date_end, n=c.order_count))}</div>
  </div>
  <div class="tags">{tags}</div>
  {headline_html}

  {report_html}

  <div class="kpis">
    <div class="kpi"><b>¥{c.total_spend:,.0f}</b><span>{html.escape(R("lbl.kpi_spend"))}</span></div>
    {save_kpi or f'<div class="kpi"><b>¥{c.avg_ticket:.0f}</b><span>{html.escape(R("lbl.kpi_avg"))}</span></div>'}
    <div class="kpi"><b>{c.order_count}</b><span>{html.escape(R("lbl.kpi_orders"))}</span></div>
  </div>

  <div class="sec">
    <h2>{html.escape(R("sec.radar"))}</h2>
    <div class="radar">{radar_svg}</div>
  </div>

  <div class="sec">
    <h2>{html.escape(R("sec.health_benefit"))}</h2>
    <div class="kvrow">
      <div class="kv"><span>{html.escape(R("lbl.kv_kcal"))}</span><b>{h.total_kcal:.0f} kcal</b></div>
      <div class="kv"><span>{html.escape(R("lbl.kv_bigmac"))}</span><b>{h.bigmac_equiv} 个巨无霸</b></div>
      <div class="kv"><span>{html.escape(R("lbl.kv_sodium"))}</span><b>{h.total_sodium/1000:.1f} g</b></div>
      {exp}{freq}
      <div class="kv"><span>{html.escape(R("lbl.kv_point"))}</span><b>{b.available_point:.0f}</b></div>
      <div class="kv"><span>{html.escape(R("lbl.kv_coupon"))}</span><b>{b.coupon_count} 张</b></div>
    </div>
    <div class="lights"><span class="g">🟢 {lights.get('green',0)}</span>
      <span class="y">🟡 {lights.get('yellow',0)}</span>
      <span class="r">🔴 {lights.get('red',0)}</span>
      <span style="font-weight:400;color:var(--muted);font-size:12px;">{html.escape(R("lbl.lights_note"))}</span></div>
  </div>

  <div class="sec">
    <h2>{html.escape(R("sec.badges"))}</h2>
    <div class="badges">{badge_html}</div>
  </div>

  <div class="quotes">{quote_html}</div>

  <div class="ft">
    {html.escape(R("ft.produced"))} · {html.escape(tools_line)}<br>
    {html.escape(R("ft.disclaimer_short"))}<br>
    <span class="cta">{html.escape(cta)}</span>
  </div>
</div>
</body></html>"""
