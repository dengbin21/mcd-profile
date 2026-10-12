"""PNG 分享卡渲染器：竖版长图 1080×自适应（朋友圈 / 小红书友好）。

依赖 matplotlib（可选）：未安装时 :func:`render_card_png` 返回 None，上层静默降级。
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .. import images
from ..archive import Archive
from ..textpack import CopyPack
from ..theme import theme_for
from .base import (
    eff_badges, eff_label, eff_quips, eff_radar, eff_slogan, eff_tags,
    img_ref, resolver,
)


def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0000FE0F]"
)

# 跨平台 CJK 字体候选（按常见度排序）；渲染前探测本机实际注册的字体，
# 避免写死某平台字体导致中文退化成方框（DejaVu Sans 无 CJK 字形）。
_CJK_CANDIDATES = (
    "PingFang SC", "Hiragino Sans GB", "Hiragino Sans CNS", "Noto Sans CJK SC",
    "Noto Sans CJK JP", "Source Han Sans SC", "WenQuanYi Zen Hei",
    "Microsoft YaHei", "SimHei", "Songti SC", "STHeiti", "Heiti SC",
    "Kaiti SC", "Arial Unicode MS",
)


def _cjk_sans_serif() -> list[str]:
    """返回当前 matplotlib 已注册的 CJK 字体名；全部缺失时兜底 DejaVu Sans。"""
    from matplotlib import font_manager as _fm
    available = {f.name for f in _fm.fontManager.ttflist}
    found = [c for c in _CJK_CANDIDATES if c in available]
    return found or ["DejaVu Sans"]


def _png_plain(s: str) -> str:
    """PNG 渲染用：剥离 emoji 与变体选择符（matplotlib 无彩色 emoji 字体）。"""
    return _EMOJI_RE.sub("", s).strip()


def _trunc(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _vert_gradient(ax, top: str, bottom: str) -> None:
    import numpy as np
    t = np.linspace(0, 1, 256).reshape(-1, 1)
    c1 = np.array(_hex(top)).reshape(1, 1, 3)
    c2 = np.array(_hex(bottom)).reshape(1, 1, 3)
    img = (1 - t)[..., None] * c2 + t[..., None] * c1   # 顶部 c1 → 底部 c2
    ax.imshow(img, aspect="auto", extent=[0, 1, 0, 1], zorder=0)


def render_card_png(a: Archive, out_path: str | Path, copy: CopyPack | None = None) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
    except Exception:  # noqa: BLE001
        return None

    fonts = _cjk_sans_serif()
    if "DejaVu Sans" not in fonts:      # CJK 全缺时已兜底，避免重复
        fonts.append("DejaVu Sans")
    plt.rcParams["font.sans-serif"] = fonts
    plt.rcParams["axes.unicode_minus"] = False

    c, h, b, p = a.consumption, a.health, a.benefit, a.persona
    s = a.savings
    th = theme_for(p)
    primary, accent = th.primary, th.accent
    R = resolver(copy)

    r = a.order_report
    slogan = eff_slogan(a, copy, th)
    tags = eff_tags(a, copy)
    badges = eff_badges(a, copy)
    quips = eff_quips(a, copy)
    radar_dims = eff_radar(a, copy)

    # ---- 预排：先算内容总高（"设计单位"，1.0 ≈ 19.2in），再动态定画布高度 ----
    GAP = 0.014
    blocks: list[tuple[float, str]] = []
    if r is not None:
        blocks.append((0.055 + 0.03 * max(1, min(6, len(r.items))), "report"))
    blocks.append((0.125, "kpi"))
    blocks.append((0.155, "radar"))
    if badges:
        blocks.append((0.045 * ((len(badges) + 2) // 3) + 0.028, "badges"))
    if quips:
        blocks.append((0.030 * len(quips[:3]) + 0.020, "quips"))
    if c.item_dist or c.store_dist:
        blocks.append((0.115, "taste"))
    if s.enriched_orders:
        blocks.append((0.062, "savings"))
    blocks.append((0.058, "mcp"))

    TOP, BOTTOM_PAD = 0.862, 0.075
    y_final = TOP - sum(hh for hh, _ in blocks) - GAP * (len(blocks) - 1)
    D = (0.99 - y_final) + BOTTOM_PAD          # 设计高度（映射到画布 1.0）
    fig_h = 19.2 * D                           # 内容越高，长图越高

    def M(v: float) -> float:                  # 设计坐标 → figure 分数
        return (v - y_final + BOTTOM_PAD) / D

    fig = plt.figure(figsize=(10.8, fig_h), dpi=100)
    bgax = fig.add_axes([0, 0, 1, 1])
    bgax.axis("off")
    bgax.set_xlim(0, 1)
    bgax.set_ylim(0, 1)
    _vert_gradient(bgax, th.bg, th.bg2)

    def panel(y0, y1, x0=0.06, x1=0.94, alpha=0.05):
        a0, a1 = M(y0), M(y1)
        bgax.add_patch(FancyBboxPatch((x0, a0), x1 - x0, a1 - a0,
                                      boxstyle="round,pad=0.006,rounding_size=0.02",
                                      linewidth=1, edgecolor=(1, 1, 1, 0.10),
                                      facecolor=(1, 1, 1, alpha), zorder=1))

    def text(x, y, t, **kw):
        fig.text(x, M(y), t, **kw)

    def draw_img(x, y_top, wx, hy, item):
        """在设计坐标 (x, y_top) 处画一个 wx×hy 的商品图；无图则画占位块。"""
        ax = fig.add_axes([x, M(y_top - hy), wx, hy / D])
        arr = images.load_array(img_ref(item))
        if arr is None:
            ax.axis("off")
            ax.add_patch(FancyBboxPatch((0.02, 0.02), 0.96, 0.96,
                                        boxstyle="round,pad=0.02,rounding_size=0.18",
                                        transform=ax.transAxes, facecolor=(1, 1, 1, 0.06),
                                        edgecolor=(1, 1, 1, 0.10), linewidth=1))
        else:
            ax.imshow(arr)
            ax.axis("off")

    # —— 头部 ——
    text(0.06, 0.968, _png_plain(R("brand")), color=primary, fontsize=17, fontweight="bold")
    text(0.06, 0.936, _png_plain(eff_label(a, copy)), color="#ffffff", fontsize=40, fontweight="black")
    text(0.06, 0.912, _png_plain(slogan), color=th.muted, fontsize=15)
    text(0.06, 0.893, " ".join(f"#{t}" for t in tags), color=accent, fontsize=13)
    text(0.94, 0.968, R("lbl.date_range", start=c.date_start, end=c.date_end),
         color=th.muted, fontsize=12, ha="right")

    y = TOP
    for hh, kind in blocks:
        if kind == "report":
            panel(y - hh, y)
            text(0.085, y - 0.028, _png_plain(R("sec.report")), color="#ffffff", fontsize=17, fontweight="bold")
            text(0.94, y - 0.028, _png_plain(R("lbl.report_done") if r.placed else R("lbl.report_preview")),
                 color=(primary if r.placed else th.muted), fontsize=12, ha="right")
            text(0.085, y - 0.052, f"{r.store_name or '门店'} · {r.take_way or '到店'}",
                 color=th.muted, fontsize=11.5)
            yy = y - 0.078
            for it in r.items[:6]:
                tx = 0.085
                if img_ref(it):
                    draw_img(0.072, yy + 0.013, 0.028, 0.0158, it)
                    tx = 0.108
                text(tx, yy, f"· {it.name or it.product_code}", color="#EDEAE3", fontsize=12.5)
                text(0.94, yy, f"×{it.quantity}", color=accent, fontsize=12.5, ha="right")
                yy -= 0.024

        elif kind == "kpi":
            kpis = [(R("lbl.kpi_spend"), f"¥{c.total_spend:,.0f}"),
                    (R("lbl.kpi_save"), f"¥{s.total_discount:,.0f}"),
                    (R("lbl.kpi_order_cnt"), f"{c.order_count} 单"),
                    (R("lbl.kpi_bigmac"), f"{h.bigmac_equiv:.0f} 个"),
                    (R("lbl.kpi_kcal"), f"{h.total_kcal:.0f}"),
                    (R("lbl.kpi_point"), f"{b.available_point:.0f}")]
            panel(y - hh, y)
            for i, (k, v) in enumerate(kpis):
                col, row = i % 3, i // 3
                x = 0.10 + col * 0.28
                yy = y - 0.038 - row * 0.055
                text(x, yy, _png_plain(v), color=primary, fontsize=22, fontweight="bold")
                text(x, yy - 0.024, _png_plain(k), color=th.muted, fontsize=11)

        elif kind == "radar":
            panel(y - hh, y)
            text(0.085, y - 0.026, _png_plain(R("sec.radar")), color="#ffffff", fontsize=15, fontweight="bold")
            ax = fig.add_axes([0.50, M(y - hh) + 0.006, 0.42, (hh - 0.012) / D], polar=True)
            ax.set_facecolor("none")
            dims = list(radar_dims.items())
            labels = [d for d, _ in dims]
            vals = [max(0.06, v / 100) for _, v in dims]
            angv = [n / len(dims) * 2 * math.pi for n in range(len(dims))] + [0]
            ax.plot(angv, vals + vals[:1], color=primary, linewidth=2.2)
            ax.fill(angv, vals + vals[:1], color=primary, alpha=0.25)
            ax.set_xticks(angv[:-1])
            ax.set_xticklabels([_png_plain(x) for x in labels], color="#b9b4ab", fontsize=9)
            ax.set_yticks([])
            ax.grid(color="#494541", linewidth=0.6)
            ax.spines["polar"].set_color("#494541")
            lights = h.lights
            text(0.085, y - hh + 0.030,
                 R("lbl.lights_png", g=lights.get('green', 0), y=lights.get('yellow', 0), r=lights.get('red', 0)),
                 fontsize=15, color="#EDEAE3")
            text(0.085, y - hh + 0.012, _png_plain(R("lbl.lights_note_png")), color=th.muted, fontsize=10)

        elif kind == "badges":
            panel(y - hh, y)
            text(0.085, y - 0.026, _png_plain(R("sec.badges")), color="#ffffff", fontsize=15, fontweight="bold")
            for i, bg in enumerate(badges[:9]):
                col, row = i % 3, i // 3
                x = 0.105 + col * 0.285
                yy = y - 0.052 - row * 0.045
                text(x, yy, _png_plain(f"{bg.emoji} {bg.title}"), color=primary,
                     fontsize=13, fontweight="bold")

        elif kind == "quips":
            panel(y - hh, y)
            yy = y - 0.030
            for q in quips[:3]:
                text(0.085, yy, f"“{_png_plain(q)}”", color="#EDEAE3", fontsize=12.5)
                yy -= 0.030

        elif kind == "taste":
            panel(y - hh, y)
            text(0.085, y - 0.026, _png_plain(R("sec.taste")), color="#ffffff", fontsize=15, fontweight="bold")
            text(0.085, y - 0.050, _png_plain(R("lbl.taste_top")), color=th.muted, fontsize=10)
            yy = y - 0.070
            for name, cnt in c.item_dist[:4]:
                text(0.085, yy, _trunc(_png_plain(name), 12), color="#EDEAE3", fontsize=11)
                text(0.44, yy, f"×{cnt}", color=accent, fontsize=11, ha="right")
                yy -= 0.020
            text(0.52, y - 0.050, _png_plain(R("lbl.taste_store")), color=th.muted, fontsize=10)
            yy = y - 0.070
            for name, cnt in c.store_dist[:4]:
                text(0.52, yy, _trunc(_png_plain(name), 12), color="#EDEAE3", fontsize=11)
                text(0.90, yy, f"{cnt} 单", color=accent, fontsize=11, ha="right")
                yy -= 0.020

        elif kind == "savings":
            panel(y - hh, y)
            text(0.085, y - 0.026, _png_plain(R("sec.savings_hl")), color="#ffffff", fontsize=15, fontweight="bold")
            bits = [R("lbl.sav_total", amt=f"{s.total_discount:.0f}", rate=f"{s.discount_rate*100:.0f}"),
                    R("lbl.sav_coupon", n=s.coupon_used)]
            if s.best_deal:
                bits.append(R("lbl.sav_best", amt=f"{s.best_deal[1]:.0f}"))
            if s.coupon_top:
                bits.append(R("lbl.sav_fav_coupon", name=_trunc(_png_plain(s.coupon_top[0][0]), 10)))
            text(0.085, y - 0.047, _png_plain("　·　".join(bits)), color="#EDEAE3", fontsize=11.5)

        elif kind == "mcp":
            panel(y - hh, y)
            text(0.085, y - 0.026, _png_plain(R("sec.mcp_cap")), color="#ffffff", fontsize=15, fontweight="bold")
            if a.raw.tool_calls:
                mcp_line = R("lbl.mcp_line_png", n=a.meta['tools_called'], ok=a.meta['tools_ok'])
            else:
                mcp_line = R("lbl.mcp_offline_png")
            text(0.085, y - 0.047, _png_plain(mcp_line), color=th.muted, fontsize=10.5)

        y -= hh + GAP

    # —— 页脚 ——
    tools_line = (R("ft.tools", n=a.meta['tools_called']) if a.raw.tool_calls else R("ft.offline"))
    fig.text(0.5, 0.046 / D, _png_plain(R("ft.line1", tools=tools_line)),
             color=th.muted, fontsize=11, ha="center")
    fig.text(0.5, 0.020 / D, _png_plain(R("ft.line2")),
             color=th.muted, fontsize=10, ha="center")

    fig.savefig(out_path, facecolor=th.bg)
    plt.close(fig)
    return str(out_path)
