"""CLI 层回归测试。

补的是此前最大的一块空白：``src/cli.py`` 有 1200+ 行、15 个子命令、
``--copy`` / ``--brief`` 全流程，却**一个用例都没有**——上一轮改 ``_copy()`` 签名
是手跑才发现的坑。这里把「命令还能跑」这件事交给测试。

守四条线：

1. **离线子命令都能跑通**（评委/demo 最常见的就是 ``--offline``）；
2. **需要联网的命令必须明确拒绝**，而不是半路炸栈或假装成功；
3. **命令不得悄悄污染仓库**——产物默认写回 ``examples/`` 的行为要能关掉；
4. **文案包的三道护栏在 CLI 上真的生效**（告警打印 + 渲染级回退）。
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cli import main                                                  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 离线可跑、且不写仓库的子命令（写产物的在各自用例里传临时路径）
_OFFLINE_READONLY = ["orders", "savings", "account", "campaign", "store", "tools"]
# 这些命令必须联网才有意义，离线时应**明确拒绝**而不是硬跑
_NEEDS_NETWORK = ["stores", "menu", "eat"]


def _run(argv: list[str]) -> str:
    """跑一条 CLI 命令，返回它打印的全部内容。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(argv)
    return buf.getvalue()


def _tmpdir():
    return tempfile.TemporaryDirectory()


# ---------------------------------------------------------------------- #
# 1) 离线子命令
# ---------------------------------------------------------------------- #
def test_offline_readonly_commands_all_run():
    for cmd in _OFFLINE_READONLY:
        out = _run(["--offline", cmd])
        assert out.strip(), f"`{cmd}` 没有任何输出"
        assert "Traceback" not in out


def test_solve_offline_smoke():
    with _tmpdir() as d:
        out = _run(["--offline", "solve", "--items", "9900010001", "--top", "2",
                    "--html", str(Path(d) / "solve.html")])
    assert "McSolve" in out
    assert "最优解" in out
    assert "实付" in out


def test_preheat_offline_smoke():
    with _tmpdir() as d:
        out = _run(["--offline", "preheat", "--html", str(Path(d) / "preheat.html")])
    assert "McPreheat" in out
    assert "备战度" in out


def test_archive_offline_smoke():
    out = _run(["--offline", "archive"])
    assert "麦麦档案" in out
    assert "麦门人格" in out


# ---------------------------------------------------------------------- #
# 2) 需要联网的命令必须明确拒绝
# ---------------------------------------------------------------------- #
def test_network_only_commands_refuse_offline():
    for cmd in _NEEDS_NETWORK:
        out = _run(["--offline", cmd])
        assert "联网" in out or "Token" in out, f"`{cmd}` 离线时没有给出明确提示：{out[:80]}"


def test_solve_requires_items():
    try:
        _run(["--offline", "solve"])
    except SystemExit as exc:
        assert exc.code != 0          # argparse 应报错退出，而不是静默跑出一个空解
    else:
        raise AssertionError("solve 缺少 --items 时应当报错退出")


# ---------------------------------------------------------------------- #
# 3) 不得悄悄污染仓库
# ---------------------------------------------------------------------- #
def test_card_without_png_does_not_touch_repo():
    """曾经：不给 --png 就默认写回 examples/profile_card.png，跑一次覆盖一次仓库示例。"""
    with _tmpdir() as d:
        out = _run(["--offline", "card", "--html", str(Path(d) / "card.html")])
    assert "卡片图已生成" not in out
    assert "跳过长图" in out


def test_demo_out_dir_redirects_artifacts():
    with _tmpdir() as d:
        _run(["--offline", "demo", "--out-dir", d])
        produced = sorted(p.name for p in Path(d).iterdir())
    assert "demo_profile.md" in produced
    assert "profile_card.html" in produced


def test_solve_and_preheat_html_flags_are_respected():
    """写产物的命令要能指哪写哪，否则测试一跑就脏了仓库。"""
    with _tmpdir() as d:
        p = Path(d) / "s.html"
        _run(["--offline", "solve", "--items", "9900010001", "--top", "1", "--html", str(p)])
        assert p.exists() and p.stat().st_size > 0
        q = Path(d) / "p.html"
        _run(["--offline", "preheat", "--html", str(q)])
        assert q.exists() and q.stat().st_size > 0


# ---------------------------------------------------------------------- #
# 4) 文案包护栏（CLI 层）
# ---------------------------------------------------------------------- #
def test_brief_for_every_scene_exports_facts():
    for scene in ("archive", "solve", "preheat"):
        with _tmpdir() as d:
            out_path = Path(d) / f"brief_{scene}.json"
            out = _run(["--offline", "brief", "--for", scene, "--out", str(out_path)])
            data = json.loads(out_path.read_text(encoding="utf-8"))
        assert "facts" in data and data["facts"], f"{scene} 的 brief 没有 facts"
        assert "text_map" in data and data["text_map"], f"{scene} 的 brief 没有 text_map"
        assert "导出" in out or "素材" in out


def test_bad_copy_pack_is_reported_and_falls_back():
    """模型写错键 / 丢占位符 / 编数字，三件事都要**看得见**，且编的数字不能上卡片。"""
    with _tmpdir() as d:
        pack = Path(d) / "bad.json"
        pack.write_text(json.dumps({
            "labels": {
                "sv.sec_solution": "闭眼点 ¥18.5 那套",      # 编数字 → 应回退
                "sv.vs_save": "白省一笔",                     # 丢 {saved} → 应回退
                "sv.hero_title": "x",                        # 键不存在 → 应告警
            },
            "solve": {"grad_word": "x"},                     # 字段名拼错 → 应告警
        }, ensure_ascii=False), encoding="utf-8")
        out = _run(["--offline", "solve", "--items", "9900010001", "--top", "1",
                    "--html", str(Path(d) / "s.html"), "--copy", str(pack)])
    assert "⚠️" in out                       # 必须有告警，不能静默放行
    assert "sv.hero_title" in out            # 未知键
    assert "solve.grad_word" in out          # 未知字段
    # 编的数字最多出现在告警里，**绝不能出现在渲染出来的正文里**
    assert "## 闭眼点 ¥18.5 那套" not in out


def test_good_copy_pack_applies():
    """护栏不能误伤：正常的改写必须真的生效。"""
    with _tmpdir() as d:
        pack = Path(d) / "good.json"
        pack.write_text(json.dumps({
            "labels": {"sv.md_title": "这一单怎么点最划算",
                       "sv.sec_solution": "照着点，别犹豫"},
            "solve": {"grade_word": {"S": "神之一单", "A": "这单稳赚",
                                     "B": "还行", "C": "忍痛"}},
        }, ensure_ascii=False), encoding="utf-8")
        # --top 给足候选，离线样例下评级为 A（只验 1 个候选时是 baseline，评级 C）
        out = _run(["--offline", "solve", "--items", "9900010001", "--top", "3",
                    "--html", str(Path(d) / "s.html"), "--copy", str(pack)])
    assert "✓ 校验通过" in out
    assert "这一单怎么点最划算" in out
    assert "照着点，别犹豫" in out
    assert "这单稳赚" in out


def test_tools_offline_lists_the_whole_plan():
    """离线时也要能自证「会调哪些官方工具」——这是卖点，不能只剩一行空话。"""
    out = _run(["--offline", "tools"])
    assert "calculate-price" in out
    assert "campaign-calendar" in out
    assert "20" in out


# ---------------------------------------------------------------------- #
def _main() -> None:
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✓ {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  ✗ {name}: {exc}")
            except Exception as exc:                                       # noqa: BLE001
                fails += 1
                print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
    print(f"\n{'FAILED' if fails else 'ALL PASSED'}（{fails} failed）")


if __name__ == "__main__":
    _main()
