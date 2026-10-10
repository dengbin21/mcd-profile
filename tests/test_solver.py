"""麦麦最优解（McSolve）自检：券解析 + 求解主流程 + 失败可见性。

不联网、不依赖 pytest，直接 `python tests/test_solver.py` 即可运行。

这里刻意固化了开发过程中**真实踩过并修掉的三个坑**，防止以后改算法时退化：

1. 目标函数一度是「实付最低」→ 最优解永远只点 1 件（少买当然最省）；
2. 「三件任选6折」的「三」是中文数字，正则没吃进去 → 件数约束失效；
3. 「中薯条买一送一」被无条件下发折扣 → 组合里没有中薯条也照样打折。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import MenuItem                                            # noqa: E402
from src.solver import (                                                   # noqa: E402
    MAX_ADD_HARD, MAX_ENUM, Solution, build_pool, eat_command,
    effective_max_add, enumerate_candidates, estimate_discount, grade_of, make_offline_pricer,
    parse_coupons, pick_verify_batch, solve,
)
from src.solve_report import render_solve_html, render_solve_markdown      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------- #
# 夹具
# ---------------------------------------------------------------------- #
def _menu() -> dict[str, MenuItem]:
    """一份极简菜单：1 个堡 + 若干小食，足够验证组合逻辑。"""
    raw = {
        "1001": ("板烧鸡腿堡", 21.5, 21.5),
        "1002": ("中薯条", 12.0, 12.0),
        "1003": ("脆薯饼", 8.0, 8.0),
        "1004": ("脆香油条", 7.0, 7.0),
        "1005": ("可乐中杯", 9.0, 9.0),
        "1006": ("香芋派", 7.5, 7.5),
        "1007": ("麦旋风", 9.5, 9.5),
    }
    return {c: MenuItem(code=c, name=n, price=p, original_price=o)
            for c, (n, p, o) in raw.items()}


def _named(menu: dict[str, MenuItem], *names: str) -> list[MenuItem]:
    out = []
    for n in names:
        hit = [i for i in menu.values() if i.name == n]
        assert hit, f"夹具里没有 {n}"
        out.append(hit[0])
    return out


# ---------------------------------------------------------------------- #
# 券解析
# ---------------------------------------------------------------------- #
def test_parse_coupon_kinds():
    rules = {r.title: r for r in parse_coupons([
        "满30减5元券", "三件任选6折", "免费中薯条", "中薯条买一送一", "8折券", "麦旋风任选",
    ])}
    assert rules["满30减5元券"].kind == "threshold"
    assert rules["满30减5元券"].threshold == 30.0 and rules["满30减5元券"].off == 5.0

    assert rules["三件任选6折"].kind == "bundle"
    assert rules["三件任选6折"].need == 3                 # ← 中文数字（坑 2）
    assert abs(rules["三件任选6折"].off - 0.6) < 1e-6

    assert rules["免费中薯条"].kind == "free"
    assert rules["免费中薯条"].free_name == "中薯条"

    assert rules["中薯条买一送一"].kind == "bogo"
    assert rules["中薯条买一送一"].free_name == "中薯条"  # ← 记住送的是什么

    assert rules["8折券"].kind == "percent"
    assert rules["麦旋风任选"].kind == "unknown"          # 解析不出就老实降级


def test_parse_coupon_dedup_and_empty():
    assert parse_coupons([]) == []
    assert parse_coupons(["", "  ", None]) == []
    # 同文案只保留一条
    assert len(parse_coupons(["满30减5", "满30减5"])) == 1


def test_bundle_needs_enough_items():
    """坑 2 的另一半：件数不够时**不能**估出折扣。"""
    menu = _menu()
    rules = parse_coupons(["三件任选6折"])
    one = _named(menu, "板烧鸡腿堡")
    three = _named(menu, "板烧鸡腿堡", "脆薯饼", "脆香油条")
    assert estimate_discount(one, rules) == 0.0, "只点 1 件不该享受三件折扣"
    assert estimate_discount(three, rules) > 0, "凑够 3 件才应有折扣"


def test_bogo_requires_the_named_item():
    """坑 3：买一送一必须真的点了 2 件该商品，不能无条件下发。"""
    menu = _menu()
    rules = parse_coupons(["中薯条买一送一"])
    no_fries = _named(menu, "板烧鸡腿堡", "脆薯饼")
    assert estimate_discount(no_fries, rules) == 0.0, "没有中薯条不该打折"

    one_fries = _named(menu, "板烧鸡腿堡", "中薯条")
    assert estimate_discount(one_fries, rules) == 0.0, "只点 1 份中薯条不满足买一送一"

    two_fries = _named(menu, "中薯条", "中薯条")
    assert estimate_discount(two_fries, rules) > 0, "点 2 份中薯条才送"


def test_estimate_discount_never_exceeds_subtotal():
    """估算再离谱也不能估出负价——它是排序用的，但越界会让排序失去意义。"""
    menu = _menu()
    rules = parse_coupons(["满30减5元券", "三件任选6折", "免费中薯条", "1折券"])
    items = _named(menu, "板烧鸡腿堡", "中薯条")
    subtotal = sum(i.price for i in items)
    assert 0 <= estimate_discount(items, rules) <= subtotal


# ---------------------------------------------------------------------- #
# 求解主流程
# ---------------------------------------------------------------------- #
def test_solve_does_not_degenerate_to_buying_less():
    """坑 1 的回归测试：有凑单券时，最优解必须比「只点必选」多出东西。

    如果这条挂了，说明目标函数又退化成「实付最低」了——那求解器
    就只是在劝人少买，而不是教人凑单。
    """
    menu = _menu()
    rules = parse_coupons(["三件任选6折", "免费脆薯饼"])
    pricer = make_offline_pricer(menu, rules)
    sol = solve(["1001"], menu, rules, pricer, max_add=3)
    assert sol.items, "应当求出解"
    assert len(sol.items) > 1, f"最优解不该只点 1 件，实际 {[i.name for i in sol.items]}"
    assert sol.baseline_items and len(sol.baseline_items) == 1
    assert sol.enum_count > 1 and sol.verify_count <= 30


def test_solve_baseline_is_must_only():
    """baseline 必须恒等于「只点必选」，否则「直觉点法」的对照就失真了。"""
    menu = _menu()
    rules = parse_coupons(["满30减5元券"])
    sol = solve(["1001", "1005"], menu, rules, make_offline_pricer(menu, rules), max_add=2)
    assert {i.name for i in sol.baseline_items} == {"板烧鸡腿堡", "可乐中杯"}
    # 21.5 + 9.0 = 30.5，正好够「满30减5」门槛 → 实付 25.5
    assert abs(sol.baseline_paid - 25.5) < 0.01, f"baseline 实付应为 25.5，实际 {sol.baseline_paid}"


def test_solve_respects_budget():
    menu = _menu()
    rules = parse_coupons(["满30减5元券", "三件任选6折"])
    sol = solve(["1001"], menu, rules, make_offline_pricer(menu, rules),
                budget=25.0, max_add=3)
    assert sol.items, "预算内应当有解"
    assert sol.paid <= 25.0 + 1e-6, f"实付 {sol.paid} 超出预算 25"
    # 预算只剪候选，不剪「试了多少种」的上报
    assert sol.enum_count > sol.valid_count or sol.valid_count == sol.enum_count


def test_solve_impossible_budget():
    """预算低于必选价 → 应无解，而不是抛异常或返回一个超预算的解。"""
    menu = _menu()
    rules = parse_coupons([])
    sol = solve(["1001"], menu, rules, make_offline_pricer(menu, rules),
                budget=5.0, max_add=2)
    assert sol.items == [], "买不起就该如实说无解"


def test_solve_unknown_must_code():
    """必选商品不在菜单里 → 静默忽略，不该崩。"""
    menu = _menu()
    rules = parse_coupons([])
    sol = solve(["9999"], menu, rules, make_offline_pricer(menu, rules), max_add=1)
    assert isinstance(sol, Solution)


def test_grade_thresholds():
    assert grade_of(0.5) == "S"
    assert grade_of(0.45) == "S"
    assert grade_of(0.30) == "A"
    assert grade_of(0.15) == "B"
    assert grade_of(0.0) == "C"


# ---------------------------------------------------------------------- #
# 失败可见性（真实模式才有意义，这里用会抛异常的 pricer 模拟）
# ---------------------------------------------------------------------- #
def _flaky_pricer(menu, rules, fail_on):
    """在指定下标上抛异常的验价器，用来模拟网络抖动。"""
    base = make_offline_pricer(menu, rules)
    state = {"n": 0}

    def pricer(pairs):
        idx = state["n"]
        state["n"] += 1
        if idx in fail_on:
            raise RuntimeError("模拟网络抖动")
        return base(pairs)

    return pricer


def test_all_verify_fail_is_reported_not_silently_empty():
    """全部验价失败时，必须能区分「没解」和「接口挂了」。"""
    menu = _menu()
    rules = parse_coupons(["三件任选6折"])
    sol = solve(["1001"], menu, rules, _flaky_pricer(menu, rules, fail_on=set(range(100))),
                max_add=2)
    assert sol.items == []
    assert sol.fail_count == sol.verify_count > 0
    assert sol.verify_ok == 0


def test_partial_fail_still_solves_and_is_disclosed():
    """部分失败：仍能出解，但失败次数必须计数并被战报披露。"""
    menu = _menu()
    rules = parse_coupons(["三件任选6折", "免费脆薯饼"])
    sol = solve(["1001"], menu, rules, _flaky_pricer(menu, rules, fail_on={0, 3, 7}),
                max_add=3)
    assert sol.items, "部分失败不该导致无解"
    assert sol.fail_count == 3
    assert sol.verify_ok == sol.verify_count - 3

    md = render_solve_markdown(sol)
    html = render_solve_html(sol)
    assert "3" in md and "失败" in md, "Markdown 必须披露验价失败"
    assert "失败" in html, "HTML 战报必须披露验价失败"


# ---------------------------------------------------------------------- #
# 并发与护栏
# ---------------------------------------------------------------------- #
def test_parallel_matches_sequential():
    """并发验价只是提速，结果必须与串行**完全一致**（含 baseline）。"""
    menu = _menu()
    rules = parse_coupons(["三件任选6折", "免费脆薯饼", "满30减5元券"])
    args = (["1001"], menu, rules)
    seq = solve(*args, make_offline_pricer(menu, rules), max_add=3, workers=1)
    par = solve(*args, make_offline_pricer(menu, rules), max_add=3, workers=4)
    assert [i.name for i in seq.items] == [i.name for i in par.items]
    assert seq.paid == par.paid and seq.discount == par.discount
    assert seq.baseline_paid == par.baseline_paid


def test_effective_max_add_cap():
    """组合数随件数爆炸，必须整层收敛，而不是跑到一半截断。"""
    # C(24,1..4)=12951 未超；C(24,5) 加入后 5.4 万 > 2 万
    assert effective_max_add(24, 3) == 3
    assert effective_max_add(24, 4) == 4
    assert effective_max_add(24, 8) == 4, "超出上限应收敛到 4 层"
    assert effective_max_add(24, 99) <= MAX_ADD_HARD
    assert effective_max_add(0, 3) == 0


def test_huge_add_does_not_explode():
    """用户传 --add 99 时，枚举量必须被钳住，不能把 CPU 跑满。"""
    menu = _menu()
    rules = parse_coupons(["三件任选6折"])
    cands, total = enumerate_candidates(["1001"], menu, rules, max_add=99)
    assert total <= MAX_ENUM + len(menu), f"枚举数 {total} 未被有效钳制"


def test_build_pool_prioritizes_free_coupon_items():
    """被免费券点名的商品必须排在凑单池最前（不点白不点）。"""
    menu = _menu()
    rules = parse_coupons(["免费香芋派"])
    pool = build_pool(menu, rules, exclude={"1001"}, limit=3)
    assert pool[0].name == "香芋派", f"香芋派应优先，实际首位 {pool[0].name}"


def test_pick_verify_batch_keeps_baseline_first_and_dedups():
    menu = _menu()
    rules = parse_coupons(["三件任选6折"])
    cands, _ = enumerate_candidates(["1001"], menu, rules, max_add=2)
    batch = pick_verify_batch(cands, top_n=5)
    assert len(batch) <= 5
    assert batch[0].codes == ("1001",), "baseline 必须排在第一位"
    keys = [c.key for c in batch]
    assert len(keys) == len(set(keys)), "同一商品集合只应验一次"


# ---------------------------------------------------------------------- #
# 渲染冒烟
# ---------------------------------------------------------------------- #
def test_render_smoke():
    menu = _menu()
    rules = parse_coupons(["三件任选6折", "免费脆薯饼"])
    sol = solve(["1001"], menu, rules, make_offline_pricer(menu, rules), max_add=3)
    md = render_solve_markdown(sol, store_name="测试门店", offline=True)
    html = render_solve_html(sol, store_name="测试门店", offline=True)
    assert "麦麦最优解" in md and "calculate-price" in md
    assert "github.com/dengbin21/mcd-profile" in md, "战报必须带项目地址（转化点）"
    assert "麦麦最优解" in html and "<style>" in html
    assert "演示模式" in md, "离线口径必须声明"


def test_render_empty_solution():
    sol = Solution()
    assert "没有求出可行组合" in render_solve_markdown(sol)
    assert "没有求出可行组合" in render_solve_html(sol)


def test_eat_command_closes_the_loop():
    """算完最优解必须能直接拿去下单——这是 solve→eat 闭环的断点。"""
    menu, rules = _menu(), parse_coupons(["满30减5元券"])
    sol = solve(["1001"], menu, rules, make_offline_pricer(menu, rules), max_add=2)
    assert sol.items, "前置条件：应当求出解"

    cmd = eat_command(sol, "1990262")
    assert cmd.startswith("python -m src.cli eat --store 1990262 --items ")
    for i in sol.items:
        assert f"{i.product_code}:1" in cmd, f"{i.name} 未出现在下单命令里"
    # 无门店时也要能跑（用户可让 eat 自己选店）
    assert eat_command(sol).startswith("python -m src.cli eat --items ")
    assert Solution() and eat_command(Solution()) == "", "无解时不应产出命令"


def test_report_discloses_discount_vs_paid_gap():
    """「折扣力度」与「多花」会并排出现，必须解释口径，否则读成自相矛盾。"""
    menu, rules = _menu(), parse_coupons(["三件任选6折"])
    sol = solve(["1001"], menu, rules, make_offline_pricer(menu, rules), max_add=2)
    md = render_solve_markdown(sol)
    html = render_solve_html(sol)
    assert "折扣力度" in md and "折扣力度" in html, "「省下」应改为无歧义的「折扣力度」"
    if sol.saved <= 0 and sol.count != sol.baseline_count:
        assert "口径" in md and "口径" in html, "实付更高时必须说明两个数字的口径差异"


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
    print(f"\n{'全部通过' if not fails else f'{fails} 个失败'}"
          f"（共 {sum(1 for n in globals() if n.startswith('test_'))} 项）")
    sys.exit(1 if fails else 0)
