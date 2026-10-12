"""零 Token 离线演示：一键跑出三个玩法的产物。

用法::

    python scripts/demo.py

产物（写入仓库 ``docs/``，可提交作演示素材）:

- ``docs/demo-card.png``     麦门人格卡（竖版长图，README 首页那张）
- ``docs/demo-solve.md``     McSolve 最优解战报（离线估算口径已声明）
- ``docs/demo-preheat.md``   McPreheat 预热卡（券到期 × 活动冲突）

全程只读、无网络、不需要 Token，也不用配 ``mcd-mcp``。
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.archive import build_archive                          # noqa: E402
from src.preheat import build_preheat                          # noqa: E402
from src.preheat_report import render_preheat_markdown         # noqa: E402
from src.report.png import render_card_png                     # noqa: E402
from src.solver import (                                       # noqa: E402
    eat_plan, load_sample_menu, make_offline_pricer, parse_coupons,
    sample_coupon_titles, solve,
)
from src.solve_report import render_solve_markdown             # noqa: E402

# 样例里的「我的常点」（板烧鸡腿堡），McSolve 的必选件
MUST_CODE = "9900010001"


def main() -> None:
    docs = REPO / "docs"
    docs.mkdir(exist_ok=True)

    # ① 麦门人格卡（archive）—— README 首页那张
    a = build_archive(None, use_remote=False)
    card = docs / "demo-card.png"
    ok = render_card_png(a, card)
    print(f"[archive] 麦门人格卡 → docs/{card.name}  "
          f"人格={a.persona.label}  渲染={'OK' if ok else '降级(未装 matplotlib)'}")

    # ② McSolve 最优解战报
    menu, _ = load_sample_menu()
    rules = parse_coupons(sample_coupon_titles())
    sol = solve([MUST_CODE], menu, rules, make_offline_pricer(menu, rules))
    solve_md = docs / "demo-solve.md"
    solve_md.write_text(render_solve_markdown(sol, offline=True), encoding="utf-8")
    plan = eat_plan(sol, "1990262")
    print(f"[solve]  McSolve 战报 → docs/{solve_md.name}  "
          f"评级={sol.grade}  省 ¥{sol.saved:.0f}  实付 ¥{sol.paid:.2f}")
    print(f"        下一步（宿主 agent 可执行）：{plan}")

    # ③ McPreheat 预热卡
    pre = build_preheat(a.raw.campaigns, a.raw.coupons)
    pre_md = docs / "demo-preheat.md"
    pre_md.write_text(render_preheat_markdown(pre), encoding="utf-8")
    print(f"[preheat] 预热卡 → docs/{pre_md.name}  "
          f"备战度={pre.grade}  等不到活动的券 {len(pre.missing)} 张")

    print("\n完成。三样产物均为随附脱敏样例生成，可直接进 README / 提交作演示素材。")


if __name__ == "__main__":
    main()
