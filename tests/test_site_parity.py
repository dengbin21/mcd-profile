"""落地页（纯前端）求解器 与 Python 求解器的**一致性**自检。

为什么需要这个测试
--------------------
``site/index.html`` 为了「免登录就能玩」，在 JS 里**独立实现了一遍**求解器；
``src/solver.py`` 是同一套算法的 Python 版本。两份实现靠人肉同步，
改了一边忘了另一边，页面上算出来的结果就和 CLI 对不上了——
而这种漂移**不会让任何既有测试变红**，只会静静地在演示里出错。

这里把页面里的 JS 抽出来用 node 跑，再把页面自带的菜单/券数据喂给 Python，
两边用**完全相同的输入**求解，逐项比对结果。

node 不可用时跳过（不阻塞 CI）。
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import CampaignEvent, Coupon, MenuItem                     # noqa: E402
from src.preheat import build_preheat, parse_until, parse_when             # noqa: E402
from src.solver import make_offline_pricer, parse_coupons, solve           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site" / "index.html"

# 预热台比对的注入日期：覆盖「有冲突」「冲突变多」「活动已过完」三种状态
PREHEAT_DAYS = ["2026-10-09", "2026-10-20", "2026-11-01"]

# 日期解析比对取样：覆盖区间 / 单一日期 / 带时刻 / 中文 / 「今日」/ 读不懂
# 「区间」这条是真实接口打出来的坑，页面和 CLI 里各埋了一份，只修一边等于没修。
DATE_SAMPLES = ["2026.10.16 23:59", "2026-10-16", "2026/10/16", "2026-10-09T16:48:16",
                "2026.10.05-2026.10.11", "2026.10.11-2026.10.11",
                "10月16日", "今日", "长期有效", ""]

# 与页面里的 MAX_ADD(=3) 保持一致；top_n 放大到不裁剪，以隔离「只验 Top30」的差异
CASES = [
    (["9900010001"], 0),                    # 板烧鸡腿堡，不限预算
    (["9900010001", "9900010037"], 30),     # + 可乐中杯，预算 30
    (["9900010002"], 0),                    # 巨无霸
    (["9900010026"], 25),                   # 中薯条（买一送一券），预算 25
    (["9900010033"], 0),                    # 圆筒冰淇淋（最便宜的起点）
]


def _node() -> str | None:
    return shutil.which("node")


def _site_script() -> str:
    """抽出页面 <script> 里「求解核心」那一段（DOM 交互部分不参与）。"""
    html = SITE.read_text(encoding="utf-8")
    m = re.search(r"<script>(.*?)</script>", html, re.S)
    assert m, "落地页里找不到 <script>"
    js = m.group(1)
    cut = js.find("const pick=")
    assert cut > 0, "找不到求解核心与 DOM 部分的分界"
    return js[:cut]


def _run_node(core: str) -> dict:
    """用 node 执行求解核心，返回 {menu, titles, results}。"""
    harness = (
        core
        + "\nconst out=[];\n"
        + f"for(const [codes,budget] of {json.dumps(CASES, ensure_ascii=False)}) {{\n"
        + "  const r=solve(codes,budget);\n"
        + "  out.push({must:codes,budget,\n"
        + "    names:r.best.items.map(i=>i[1]),\n"
        + "    paid:Math.round(r.best.paid*100)/100,\n"
        + "    orig:Math.round(r.best.orig*100)/100,\n"
        + "    basePaid:Math.round(r.baseline.paid*100)/100,\n"
        + "    total:r.total});\n"
        + "}\n"
        + "console.log(JSON.stringify({menu:MENU,titles:TITLES,results:out}));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(harness)
        path = fh.name
    try:
        proc = subprocess.run([_node(), path], capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    assert proc.returncode == 0, f"node 执行失败：{proc.stderr[:500]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_site_solver_matches_python():
    node = _node()
    if not node:
        print("  ~ 未找到 node，跳过落地页一致性校验")
        return

    data = _run_node(_site_script())

    # 用**页面自带的**菜单与券喂给 Python，保证输入完全一致
    menu: dict[str, MenuItem] = {}
    for code, name, price, orig in data["menu"]:
        menu[str(code)] = MenuItem(code=str(code), name=name,
                                   price=float(price), original_price=float(orig))
    titles = list(data["titles"])
    rules = parse_coupons(titles)

    assert len(menu) > 20, f"页面菜单条目异常：{len(menu)}"
    # 页面至少得解析出「三件任选6折」这类关键规则，否则演示就是假的
    kinds = {r.kind for r in rules}
    assert "bundle" in kinds and "threshold" in kinds, f"券规则解析异常：{kinds}"

    for case, js_res in zip(CASES, data["results"], strict=True):
        codes, budget = case
        sol = solve(list(codes), menu, rules, make_offline_pricer(menu, rules),
                    budget=budget, max_add=3, top_n=9999)
        py_names = [i.name for i in sol.items]
        assert py_names == js_res["names"], (
            f"最优解不一致 {codes} 预算{budget}\n"
            f"  JS : {js_res['names']} ¥{js_res['paid']}\n"
            f"  PY : {py_names} ¥{sol.paid}")
        assert abs(sol.paid - js_res["paid"]) < 0.011, (
            f"实付不一致 {codes}: JS {js_res['paid']} vs PY {sol.paid}")
        assert abs(sol.baseline_paid - js_res["basePaid"]) < 0.011, (
            f"直觉点法不一致 {codes}: JS {js_res['basePaid']} vs PY {sol.baseline_paid}")


def test_site_preheat_matches_python():
    """预热台同样有两份实现（页面 JS / Python），一并比对。

    用**固定的 today** 注入两边，避免「跑测试的日期不同」导致假失败。
    """
    node = _node()
    if not node:
        print("  ~ 未找到 node，跳过预热台一致性校验")
        return

    core = _site_script()
    harness = (
        core
        + "\nconst out=[];\n"
        + f"for(const t of {json.dumps(PREHEAT_DAYS)}) {{\n"
        + "  const r=buildPreheat(t);\n"
        + "  out.push({day:t,headline:r.headline,daysLeft:r.daysLeft,\n"
        + "    score:r.score,grade:r.grade,\n"
        + "    target:r.target?r.target.title:null,\n"
        + "    missing:r.missing.map(w=>w.title),\n"
        + "    surviving:r.surviving.map(w=>w.title)});\n"
        + "}\n"
        + "console.log(JSON.stringify({campaigns:CAMPAIGNS,coupons:COUPONS,results:out}));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(harness)
        path = fh.name
    try:
        proc = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    assert proc.returncode == 0, f"node 执行失败：{proc.stderr[:500]}"
    data = json.loads(proc.stdout.strip().splitlines()[-1])

    # 用页面自带的活动/券数据喂给 Python
    campaigns = [CampaignEvent(date=c["date"], title=c["title"],
                               content=c.get("content", ""), stage=c.get("stage", "future"))
                 for c in data["campaigns"]]
    coupons = [Coupon(title=c["title"], available_until=c.get("until", ""))
               for c in data["coupons"]]
    assert campaigns and coupons, "页面缺少预热台数据"

    for day, js in zip(PREHEAT_DAYS, data["results"], strict=True):
        y, m, d = (int(x) for x in day.split("-"))
        pre = build_preheat(campaigns, coupons, today=date(y, m, d),
                            points=1320.1, redeem_points=[100, 200, 500, 800, 1600])
        assert pre.headline == js["headline"], (
            f"{day} 钩子文案不一致\n  JS: {js['headline']}\n  PY: {pre.headline}")
        assert pre.days_left == js["daysLeft"], f"{day} 倒计时不一致"
        assert pre.score == js["score"] and pre.grade == js["grade"], (
            f"{day} 备战度不一致：JS {js['score']}{js['grade']} vs PY {pre.score}{pre.grade}")
        assert (pre.target.title if pre.target else None) == js["target"]
        assert [c.title for c in pre.missing] == js["missing"], f"{day} 冲突券不一致"
        assert [c.title for c in pre.surviving] == js["surviving"], f"{day} 可用券不一致"


def _run_js(core: str, tail: str) -> str:
    """把 ``tail`` 拼到页面核心 JS 后面跑一遍，返回最后一行 stdout。"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(core + "\n" + tail)
        path = fh.name
    try:
        proc = subprocess.run([_node(), path], capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    assert proc.returncode == 0, f"node 执行失败：{proc.stderr[:500]}"
    return proc.stdout.strip().splitlines()[-1]


def test_site_date_parsing_matches_python():
    """JS 的 ``pd`` / ``pu`` 与 Python 的 ``parse_when`` / ``parse_until`` 必须同口径。

    券面到期写成区间 ``2026.10.05-2026.10.11`` 时，取首段会把它判成「5 天前已过期」。
    这个坑在页面 JS 和 CLI 里**各埋了一份**，靠人肉同步迟早只修一边——
    页面演示里的券到期时间与 CLI 算出来的对不上，而没有任何既有测试会变红。
    """
    node = _node()
    if not node:
        print("  ~ 未找到 node，跳过日期解析一致性校验")
        return

    tail = (
        "const iso=d=>d?d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')"
        "+'-'+String(d.getDate()).padStart(2,'0'):null;\n"
        f"const out=[];\nfor(const s of {json.dumps(DATE_SAMPLES, ensure_ascii=False)}) {{\n"
        "  out.push([s, iso(pd(s)), iso(pu(s))]);\n}\n"
        "console.log(JSON.stringify(out));\n"
    )
    rows = json.loads(_run_js(_site_script(), tail))
    assert len(rows) == len(DATE_SAMPLES), "取样条数对不上，harness 可能没跑全"

    for s, js_first, js_last in rows:
        py_first, py_last = parse_when(s), parse_until(s)
        assert (py_first.isoformat() if py_first else None) == js_first, (
            f"活动日期解析不一致：{s!r}  JS {js_first} vs PY {py_first}")
        assert (py_last.isoformat() if py_last else None) == js_last, (
            f"券到期解析不一致：{s!r}  JS {js_last} vs PY {py_last}")

    # 光「两边一致」还不够——一致地错更可怕，所以再钉死语义：区间取**结束日**
    assert parse_until("2026.10.05-2026.10.11").isoformat() == "2026-10-11"
    assert parse_when("2026.10.05-2026.10.11").isoformat() == "2026-10-05"


def test_site_has_star_cta():
    """落地页必须带项目地址——它是拉票的主要转化点，改动时别弄丢。"""
    html = SITE.read_text(encoding="utf-8")
    assert "github.com/dengbin21/mcd-profile" in html, "落地页缺少项目地址 CTA"


def test_reports_share_one_design_language():
    """两张新卡片必须共用同一套设计 token。

    它们最初各复制了一份 CSS 并已漂移（区块标题一个 14px 灰、一个 16px 金；
    面板内边距、页脚色、CTA 间距也不同），摆在一起像两个产品。
    锁住同源，防止以后再分叉。
    """
    from src.preheat_report import _CSS as preheat_css                     # noqa: PLC0415
    from src.report.tokens import REPORT_BASE_CSS                          # noqa: PLC0415
    from src.solve_report import _CSS as solve_css                         # noqa: PLC0415

    assert solve_css.startswith(REPORT_BASE_CSS), "战报未使用公共设计 token"
    assert preheat_css.startswith(REPORT_BASE_CSS), "预热卡未使用公共设计 token"
    # 各自的私有部分不能重复定义公共类，否则又会各说各话
    for cls in (".sec{", ".foot{", ".cta{", ".note{", ".wrap{"):
        assert solve_css.replace(REPORT_BASE_CSS, "").find(cls) == -1, \
            f"战报重复定义了公共样式 {cls}"
        assert preheat_css.replace(REPORT_BASE_CSS, "").find(cls) == -1, \
            f"预热卡重复定义了公共样式 {cls}"


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
    print(f"\n{'全部通过' if not fails else f'{fails} 个失败'}")
    sys.exit(1 if fails else 0)
