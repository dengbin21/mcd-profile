"""麦麦最优解战报渲染：把 :class:`~src.solver.Solution` 变成能晒的竖版卡片。

三种产物：
- ``render_solve_markdown`` —— 终端/仓库里可读的 Markdown；
- ``render_solve_html``     —— 自包含 HTML 竖版长图（1080 宽，手机截图即朋友圈比例）；
- 复用 ``src/report`` 的 PNG 能力不在本模块，HTML 转图交给浏览器/截图。

配色沿用 ``src.theme`` 的「优惠猎人」主题，与既有档案卡片同族，
保证「同一套产品、两种卡片」的观感一致。

**文案全部走 ``src.textpack`` 的文案层**（``sv.*`` 键）：默认用规则模板，
传入 ``copy``（WorkBuddy 生成的文案包）即可覆写**除数值外的全部文字**。
数值一律由规则计算并经 ``{占位符}`` 注入——**数值永不出自模型**。
"""
from __future__ import annotations

from .report.tokens import REPO_URL, REPORT_BASE_CSS
from .solver import Solution
from .textpack import CopyPack, TextResolver, pick_grade_word
from .theme import THEMES

_THEME = THEMES.get("优惠猎人", next(iter(THEMES.values())))

_GRADE_COLOR = {"S": "#FFC72C", "A": "#17C3A2", "B": "#4D7CFE", "C": "#98938B"}
_GRADE_WORD = {
    "S": "这单可以吹一年",
    "A": "省得很体面",
    "B": "还能再压一压",
    "C": "原价党本色出演",
}


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _avg_drop(sol: Solution) -> float:
    """均价降幅（%）：直觉点法的单件均价 → 最优解的单件均价。"""
    if not sol.baseline_avg:
        return 0.0
    return (sol.baseline_avg - sol.avg_price) / sol.baseline_avg * 100.0


def _esc(s: str) -> str:
    """HTML 转义，但放行 ``<br>``——模型文案靠它换行，其余标签一律挡掉。

    文案来自模型，**不能直接插进 HTML**：否则一句带 ``<script>`` 的文案
    就能把分享卡变成注入载体。这里白名单只留换行。
    """
    if not s:
        return ""
    out = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
    return out.replace("&lt;br&gt;", "<br>").replace("&lt;/br&gt;", "<br>")


def _grade_word(sol: Solution, copy: CopyPack | None) -> str:
    """评级词：模型可在 ``copy.solve.grade_word`` 里整词覆写。

    两种写法都收：一个字符串（所有评级同一句），或 ``{"S": …, "A": …}``
    按评级各写一句——后者更像人话，四个档位本来就不该同词。
    """
    ow = pick_grade_word(copy.solve, sol.grade) if copy else ""
    return ow or _GRADE_WORD.get(sol.grade, "")


def _headline(sol: Solution, copy: CopyPack | None) -> str:
    """卡片一句话总括：模型可在 ``copy.solve.headline`` 里自由发挥。"""
    return ((copy.solve.get("headline") if copy else "") or "").strip()


# ---------------------------------------------------------------------- #
# Markdown
# ---------------------------------------------------------------------- #
def render_solve_markdown(sol: Solution, *, store_name: str = "",
                          offline: bool = False,
                          copy: CopyPack | None = None) -> str:
    tx = TextResolver(copy)
    if not sol.items:
        return f"# {tx('sv.kicker')}\n\n（{tx('sv.no_solution')}）\n"

    n = sol.nutrition or {}
    lines: list[str] = []
    lines.append(f"# {tx('sv.md_title')}\n")
    lines.append(tx("sv.grade_line", grade=sol.grade, word=_grade_word(sol, copy)))
    lines.append("")

    if store_name:
        lines.append(tx("sv.store_line", store=store_name))
        lines.append("")

    lines.append(f"## {tx('sv.sec_solution')}\n")
    lines.append("| | |\n|---|---|")
    lines.append(f"| {tx('sv.lbl_original')} | ¥{_fmt(sol.original)} |")
    lines.append(f"| **{tx('sv.lbl_paid')}** | **¥{_fmt(sol.paid)}** |")
    lines.append(f"| {tx('sv.lbl_discount')} | "
                 f"{tx('sv.discount_note', discount=_fmt(sol.discount), rate=f'{sol.save_rate * 100:.1f}')} |")
    lines.append("")
    lines.append(f"### {tx('sv.sec_items')}\n")
    for i in sol.items:
        lines.append(f"- {i.name}  ¥{_fmt(i.price)}")

    if sol.baseline_paid and sol.baseline_count and sol.count != sol.baseline_count:
        lines.append("")
        lines.append(f"## {tx('sv.sec_vs')}\n")
        lines.append(f"| | {tx('sv.lbl_count')} | {tx('sv.lbl_pay')} | {tx('sv.lbl_avg')} |"
                     "\n|---|---|---|---|")
        lines.append(f"| {tx('sv.lbl_baseline')} | {sol.baseline_count} "
                     f"| ¥{_fmt(sol.baseline_paid)} | ¥{_fmt(sol.baseline_avg)} |")
        lines.append(f"| {tx('sv.lbl_best')} | **{sol.count}** "
                     f"| **¥{_fmt(sol.paid)}** | **¥{_fmt(sol.avg_price)}** |")
        lines.append("")
        if sol.saved > 0:
            lines.append(f"**{tx('sv.vs_save', saved=_fmt(sol.saved))}**")
        else:
            drop_txt = f"{_avg_drop(sol):.0f}"
            more_txt = tx("sv.vs_more", extra=_fmt(-sol.saved), n=sol.extra_count,
                          a=_fmt(sol.baseline_avg), b=_fmt(sol.avg_price), drop=drop_txt)
            lines.append(f"**{more_txt}**")
            # 两个「省」必须说清口径，否则和上面的「官方优惠」读起来自相矛盾
            lines.append("")
            lines.append(f"> {tx('sv.vs_note', extra=_fmt(-sol.saved))}")

    lines.append("")
    lines.append(f"## {tx('sv.sec_process')}\n")
    lines.append(tx("sv.enum_line", n=sol.enum_count))
    if sol.valid_count and sol.valid_count != sol.enum_count:
        lines.append(tx("sv.valid_line", n=sol.valid_count))
    lines.append(tx("sv.verify_line", n=sol.verify_count, ok=sol.verify_ok))
    if sol.fail_count:
        lines.append(tx("sv.fail_line", n=sol.fail_count))
    lines.append(f"- {tx('sv.final_note')}")

    recognized = [r for r in sol.rules if r.kind != "unknown"]
    if recognized:
        lines.append("")
        lines.append(f"### {tx('sv.sec_rules')}\n")
        for r in recognized[:8]:
            lines.append(f"- {r.title} → {r.readable}")

    if n:
        lines.append("")
        lines.append(f"## {tx('sv.sec_nutrition')}\n")
        kcal_txt = f"{n.get('kcal', 0):.0f}"
        protein_txt = f"{n.get('protein', 0):.0f}"
        fat_txt = f"{n.get('fat', 0):.0f}"
        sodium_txt = f"{n.get('sodium', 0):.0f}"
        lines.append(f"- {tx('sv.nut_kcal', kcal=kcal_txt)}")
        lines.append(f"- {tx('sv.nut_line', p=protein_txt, f=fat_txt, na=sodium_txt)}")
        if n.get("total"):
            lines.append(f"- {tx('sv.nut_cov', m=n.get('matched', 0), t=n.get('total', 0))}")

    lines.append("")
    if offline:
        lines.append(f"> {tx('sv.demo_warn')}")
    lines.append(f"> {tx('sv.foot_price')}")
    lines.append(f"> {tx('sv.foot_nutrition')}")
    lines.append("")
    lines.append(f"---\n\n{tx('sv.cta_md', repo=REPO_URL)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# HTML
# ---------------------------------------------------------------------- #
_SOLVE_CSS = """
.hero{position:relative;border-radius:28px;padding:34px 28px 30px;background:#171205;
  border:1px solid rgba(255,199,44,.22);overflow:hidden}
.hero::after{content:"";position:absolute;right:-70px;top:-70px;width:230px;height:230px;
  border-radius:50%;background:rgba(255,199,44,.10)}
.kicker{font-size:15px;letter-spacing:.22em;color:#FFE38A}
.title{font-size:40px;font-weight:800;margin-top:10px;letter-spacing:.02em}
.sub{font-size:15px;color:#98938B;margin-top:8px}
.grade{margin-top:22px;display:flex;align-items:center;gap:14px}
.gword{font-size:19px;font-weight:700}
.gnote{font-size:13px;color:#98938B;margin-top:3px}
.hline{margin-top:14px;font-size:18px;font-weight:700;color:#FFE38A;line-height:1.5}
.paidrow{margin-top:26px;display:flex;align-items:flex-end;gap:12px}
.paid{font-size:76px;font-weight:800;line-height:1;color:#FFC72C}
.cur{font-size:26px;font-weight:700;color:#FFC72C;margin-bottom:10px}
.strike{font-size:20px;color:#98938B;text-decoration:line-through;margin-bottom:12px}
.save{margin-top:14px;display:inline-block;padding:8px 16px;border-radius:999px;
  background:rgba(255,199,44,.14);color:#FFE38A;font-size:17px;font-weight:700}
.item{display:flex;justify-content:space-between;align-items:center;padding:11px 0;
  border-bottom:1px dashed rgba(255,255,255,.08);font-size:17px}
.item:last-child{border-bottom:none}
.iname{color:#F6F4EF}
.iprice{color:#FFE38A;font-weight:700}
.vs{display:flex;gap:14px}
.vscol{flex:1;border-radius:18px;padding:18px 16px;background:#1A1710;text-align:center}
.vslab{font-size:13px;color:#98938B}
.vsnum{font-size:30px;font-weight:800;margin-top:8px}
.vsnum.dim{color:#98938B}
.vsnum.hot{color:#FFC72C}
.vssub{font-size:12px;color:#98938B;margin-top:7px}
.vsfoot{margin-top:18px;text-align:center;font-size:19px;font-weight:800;color:#17C3A2;line-height:1.6}
.vsnote{margin-top:12px;padding:10px 14px;border-radius:12px;font-size:12px;line-height:1.7;
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);color:#98938B}
.nut{display:flex;gap:14px;text-align:center}
.nutc{flex:1;background:#1A1710;border-radius:16px;padding:14px 8px}
.nnum{font-size:22px;font-weight:800}
.nlab{font-size:12px;color:#98938B;margin-top:5px}
"""
_CSS = REPORT_BASE_CSS + _SOLVE_CSS


def render_solve_html(sol: Solution, *, store_name: str = "",
                      offline: bool = False,
                      copy: CopyPack | None = None) -> str:
    tx = TextResolver(copy)
    if not sol.items:
        return (f"<!doctype html><meta charset='utf-8'>"
                f"<p>{_esc(tx('sv.no_solution_html'))}</p>")

    g = sol.grade
    gcolor = _GRADE_COLOR.get(g, "#98938B")
    n = sol.nutrition or {}
    hl = _headline(sol, copy)

    items_html = "".join(
        f"<div class='item'><span class='iname'>{_esc(i.name or '')}</span>"
        f"<span class='iprice'>¥{_fmt(i.price)}</span></div>"
        for i in sol.items
    )

    vs_html = ""
    if sol.baseline_paid and sol.baseline_count and sol.count != sol.baseline_count:
        if sol.saved > 0:
            foot = _esc(tx("sv.vs_save", saved=_fmt(sol.saved)))
            note = ""
        else:
            foot = _esc(tx("sv.vs_more_html", extra=_fmt(-sol.saved),
                           n=sol.extra_count, drop=f"{_avg_drop(sol):.0f}"))
            # 「折扣力度」与「多花」并排出现，不解释口径会读成自相矛盾
            note = (f"<div class='vsnote'>{_esc(tx('sv.vs_note_html', extra=_fmt(-sol.saved)))}</div>")
        vs_html = (
            f"<div class='sec'><div class='h'>{_esc(tx('sv.sec_vs'))}</div>"
            "<div class='vs'>"
            f"<div class='vscol'><div class='vslab'>"
            f"{_esc(tx('sv.vs_baseline_col', n=sol.baseline_count))}</div>"
            f"<div class='vsnum dim'>¥{_fmt(sol.baseline_paid)}</div>"
            f"<div class='vssub'>{_esc(tx('sv.vs_avg_line', avg=_fmt(sol.baseline_avg)))}</div></div>"
            f"<div class='vscol'><div class='vslab'>"
            f"{_esc(tx('sv.vs_best_col', n=sol.count))}</div>"
            f"<div class='vsnum hot'>¥{_fmt(sol.paid)}</div>"
            f"<div class='vssub'>{_esc(tx('sv.vs_avg_line', avg=_fmt(sol.avg_price)))}</div></div>"
            "</div>"
            f"<div class='vsfoot'>{foot}</div>{note}</div>"
        )

    recognized = [r for r in sol.rules if r.kind != "unknown"]
    chips = "".join(f"<span class='chip'>{_esc(r.title)}</span>" for r in recognized[:10])
    unknown = len(sol.rules) - len(recognized)
    if unknown > 0:
        chips += f"<span class='chip dim'>{_esc(tx('sv.rules_unknown', n=unknown))}</span>"
    rules_html = (
        f"<div class='sec'><div class='h'>{_esc(tx('sv.sec_rules'))}</div>"
        f"<div class='chips'>{chips}</div></div>"
        if chips else ""
    )

    nut_html = ""
    if n and n.get("kcal"):
        nut_html = (
            f"<div class='sec'><div class='h'>{_esc(tx('sv.sec_nutrition'))}</div><div class='nut'>"
            f"<div class='nutc'><div class='nnum'>{n.get('kcal', 0):.0f}</div>"
            f"<div class='nlab'>{_esc(tx('sv.lbl_kcal_unit'))}</div></div>"
            f"<div class='nutc'><div class='nnum'>{n.get('protein', 0):.0f}g</div>"
            f"<div class='nlab'>{_esc(tx('sv.lbl_protein'))}</div></div>"
            f"<div class='nutc'><div class='nnum'>{n.get('fat', 0):.0f}g</div>"
            f"<div class='nlab'>{_esc(tx('sv.lbl_fat'))}</div></div>"
            f"<div class='nutc'><div class='nnum'>{n.get('sodium', 0):.0f}mg</div>"
            f"<div class='nlab'>{_esc(tx('sv.lbl_sodium'))}</div></div>"
            "</div></div>"
        )

    # 验价失败必须如实露出：最优解只在「验价成功的组合」里挑，
    # 藏着不说会让人误以为已经穷举过全部候选。
    fail_html = (
        f"<div class='note'>⚠️ {_esc(tx('sv.fail_note_html', n=sol.fail_count))}</div>"
        if sol.fail_count else ""
    )

    stats_html = (
        f"<div class='sec'><div class='h'>{_esc(tx('sv.sec_process'))}</div><div class='stats'>"
        f"<div class='stat'><div class='snum'>{sol.enum_count}</div>"
        f"<div class='slab'>{_esc(tx('sv.stat_enum'))}</div></div>"
        f"<div class='stat'><div class='snum'>{sol.verify_count}</div>"
        f"<div class='slab'>{_esc(tx('sv.stat_verify'))}</div></div>"
        f"<div class='stat'><div class='snum'>{sol.save_rate * 100:.0f}%</div>"
        f"<div class='slab'>{_esc(tx('sv.stat_rate'))}</div></div>"
        f"</div>{fail_html}</div>"
    )

    warn = (f"<div class='warn'>{_esc(tx('sv.demo_warn'))}</div>" if offline else "")

    store_line = f"<div class='sub'>{_esc(store_name)}</div>" if store_name else ""
    hl_line = f"<div class='hline'>{_esc(hl)}</div>" if hl else ""

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(tx('sv.md_title'))}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">

<div class="hero">
  <div class="kicker">M C S O L V E</div>
  <div class="title">{_esc(tx('sv.kicker'))}</div>
  {store_line}
  {hl_line}
  <div class="grade">
    <div class="badge" style="background:{gcolor}">{g}</div>
    <div>
      <div class="gword">{_esc(_grade_word(sol, copy))}</div>
      <div class="gnote">{_esc(tx('sv.sub'))}</div>
    </div>
  </div>
  <div class="paidrow">
    <span class="cur">¥</span><span class="paid">{_fmt(sol.paid)}</span>
    <span class="strike">¥{_fmt(sol.original)}</span>
  </div>
  <div class="save">{_esc(tx('sv.lbl_discount'))} ¥{_fmt(sol.discount)} · {_esc(tx('sv.stat_rate'))} {sol.save_rate * 100:.1f}%</div>
</div>

<div class="sec">
  <div class="h">{_esc(tx('sv.sec_items'))}</div>
  {items_html}
</div>

{vs_html}
{stats_html}
{rules_html}
{nut_html}

<div class="cta">{_esc(tx('sv.cta', repo=REPO_URL))}</div>
{warn}
<div class="foot">
  {_esc(tx('sv.foot_price_html'))}<br>
  {_esc(tx('sv.foot_nutrition'))}
</div>

</div></body></html>"""
