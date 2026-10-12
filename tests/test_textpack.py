"""文案层（WorkBuddy 在环）的测试。

守三条底线：

1. **引用的文案键必须存在**——注册表里没有的 key 会静默渲染成空字符串，
   卡片上就是一个没有标题的空区块，很难发现（历史上真的发生过：``ph.sec_urgent`` 漏定义）；
2. **模型文案不能弄丢数值**——删掉 ``{占位符}`` 时必须回退默认，而不是显示残缺；
3. **模型文案不能夹带编造的数字**——不在 ``facts`` 里的数字一律回退默认，绝不进产物；
4. **模型的错误必须看得见**——键名写错、字段名写错若静默放行，用户会以为改写生效了；
5. **不注入文案包时，输出与规则期完全一致**——文案层是「可选增强」，
   不能因为抽了文案就改变默认产物。
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.preheat import build_preheat                                        # noqa: E402
from src.preheat_report import render_preheat_markdown  # noqa: E402
from src.solve_report import render_solve_html, render_solve_markdown        # noqa: E402
from src.solver import make_offline_pricer, parse_coupons, solve             # noqa: E402
from src.textpack import (                                                   # noqa: E402
    TEXT_REGISTRY, CopyPack, TextResolver, missing_placeholders,
    pick_grade_word, validate_copy_pack,
)

ROOT = Path(__file__).resolve().parent.parent
# 会调用文案解析器的模块（新增模块请加进来）
_SCAN_FILES = ["src/solve_report.py", "src/preheat_report.py", "src/preheat.py"]
_RE_KEY = re.compile(r"""\btx\(\s*['"]([a-z][\w.]*)['"]""")


def _refs() -> set[str]:
    """扫描源码里实际引用的文案键。"""
    out: set[str] = set()
    for rel in _SCAN_FILES:
        src = (ROOT / rel).read_text(encoding="utf-8")
        out.update(_RE_KEY.findall(src))
    return out


def test_all_referenced_keys_exist():
    """源码引用的每个文案键都必须在注册表里有定义。

    漏定义时 TextResolver 返回空串，产物上表现为「标题消失」，极难发现。
    """
    missing = sorted(k for k in _refs() if k not in TEXT_REGISTRY)
    assert not missing, f"以下文案键未定义（会渲染成空）：{missing}"


def test_registry_defaults_are_strings():
    for k, v in TEXT_REGISTRY.items():
        assert isinstance(v.get("default"), str), f"{k} 的 default 不是字符串"
        assert v.get("desc"), f"{k} 缺少 desc（模型要靠 desc 理解该改什么）"


def test_no_placeholder_leftover_in_rendered_output():
    """渲染结果里不能残留未填充的 ``{占位符}``。"""
    sol = _solve()
    md = render_solve_markdown(sol, offline=True)
    html = render_solve_html(sol, offline=True)
    for txt, name in ((md, "markdown"), (html, "html")):
        left = re.findall(r"\{[a-z_]+\}", txt)
        assert not left, f"solve {name} 残留占位符：{left}"


def test_missing_placeholder_is_detected():
    """模型删掉占位符 → 必须被检出。"""
    assert missing_placeholders("sv.vs_save", "白省一笔") == ["saved"]
    assert missing_placeholders("sv.vs_save", "白省 ¥{saved}") == []
    warns = validate_copy_pack(CopyPack(labels={"sv.vs_save": "白省一笔"}))
    assert warns and "saved" in warns[0]


def test_missing_placeholder_falls_back_to_default():
    """丢了占位符的那条，解析时要回退默认——宁可字不好看，也不能丢数字。"""
    tx = TextResolver(CopyPack(labels={"sv.vs_save": "白省一笔，别客气"}))
    assert "12.5" in tx("sv.vs_save", saved="12.5"), "回退默认后金额必须还在"
    # 没丢的那条照常生效
    tx2 = TextResolver(CopyPack(labels={"sv.vs_save": "白省 ¥{saved}，别客气"}))
    assert tx2("sv.vs_save", saved="12.5") == "白省 ¥12.5，别客气"


def test_unknown_number_is_flagged():
    """模型编了个 facts 里没有的数字 → 告警（不阻断，但要让人看见）。"""
    pack = CopyPack(headline="这单省了 88 元，血赚", solve={"headline": "打了 3.5 折，绝了"})
    warns = validate_copy_pack(pack, allowed_numbers={"21", "22", "40"})
    joined = " | ".join(warns)
    assert "88" in joined and "3.5" in joined


def test_known_number_passes():
    pack = CopyPack(headline="实付 21.9，稳", solve={"headline": "省了 40%"})
    assert not validate_copy_pack(pack, allowed_numbers={"21.9", "21", "40"})


def test_preheat_headline_and_grade_override():
    """模型整句覆写钩子句与评级词，且**不影响任何数值**。"""
    pre = build_preheat(_campaigns(), _coupons(), today=_TODAY)

    pack = CopyPack(preheat={"headline": "还有 7 天，但你 1 张券撑不到",
                             "grade_word": "还差一口气"})
    pre2 = build_preheat(_campaigns(), _coupons(), today=_TODAY, copy=pack)
    md2 = render_preheat_markdown(pre2, pack)

    assert "还有 7 天，但你 1 张券撑不到" in md2
    assert "还差一口气" in md2
    assert pre.headline not in md2
    # 数值未被动：分数与天数依旧由规则给出
    assert f"{pre.score}/100" in md2
    assert pre.score == pre2.score and pre.grade == pre2.grade


def test_preheat_hook_pattern_override():
    """模型改写钩子句式（保留占位符）→ 规则生成的 headline 跟着变。"""
    pack = CopyPack(labels={"ph.hook_conflict": "距「{title}」还有 {d} 天，"
                                                "但你 {n} 张券会先作废"})
    pre = build_preheat(_campaigns(), _coupons(), today=_TODAY, copy=pack)
    assert "会先作废" in pre.headline
    assert "距「" in pre.headline and "7" in pre.headline


def test_preheat_tips_override():
    pack = CopyPack(preheat={"tips": ["先把满减用掉", "别惦记新品了"]})
    pre = build_preheat(_campaigns(), _coupons(), today=_TODAY, copy=pack)
    assert pre.tips == ["先把满减用掉", "别惦记新品了"]
    assert "先用掉" not in "".join(pre.tips)


def test_solve_headline_override():
    pack = CopyPack(solve={"headline": "这单我赢麻了"})
    sol = _solve()
    html = render_solve_html(sol, offline=True, copy=pack)
    assert "这单我赢麻了" in html
    # 数值照样在
    assert f"{sol.paid:.2f}".rstrip("0").rstrip(".") in html


def test_model_text_is_html_escaped():
    """模型文案里夹带 HTML 标签时不能真的插进页面（分享卡会被注入破坏）。"""
    pack = CopyPack(solve={"headline": "<script>alert(1)</script>划算"})
    sol = _solve()
    html = render_solve_html(sol, offline=True, copy=pack)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_default_output_unchanged_without_copy():
    """不注入文案包时，文案层对产物应当是**零影响**。"""
    sol = _solve()
    assert render_solve_markdown(sol, offline=True) == \
        render_solve_markdown(sol, offline=True, copy=CopyPack())
    pre = build_preheat(_campaigns(), _coupons(), today=_TODAY)
    p0 = build_preheat(_campaigns(), _coupons(), today=_TODAY, copy=CopyPack())
    assert pre.headline == p0.headline and pre.tips == p0.tips


def test_empty_copy_pack_is_inactive():
    assert CopyPack().active is False
    assert CopyPack(labels={"sv.kicker": "随便"}).active is True
    assert CopyPack(preheat={"headline": "x"}).active is True


def test_resolver_keeps_placeholders():
    tx = TextResolver(CopyPack(labels={"sv.enum_line": "试了 {n} 种组合"}))
    assert tx("sv.enum_line", n=1234) == "试了 1234 种组合"


# ---------------------------------------------------------------------- #
# 护栏：模型写文案最常犯的三个错，必须**看得见**，不能静默放行
# ---------------------------------------------------------------------- #
def test_unknown_key_is_reported_with_suggestion():
    """键名写错 = 这条改写根本不会生效，必须告警（否则用户以为生效了）。"""
    pack = CopyPack(labels={"sv.hero_title": "x"})
    warns = validate_copy_pack(pack)
    assert warns and "sv.hero_title" in warns[0]
    assert "sv.md_title" in warns[0]          # 还要给出「是不是想写这个」


def test_unknown_block_field_is_reported():
    """solve.grad_word（拼错）、preheat.tips 之外的字段同样会静默失效。"""
    warns = validate_copy_pack(CopyPack(solve={"grad_word": "x"}))
    assert any("solve.grad_word" in w for w in warns)
    assert not validate_copy_pack(CopyPack(solve={"grade_word": "神之一单"}))


def test_numeric_leak_in_labels_is_reported():
    """模型夹带 facts 里没有的数字 = 编造，必须报。"""
    pack = CopyPack(labels={"sv.sec_solution": "闭眼点 ¥18.5 那套"})
    assert not validate_copy_pack(pack)                       # 没给 facts，不查数值
    warns = validate_copy_pack(pack, {"21", "3"})
    assert any("18.5" in w for w in warns)
    # facts 里有的数字不算编造
    assert not validate_copy_pack(
        CopyPack(labels={"sv.sec_solution": "闭眼点 ¥21 那套"}), {"21"})


def test_leaked_number_never_reaches_output():
    """告警之外还要**真回退**：编的数字不能上卡片。"""
    pack = CopyPack(labels={"sv.sec_solution": "闭眼点 ¥18.5 那套"})
    tx = TextResolver(pack)
    assert "18.5" in tx("sv.sec_solution")          # 未绑定 facts：只告警，不猜
    pack.bind_facts({"paid": 21.9})
    assert "18.5" not in TextResolver(pack)("sv.sec_solution")
    assert TextResolver(pack)("sv.sec_solution") == TEXT_REGISTRY["sv.sec_solution"]["default"]


def test_bind_facts_does_not_break_legit_copy():
    """绑定 facts 后，正常改写仍要生效（护栏不能误伤）。"""
    pack = CopyPack(labels={"sv.sec_solution": "照着点，别犹豫",
                            "sv.vs_save": "白省 ¥{saved}"})
    pack.bind_facts({"saved": 9.0})
    tx = TextResolver(pack)
    assert tx("sv.sec_solution") == "照着点，别犹豫"
    assert tx("sv.vs_save", saved=9) == "白省 ¥9"


def test_grade_word_supports_string_and_mapping():
    """评级词两种写法：整词字符串 / {评级: 词}；映射写法没覆盖的档位回退默认。"""
    assert pick_grade_word({"grade_word": "神之一单"}, "A") == "神之一单"
    m = {"grade_word": {"S": "神之一单", "A": "这单稳赚"}}
    assert pick_grade_word(m, "A") == "这单稳赚"
    assert pick_grade_word(m, "C") == ""
    assert pick_grade_word({}, "A") == ""


def test_grade_word_mapping_survives_copy_pack_load(tmp_path=None):
    """_str_map 曾经会**吞掉** dict 类型，分级评级词直接失效。"""
    import json
    from pathlib import Path

    target = Path(str(tmp_path)) if tmp_path else Path(tempfile.mkdtemp())
    p = target / "_gw_test.json"
    p.write_text(json.dumps({"solve": {"grade_word": {"A": "这单稳赚"}}}), encoding="utf-8")
    try:
        pack = CopyPack.load(p)
        assert pick_grade_word(pack.solve, "A") == "这单稳赚"
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------- #
# 夹具
# ---------------------------------------------------------------------- #
_TODAY = __import__("datetime").date(2026, 10, 9)


def _campaigns():
    from src.models import CampaignEvent
    return [
        CampaignEvent(title="秋日限定新品上新", date="2026-10-16",
                      content="季节新品限时尝鲜", stage="future"),
        CampaignEvent(title="周末欢乐桶限时回归", date="2026-10-25",
                      content="", stage="future"),
    ]


def _coupons():
    class C:
        def __init__(self, title, until):
            self.title, self.available_until = title, until
    return [C("满30减5元券", "2026.10.12 23:59"),
            C("免费香芋派", "2026.10.16 23:59"),
            C("免费中薯条", "2026.12.01 23:59")]


def _solve():
    from src.solver import load_sample_menu, sample_coupon_titles

    menu, _ = load_sample_menu()
    rules = parse_coupons(sample_coupon_titles())
    code = "9900010001" if "9900010001" in menu else next(iter(menu))
    return solve([code], menu, rules, make_offline_pricer(menu, rules), max_add=3)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✓ {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  ✗ {name}: {exc}")
            except Exception as exc:                                         # noqa: BLE001
                fails += 1
                print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    print(f"\n{'FAILED' if fails else 'ALL PASSED'}（{fails} failed）")
