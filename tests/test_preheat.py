"""麦麦预热台（McPreheat）自检：日期解析 + 冲突检测 + 备战度。

不联网、不依赖 pytest，直接 `python tests/test_preheat.py` 即可运行。

固化两个**真实踩过的坑**：

1. ``pick_target`` 一度把「今天开始」的活动也当倒计时目标 → 倒计时恒为 0，
   整个钩子失效（预热台变成一张写着「就是今天」的废卡）；
2. 备战度权重给得太松 → 3 张券里有 1 张赶不上活动，仍被评为 **S（弹药充足）**，
   和卡片上同时出现的「有 1 张券等不到那天」自相矛盾。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import CampaignEvent, Coupon                               # noqa: E402
from src.preheat import (                                                  # noqa: E402
    build_preheat, parse_when, pick_target, remaining_parts,
)
from src.preheat_report import render_preheat_html, render_preheat_markdown  # noqa: E402

TODAY = date(2026, 10, 9)

CAMPAIGNS = [
    CampaignEvent(date="2026-10-09", title="超值9.9元早餐两件套", content="凭券两件套9.9元",
                  stage="today"),
    CampaignEvent(date="2026-10-16", title="秋日限定新品上新", content="季节新品", stage="future"),
    CampaignEvent(date="2026-10-25", title="周末欢乐桶限时回归", content="周末限定", stage="future"),
]

COUPONS = [
    Coupon(title="免费香芋派", available_until="2026.10.16 23:59"),
    Coupon(title="满30减5元券", available_until="2026.10.12 23:59"),
    Coupon(title="免费中薯条", available_until="2026.12.01 23:59"),
]


def _pre(**kw):
    return build_preheat(CAMPAIGNS, COUPONS, today=TODAY,
                         server_time="2026-10-09 16:48:16",
                         points=1320.1, redeem_points=[100, 200, 500, 800, 1600], **kw)


# ---------------------------------------------------------------------- #
# 日期解析
# ---------------------------------------------------------------------- #
def test_parse_when_formats():
    assert parse_when("2026.10.16 23:59") == date(2026, 10, 16)
    assert parse_when("2026-10-16") == date(2026, 10, 16)
    assert parse_when("2026/10/16") == date(2026, 10, 16)
    assert parse_when("2026-10-09T16:48:16") == date(2026, 10, 9)
    # 解析不出来就返回 None，绝不猜
    assert parse_when("") is None
    assert parse_when("长期有效") is None
    assert parse_when(None) is None


# ---------------------------------------------------------------------- #
# 预热目标（坑 1）
# ---------------------------------------------------------------------- #
def test_target_is_strictly_future():
    """坑 1 的回归：今天开始的活动不能当倒计时目标，否则倒计时恒为 0。"""
    t = pick_target(CAMPAIGNS, TODAY)
    assert t is not None and t.title == "秋日限定新品上新", f"目标应为 10-16 那场，实际 {t}"
    pre = _pre()
    assert pre.days_left == 7
    assert [c.title for c in pre.running] == ["超值9.9元早餐两件套"]


def test_target_advances_as_time_passes():
    """时间推进后目标应自动切到下一场。"""
    p1 = build_preheat(CAMPAIGNS, COUPONS, today=date(2026, 10, 20))
    assert p1.target.title == "周末欢乐桶限时回归" and p1.days_left == 5


def test_no_future_campaign():
    """没有未来活动时不能崩，且要给出明确文案。"""
    pre = build_preheat(CAMPAIGNS, COUPONS, today=date(2026, 11, 1))
    assert pre.target is None and pre.days_left is None
    assert "没有" in pre.headline
    assert pre.score > 0


# ---------------------------------------------------------------------- #
# 冲突检测（钩子的主体）
# ---------------------------------------------------------------------- #
def test_conflict_detected():
    pre = _pre()
    miss = {c.title for c in pre.missing}
    assert miss == {"满30减5元券"}, f"只有满30减5赶不上，实际 {miss}"
    assert {c.title for c in pre.surviving} == {"免费香芋派", "免费中薯条"}
    assert "等不到那天" in pre.headline
    assert pre.progress > 0


def test_conflict_grows_when_target_is_later():
    """目标越远，赶不上的券越多。"""
    p = build_preheat(CAMPAIGNS, COUPONS, today=date(2026, 10, 20))
    assert len(p.missing) == 2, f"10-25 那场应有 2 张券赶不上，实际 {len(p.missing)}"


def test_expired_coupon():
    """已过期的券：算作赶不上，且提示语要说「已过期」而不是负数天。"""
    cs = [Coupon(title="古早券", available_until="2026.09.01 23:59")]
    p = build_preheat(CAMPAIGNS, cs, today=TODAY)
    assert len(p.missing) == 1
    assert p.coupons[0].expired
    assert any("过期" in t for t in p.tips)


def test_tight_flag():
    """撑得到但到期日就在眼前 → 标「压线」。"""
    pre = _pre()
    tight = {c.title for c in pre.surviving if c.tight}
    assert tight == {"免费香芋派"}, f"香芋派 7 天内到期应压线，实际 {tight}"


def test_coupon_without_expiry():
    """没有到期时间的券：不参与冲突判断，也不该崩。"""
    cs = [Coupon(title="神秘券", available_until="")]
    p = build_preheat(CAMPAIGNS, cs, today=TODAY)
    assert p.coupons[0].until is None
    assert p.coupons[0].survives is None
    assert p.missing == []


# ---------------------------------------------------------------------- #
# 备战度（坑 2）
# ---------------------------------------------------------------------- #
def test_score_penalty_beats_bonus():
    """坑 2 的回归：有券赶不上时，绝不能还评 S。

    「卡片上写着有 1 张券等不到那天，评级却是 S 弹药充足」是自相矛盾的。
    """
    pre = _pre()
    assert pre.missing, "本用例前提：存在赶不上的券"
    assert pre.grade in ("A", "B", "C"), f"有冲突却评到 {pre.grade}（{pre.score}）"
    assert pre.score < 85


def test_score_clean_is_high():
    """反过来：券包干干净净时应该拿高分。"""
    cs = [Coupon(title="长期券", available_until="2026.12.31 23:59")]
    p = build_preheat(CAMPAIGNS, cs, today=TODAY, points=1320.1,
                      redeem_points=[100, 200])
    assert not p.missing and not p.urgent
    assert p.score >= 85 and p.grade == "S"


def test_score_clamped():
    """再糟也不能出 0 以下、100 以上。"""
    cs = [Coupon(title=f"券{i}", available_until="2026.10.10 23:59") for i in range(10)]
    p = build_preheat(CAMPAIGNS, cs, today=TODAY)
    assert 0 <= p.score <= 100


def test_all_coupons_miss():
    """有券、但**全部**赶不上 → 明确提示「等于原价进场」。"""
    cs = [Coupon(title="短命券", available_until="2026.10.10 23:59")]
    p = build_preheat(CAMPAIGNS, cs, today=TODAY)
    assert p.missing and not p.surviving
    assert any("原价" in t for t in p.tips)


def test_no_coupon_data_is_not_over_claimed():
    """拿不到券数据时**不臆测**：既不说「原价进场」，也不崩。

    「用户一张券都没有」和「券接口没返回」在代码里长一样，
    口径诚实的选择是闭嘴，而不是编一句吓人的话。
    """
    p = build_preheat(CAMPAIGNS, [], today=TODAY)
    assert p.surviving == [] and p.missing == []
    assert p.tips, "至少要有一条兜底建议"
    assert not any("原价" in t for t in p.tips)


# ---------------------------------------------------------------------- #
# 积分 / 其他
# ---------------------------------------------------------------------- #
def test_points_redeemable():
    pre = _pre()
    assert pre.redeem_floor == 100
    assert pre.redeemable == 4          # 1320 分够兑 100/200/500/800
    assert any("够兑" in t for t in pre.tips)


def test_remaining_parts():
    pre = _pre()
    d, h, m, s = remaining_parts(pre)
    assert d == 7 and h == 0 and m == 0 and s == 0


def test_remaining_parts_zero_when_started():
    p = build_preheat([], [], today=TODAY)
    assert remaining_parts(p) == (0, 0, 0, 0)


# ---------------------------------------------------------------------- #
# 渲染
# ---------------------------------------------------------------------- #
def test_render_smoke():
    pre = _pre()
    md = render_preheat_markdown(pre)
    html = render_preheat_html(pre)
    assert "麦麦预热台" in md and "等不到那天" in md
    assert "github.com/dengbin21/mcd-profile" in md, "战报必须带项目地址（转化点）"
    assert "倒计时" in md or "秋日限定新品上新" in md
    for k in ("麦麦预热台", "campaign-calendar", "<svg", "danger"):
        assert k in html, f"战报 HTML 缺少 {k}"
    assert "class=.cunit." not in html, "HTML 里混入了占位引号"


def test_render_no_target():
    p = build_preheat([], [], today=TODAY)
    assert "麦麦预热台" in render_preheat_markdown(p)
    assert "麦麦预热台" in render_preheat_html(p)


def test_unparsed_campaign_is_disclosed_not_silently_dropped():
    """日期读不懂必须披露。

    否则预热台会静默退化成「没有可预热的活动」，而 campaign 命令
    （按官方 stage 分桶）照常显示——两处对不上就是 bug。
    """
    bad = [CampaignEvent(date="10月16日", title="秋日上新", stage="future")]
    p = build_preheat(bad, [], today=TODAY)
    assert p.unparsed_count == 1, "解析失败必须计数"
    assert p.target is None and not p.running and not p.upcoming

    md = render_preheat_markdown(p)
    html = render_preheat_html(p)
    assert "未能解析" in md, "Markdown 必须说明日期未解析，而不是假装没活动"
    assert "未能解析" in html, "HTML 必须说明日期未解析"
    assert "没有可预热的活动" not in md, "不能把「读不懂」说成「没有」"


def test_unparsed_mixed_with_parsed_still_works():
    """部分解析失败时，可读的那部分照常工作，同时披露跳过的条数。"""
    mixed = CAMPAIGNS + [CampaignEvent(date="十月三十日", title="读不懂的活动")]
    p = build_preheat(mixed, COUPONS, today=TODAY)
    assert p.unparsed_count == 1
    assert p.target is not None and p.target.title == "秋日限定新品上新"
    assert "未能解析" in render_preheat_markdown(p)


def test_urgent_section_labels_its_window():
    """临期券在 account(30天) / preheat(7天) 两处口径不同，必须各自标死。"""
    p = _pre()
    assert p.urgent, "前置条件：样例里应当有临期券"
    md = render_preheat_markdown(p)
    assert "即将到期（7 天内）" in md, "不标窗口会和 account 的「30 天内到期」打架"


# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            fails += 1
            print(f"  ✗ {name}: {exc}")
        except Exception as exc:                                           # noqa: BLE001
            fails += 1
            print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    total = sum(1 for n in globals() if n.startswith("test_"))
    print(f"\n{'全部通过' if not fails else f'{fails} 个失败'}（共 {total} 项）")
    sys.exit(1 if fails else 0)
