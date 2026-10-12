"""麦麦预热台战报渲染：倒计时 + 冲突预警 + 备战度，竖版可截图长图。

视觉沿用「优惠猎人」主题（暗金），与 McSolve 战报同族，
保证「同一套产品、两种卡片」的观感一致。

主视觉是**倒计时**：大号天数 + 进度环；钩子是**冲突预警**——
「你的券等不到那天」用高对比色块顶在最前面。

**文案全部走 ``src.textpack`` 的文案层**（``ph.*`` 键）：默认用规则模板，
传入 ``copy``（WorkBuddy 生成的文案包）即可覆写**除数值外的全部文字**。
数值一律由规则计算并经 ``{占位符}`` 注入——**数值永不出自模型**。
"""
from __future__ import annotations

from .preheat import URGENT_DAYS, CouponWatch, Preheat
from .report.tokens import (
    GRADE_COLOR, REPO_URL, REPORT_BASE_CSS, esc as _esc, html_wrap,
)
from .textpack import CopyPack, TextResolver


def _expire_text(c: CouponWatch, tx: TextResolver) -> str:
    """券的到期显示文案（数值占位符由程序填入）。"""
    left = c.days_to_expire
    if left is None:
        return tx("ph.lbl_dash")
    if left < 0:
        return tx("ph.lbl_expired")
    if left == 0:
        # 「0 天后」没人看得懂——今天到期就说今天。
        return tx("ph.lbl_today")
    return tx("ph.lbl_expire_in", n=left)


# ---------------------------------------------------------------------- #
# Markdown
# ---------------------------------------------------------------------- #
def render_preheat_markdown(pre: Preheat, copy: CopyPack | None = None) -> str:
    tx = TextResolver(copy)
    lines: list[str] = []
    lines.append(f"# {tx('ph.md_title')}\n")
    lines.append(f"> {pre.headline}\n")
    lines.append(f"> {tx('ph.sec_score')} **{pre.grade}**"
                 f"（{tx('ph.lbl_score', score=pre.score)}）—— {pre.grade_word}\n")

    if pre.server_time:
        lines.append(f"{tx('ph.lbl_data_time', t=pre.server_time)}\n")

    # 日期读不懂必须说出来，否则会静默退化成「没有可预热的活动」，
    # 而 campaign 命令（按官方 stage 字段分桶）照常显示——两处对不上就是 bug。
    if pre.unparsed_count:
        lines.append(f"> {tx('ph.unparsed_note_full', n=pre.unparsed_count)}\n")

    # 券侧同理：到期文案读不懂的券不能默默消失——
    # 真实接口里「今日」到期的那张券就差点这么人间蒸发。
    if pre.coupon_unparsed_count:
        lines.append(f"> {tx('ph.coupon_unparsed_full', n=pre.coupon_unparsed_count)}\n")

    # ---- 倒计时 ----
    if pre.target:
        lines.append(f"## {tx('ph.sec_countdown')}\n")
        lines.append("| | |\n|---|---|")
        lines.append(f"| {tx('ph.lbl_target')} | **{pre.target.title}** |")
        lines.append(f"| {tx('ph.lbl_date')} | {pre.target.date} |")
        lines.append(f"| {tx('ph.lbl_left')} | **{pre.days_left} {tx('ph.lbl_unit_day')}** |")
        if pre.target.content:
            lines.append(f"| {tx('ph.lbl_desc')} | {pre.target.content} |")
        lines.append("")

    # ---- 冲突（钩子主体）----
    if pre.missing:
        lines.append(f"## ⚠️ {tx('ph.sec_conflict')}\n")
        lines.append(f"| {tx('ph.tbl_coupon')} | {tx('ph.tbl_expire')} "
                     f"| {tx('ph.tbl_left')} |\n|---|---|---|")
        for c in pre.missing:
            lines.append(f"| {c.title} | {c.until_text or tx('ph.lbl_dash')} "
                         f"| {_expire_text(c, tx)} |")
        lines.append("")
        lines.append(f"**{tx('ph.conflict_warn')}**")
        lines.append("")

    if pre.urgent:
        urgent_title = tx('ph.sec_urgent', n=URGENT_DAYS)
        lines.append(f"## {urgent_title}\n")
        for c in pre.urgent:
            lines.append(f"- {c.title} —— {c.until_text}（{_expire_text(c, tx)}）")
        lines.append("")

    if pre.surviving:
        # 压线券已经在「即将到期」里列过一遍，这里再列就是**同一批券抄两遍**
        # （活动只剩 1 天时两节会完全重叠）。只补上真正安全的那部分。
        safe = [c for c in pre.surviving if not c.tight]
        lines.append(f"## {tx('ph.sec_surviving')}\n")
        for c in safe[:8]:
            tail = f"（{_expire_text(c, tx)}到期）" if c.days_to_expire is not None else ""
            lines.append(f"- ✅ {c.title}{tail}")
        tight_n = len(pre.surviving) - len(safe)
        if tight_n:
            lines.append("")
            lines.append(f"_{tx('ph.surviving_note', n=tight_n)}_")
        lines.append("")

    # ---- 积分 ----
    if pre.points:
        lines.append(f"## {tx('ph.sec_ammo')}\n")
        tip = tx("ph.ammo_floor", floor=f"{pre.redeem_floor:g}") if pre.redeem_floor else ""
        lines.append(f"- {tx('ph.ammo_line', points=f'{pre.points:g}', tip=tip)}")
        if pre.redeemable:
            lines.append(f"- {tx('ph.ammo_redeem', n=pre.redeemable)}")
        lines.append("")

    # ---- 今日活动 ----
    if pre.running:
        lines.append(f"## {tx('ph.sec_running')}\n")
        for c in pre.running:
            tail = f" —— {c.content}" if c.content else ""
            lines.append(f"- {c.title}{tail}")
        lines.append("")

    if pre.upcoming and pre.target:
        rest = [c for c in pre.upcoming if c is not pre.target]
        if rest:
            lines.append(f"## {tx('ph.sec_later')}\n")
            for c in rest[:5]:
                lines.append(f"- {c.date}　{c.title}")
            lines.append("")

    # ---- 建议 ----
    lines.append(f"## {tx('ph.sec_tips')}\n")
    for t in pre.tips:
        lines.append(f"1. {t}")
    lines.append("")

    lines.append("---\n")
    lines.append(f"{tx('ph.foot_md')}\n")
    lines.append(tx("ph.cta_md", repo=REPO_URL))
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# HTML
# ---------------------------------------------------------------------- #
_PREHEAT_CSS = """
.hero{border-radius:28px;padding:32px 28px 28px;background:#171205;
  border:1px solid rgba(255,199,44,.22)}
.kicker{font-size:15px;letter-spacing:.22em;color:#FFE38A}
.title{font-size:38px;font-weight:800;margin-top:10px}
.head{font-size:19px;color:#FFC72C;margin-top:12px;font-weight:700;line-height:1.5}
.sub{font-size:14px;color:#98938B;margin-top:10px}

.count{margin-top:26px;display:flex;align-items:center;gap:22px}
.cnum{font-size:88px;font-weight:800;line-height:.9;color:#FFC72C;letter-spacing:-.03em}
.cunit{font-size:22px;font-weight:700;color:#FFE38A;margin-left:6px}
.ctitle{font-size:17px;font-weight:700;margin-top:6px}
.cmeta{font-size:13px;color:#98938B;margin-top:4px}

.sec.danger{background:#1E0F0C;border-color:rgba(255,92,74,.34)}
.sec.danger .h{color:#FF8A76}

.rows{margin-top:14px}
.row{display:flex;justify-content:space-between;gap:14px;padding:11px 0;
  border-bottom:1px solid rgba(255,255,255,.06);font-size:16px}
.row:last-child{border-bottom:0}
.row .r{color:#98938B;font-size:14px;white-space:nowrap}
.list .tag{display:inline-block;min-width:30px;color:#17C3A2;font-weight:700}
.list .tag.bad{color:#FF8A76}

.score{margin-top:20px;display:flex;align-items:center;gap:16px}
.snum{font-size:30px;font-weight:800}
.sword{font-size:14px;color:#98938B;margin-top:2px}
.bar{margin-top:14px;height:10px;border-radius:6px;background:rgba(255,255,255,.09);overflow:hidden}
.bar i{display:block;height:100%;border-radius:6px}

.tips{margin-top:12px;padding-left:20px}
.tips li{font-size:15px;line-height:1.85;margin-bottom:6px}
"""
_CSS = REPORT_BASE_CSS + _PREHEAT_CSS


def _ring(progress: float) -> str:
    """倒计时进度环。"""
    p = max(0.0, min(1.0, progress))
    r, c = 46, 2 * 3.14159 * 46
    return (
        f"<svg width='116' height='116' viewBox='0 0 116 116'>"
        f"<circle cx='58' cy='58' r='{r}' fill='none' stroke='rgba(255,255,255,.10)' stroke-width='9'/>"
        f"<circle cx='58' cy='58' r='{r}' fill='none' stroke='#FFC72C' stroke-width='9' "
        f"stroke-linecap='round' stroke-dasharray='{c:.1f}' stroke-dashoffset='{c * (1 - p):.1f}' "
        f"transform='rotate(-90 58 58)'/>"
        f"<text x='58' y='64' text-anchor='middle' font-size='22' font-weight='800' "
        f"fill='#FFC72C'>{int(p * 100)}%</text></svg>"
    )


def _coupon_rows(items: list[CouponWatch], bad: bool, tx: TextResolver) -> str:
    out = []
    for c in items:
        right = _expire_text(c, tx)
        tag = "bad" if bad else ""
        warn = (f" <span style='color:#FFC72C;font-size:13px'>"
                f"· {_esc(tx('ph.lbl_press'))}</span>" if c.tight else "")
        tail = f" · {_esc(c.until_text)}" if c.until_text else ""
        out.append(f"<li><span class='tag {tag}'>{'✕' if bad else '✓'}</span> "
                   f"{_esc(c.title)} <span style='color:#98938B;font-size:13px'>"
                   f"· {_esc(right)}{tail}</span>{warn}</li>")
    return "<ul class='list'>" + "".join(out) + "</ul>"


def render_preheat_html(pre: Preheat, copy: CopyPack | None = None) -> str:
    tx = TextResolver(copy)
    g = pre.grade
    gcolor = GRADE_COLOR.get(g, "#98938B")

    # ---- 倒计时 ----
    if pre.target:
        d = pre.days_left or 0
        num = str(d) if d > 0 else tx("ph.lbl_today")
        unit_html = f"<span class='cunit'>{_esc(tx('ph.lbl_unit_day'))}</span>" if d > 0 else ""
        meta = pre.target.date + (f" · {pre.target.content}" if pre.target.content else "")
        count_html = (
            "<div class='count'>"
            f"<div><div><span class='cnum'>{num}</span>{unit_html}</div>"
            f"<div class='ctitle'>{_esc(pre.target.title)}</div>"
            f"<div class='cmeta'>{_esc(meta)}</div></div>"
            f"<div style='margin-left:auto'>{_ring(pre.progress)}</div>"
            "</div>"
        )
    else:
        count_html = (f"<div class='count'><div class='ctitle'>{_esc(tx('ph.no_target'))}"
                      f"</div><div class='cmeta'>{_esc(tx('ph.no_target_sub'))}</div></div>")

    # ---- 冲突（钩子主体，放最前）----
    danger_html = ""
    if pre.missing:
        danger_html = (
            f"<div class='sec danger'><div class='h'>⚠️ {_esc(tx('ph.sec_conflict'))}</div>"
            + _coupon_rows(pre.missing, bad=True, tx=tx)
            + "<div style='margin-top:12px;font-size:14px;color:#FF8A76'>"
            + _esc(tx("ph.conflict_warn")) + "</div></div>"
        )

    urgent_html = ""
    if pre.urgent:
        urgent_html = (f"<div class='sec'><div class='h'>"
                       f"{_esc(tx('ph.sec_urgent', n=URGENT_DAYS))}</div>"
                       + _coupon_rows(pre.urgent, bad=True, tx=tx) + "</div>")

    ok_html = ""
    if pre.surviving:
        # 与 Markdown 同口径：压线券不在这里重复列一遍，只补真正安全的那部分。
        safe = [c for c in pre.surviving if not c.tight]
        tight_n = len(pre.surviving) - len(safe)
        note = (f"<div style='margin-top:10px;font-size:13px;color:#98938B'>"
                f"{_esc(tx('ph.surviving_note', n=tight_n))}</div>") if tight_n else ""
        body = _coupon_rows(safe[:8], bad=False, tx=tx) if safe else ""
        ok_html = (f"<div class='sec'><div class='h'>{_esc(tx('ph.sec_surviving'))}</div>"
                   + body + note + "</div>")

    # ---- 备战度 ----
    score_html = (
        f"<div class='sec'><div class='h'>{_esc(tx('ph.sec_score'))}</div><div class='score'>"
        f"<div class='badge' style='background:{gcolor}'>{g}</div>"
        f"<div><div class='snum'>{_esc(tx('ph.lbl_score', score=pre.score))}</div>"
        f"<div class='sword'>{_esc(pre.grade_word)}</div></div></div>"
        f"<div class='bar'><i style='width:{pre.score}%;background:{gcolor}'></i></div></div>"
    )

    # ---- 弹药 ----
    ammo_html = ""
    if pre.points:
        tip = tx("ph.ammo_floor", floor=f"{pre.redeem_floor:g}") if pre.redeem_floor else ""
        extra = tx("ph.ammo_redeem_html", n=pre.redeemable) if pre.redeemable else ""
        ammo_html = (f"<div class='sec'><div class='h'>{_esc(tx('ph.sec_ammo'))}</div>"
                     f"<ul class='list'><li>{tx('ph.ammo_html', points=f'{pre.points:g}', tip=tip)}"
                     f"<span style='color:#98938B;font-size:13px'>{_esc(extra)}</span>"
                     f"</li></ul></div>")

    # ---- 今日/后续活动 ----
    today_html = ""
    if pre.running:
        lis = "".join(
            f"<li>{_esc(c.title)}"
            + (f"<span style='color:#98938B;font-size:13px'> · {_esc(c.content)}</span>"
               if c.content else "")
            + "</li>" for c in pre.running)
        today_html = (f"<div class='sec'><div class='h'>{_esc(tx('ph.sec_running'))}</div>"
                      f"<ul class='list'>{lis}</ul></div>")

    later_html = ""
    rest = [c for c in pre.upcoming if c is not pre.target]
    if rest:
        lis = "".join(f"<li><span style='color:#98938B'>{_esc(c.date)}</span>　{_esc(c.title)}</li>"
                      for c in rest[:5])
        later_html = (f"<div class='sec'><div class='h'>{_esc(tx('ph.sec_later'))}</div>"
                      f"<ul class='list'>{lis}</ul></div>")

    tips_html = (f"<div class='sec'><div class='h'>{_esc(tx('ph.sec_tips'))}</div>"
                 "<ol class='tips'>"
                 + "".join(f"<li>{_esc(t)}</li>" for t in pre.tips) + "</ol></div>")

    # 日期读不懂必须露出：否则卡片静默变成「没有可预热的活动」，
    # 而 campaign 命令照常列出活动，两处对不上就成了 bug。
    unparsed_html = (
        f"<div class='note'>⚠️ {_esc(tx('ph.unparsed_note', n=pre.unparsed_count))} "
        f"{_esc(tx('ph.unparsed_note_html'))}</div>"
        if pre.unparsed_count else ""
    )
    # 券侧：读不懂到期日的券不能悄悄不显示，否则用户以为自己没这张券。
    coupon_unparsed_html = (
        f"<div class='note'>⚠️ {_esc(tx('ph.coupon_unparsed_html', n=pre.coupon_unparsed_count))}</div>"
        if pre.coupon_unparsed_count else ""
    )

    return html_wrap(
        _esc(tx('ph.md_title')), _CSS,
        f"""<div class="hero">
  <div class="kicker">M C P R E H E A T</div>
  <div class="title">{_esc(tx('ph.kicker'))}</div>
  <div class="head">{_esc(pre.headline)}</div>
  {('<div class="sub">' + _esc(tx('ph.lbl_data_time', t=pre.server_time)) + '</div>') if pre.server_time else ''}
  {count_html}
  {unparsed_html}
  {coupon_unparsed_html}
</div>

{danger_html}
{urgent_html}
{ok_html}
{score_html}
{ammo_html}
{today_html}
{later_html}
{tips_html}

<div class="foot">
  {_esc(tx('ph.foot_tools'))}<br>
  {_esc(tx('ph.foot_disclaimer'))}
  <div class="cta">{_esc(tx('ph.cta', repo=REPO_URL))}</div>
</div>""",
    )
