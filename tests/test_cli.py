"""CLI 层回归测试。

补的是此前最大的一块空白：``src/cli.py`` 有 1200+ 行、15 个子命令、
``--copy`` / ``--brief`` 全流程，却**一个用例都没有**——上一轮改 ``_copy()`` 签名
是手跑才发现的坑。这里把「命令还能跑」这件事交给测试。

守四条线：

1. **离线子命令都能跑通**（评委/demo 最常见的就是 ``--offline``）；
2. **需要联网的命令必须明确拒绝**，而不是半路炸栈或假装成功；
3. **命令不得悄悄污染仓库**——产物默认写回 ``examples/`` 的行为要能关掉；
4. **文案包的三道护栏在 CLI 上真的生效**（告警打印 + 渲染级回退）；
5. **第一次用的人不会卡在 403 上**——没 Token 时必须给出可照做的指引，
   且自检报告里不能出现 Token 原文。
"""
from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest                                                             # noqa: E402

from src import cli, mcp_client                                           # noqa: E402
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


def _run_exit(argv: list[str]) -> tuple[int, str]:
    """跑一条 CLI 命令，返回 ``(退出码, 打印内容)``。"""
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf):
        try:
            main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 0
    return code, buf.getvalue()


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
    assert "麦麦战绩" in out
    assert "麦门人格" in out


def test_preheat_hint_uses_date_based_target():
    """archive 的「下一场活动」回流量必须与预热台同口径（按日期取最近未来活动）。

    回归：`_preheat_hint` 曾依赖 stage 字段的 upcoming[0]（插入序），
    与 preheat 的日期分桶可能指向不同活动——两个命令在同一份数据上打架。
    """
    from types import SimpleNamespace

    from src.models import CampaignEvent

    # stage 乱序（future 先出现），真实日期次序才是目标：应指向 10-16 的秋日限定
    campaigns = [
        CampaignEvent(date="2026-10-25", title="周末欢乐桶限时回归", stage="future"),
        CampaignEvent(date="2026-10-09", title="超值9.9元早餐两件套", stage="today"),
        CampaignEvent(date="2026-10-16", title="秋日限定新品上新", stage="future"),
    ]
    a = SimpleNamespace(raw=SimpleNamespace(
        campaigns=campaigns, server_time="2026-10-09 16:48:16"))
    hint = cli._preheat_hint(a)
    assert "秋日限定新品上新" in hint, f"回流量应指向最近的未来活动，实际 {hint}"
    assert "周末欢乐桶" not in hint


def test_preheat_hint_handles_no_future():
    from types import SimpleNamespace

    a = SimpleNamespace(raw=SimpleNamespace(campaigns=[], server_time=""))
    assert cli._preheat_hint(a) == ""


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
# 5. Token 配置（别人要用这个 Skill，第一步就是配它，配错会静默 401）
# ---------------------------------------------------------------------- #
def test_env_token_beats_everything(monkeypatch):
    """环境变量优先级最高：配置文件里写得再真也不能盖过 env。"""
    monkeypatch.setenv("MCD_MCP_TOKEN", "FROM_ENV")
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(cli, "ROOT", Path(d))
        _write_cfg(Path(d) / "mcp-config.local.json", "FROM_FILE")
        assert cli._env_token() == "FROM_ENV"
        assert cli._client(argparse.Namespace(token=None)).token == "FROM_ENV"


def test_local_config_wins_over_example(monkeypatch):
    """`mcp-config.local.json`（已 gitignore）应优先于模板文件。"""
    monkeypatch.delenv("MCD_MCP_TOKEN", raising=False)
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(Path, "home", lambda: Path(d) / "nohome")  # 排除本机真实配置
        monkeypatch.setattr(cli, "ROOT", Path(d))
        _write_cfg(Path(d) / "mcp-config.local.json", "FROM_LOCAL")
        _write_cfg(Path(d) / "mcp-config.example.json", "FROM_EXAMPLE")
        assert cli._token_from_config() == "FROM_LOCAL"


def test_placeholder_is_never_used_as_token(monkeypatch):
    """`Bearer ${MCD_MCP_TOKEN}` 是占位符：没设环境变量时不能把它当 Token 发出去，
    否则会以字面量进 Authorization 头，换来一个看不懂的 401。"""
    monkeypatch.delenv("MCD_MCP_TOKEN", raising=False)
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(Path, "home", lambda: Path(d) / "nohome")
        monkeypatch.setattr(cli, "ROOT", Path(d))
        _write_cfg(Path(d) / "mcp-config.example.json", "${MCD_MCP_TOKEN}")
        assert cli._token_from_config() is None


def _write_cfg(path: Path, token: str) -> None:
    path.write_text(json.dumps({"mcpServers": {"mcd-mcp": {
        "type": "streamablehttp", "url": "https://mcp.mcd.cn",
        "headers": {"Authorization": f"Bearer {token}"}}}}), encoding="utf-8")


# ---------------------------------------------------------------------- #
# 5) 首次使用：没 Token 的体验
# ---------------------------------------------------------------------- #
def test_remote_command_without_token_shows_setup_guide(monkeypatch):
    """全新用户直接 `eat`：不能只抛 403，必须说清去哪申请、填到哪、怎么自检。"""
    monkeypatch.delenv("MCD_MCP_TOKEN", raising=False)
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(Path, "home", lambda: Path(d) / "nohome")
        monkeypatch.setattr(cli, "ROOT", Path(d))
        code, out = _run_exit(["eat"])
    assert code == 2, "没有 Token 时应明确失败，而不是继续执行"
    assert "open.mcd.cn" in out
    assert "export MCD_MCP_TOKEN" in out
    assert "doctor" in out
    assert "403" not in out, "别把原始 HTTP 错误丢给用户"


def test_doctor_without_token_explains_and_is_not_a_failure(monkeypatch):
    """`doctor` 是诊断命令：没 Token 时给出指引，但**不该**以失败退出。"""
    monkeypatch.delenv("MCD_MCP_TOKEN", raising=False)
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(Path, "home", lambda: Path(d) / "nohome")
        monkeypatch.setattr(cli, "ROOT", Path(d))
        code, out = _run_exit(["doctor"])
    assert code == 0
    assert "没找到" in out
    assert "open.mcd.cn" in out


def test_doctor_offline_does_not_nag_about_token(monkeypatch):
    """`--offline doctor` 是离线自检：不该反过来催用户配 Token。"""
    monkeypatch.delenv("MCD_MCP_TOKEN", raising=False)
    out = _run(["--offline", "doctor"])
    assert "已跳过" in out
    assert "还差一步" not in out


def test_doctor_never_prints_the_token_itself(monkeypatch):
    """自检报告会被贴进 issue / 群里——Token 原文绝不能出现在输出中。"""
    monkeypatch.setenv("MCD_MCP_TOKEN", "SUPERSECRETTOKEN12345")
    monkeypatch.setattr(cli.McdMcpClient, "list_tools", lambda self: [])
    out = _run(["doctor"])
    assert "SUPERSECRETTOKEN12345" not in out
    assert "SUPE" in out and "2345" in out      # 只留首尾各 4 位


def test_doctor_reports_missing_tools(monkeypatch):
    """连上了但工具不全，要指名缺哪些——否则会变成「跑一半静默少数据」。"""
    monkeypatch.setenv("MCD_MCP_TOKEN", "SUPERSECRETTOKEN12345")
    monkeypatch.setattr(cli.McdMcpClient, "list_tools",
                        lambda self: [{"name": "order-list"}])
    out = _run(["doctor"])
    assert "缺" in out
    assert "calculate-price" in out


def test_http_401_becomes_actionable_auth_error(monkeypatch):
    """401/403 必须翻译成「去配 Token」，且单独成类（该配凭据，不是该重试）。"""
    import requests

    class _Resp:
        status_code = 401
        headers: dict = {}
        text = "{}"

        def raise_for_status(self):
            raise requests.HTTPError("401 Client Error", response=self)

    monkeypatch.setattr(mcp_client.requests, "post", lambda *a, **k: _Resp())
    with pytest.raises(mcp_client.McpAuthError) as excinfo:
        mcp_client.McdMcpClient(token="x").call_tool("now-time-info")
    assert "open.mcd.cn" in str(excinfo.value)


def test_non_auth_http_error_stays_a_plain_mcp_error(monkeypatch):
    """不能为了「友好」把所有 HTTP 错误都说成凭据问题——500 就是 500。"""
    import requests

    class _Resp:
        status_code = 500
        headers: dict = {}
        text = "{}"

        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error", response=self)

    monkeypatch.setattr(mcp_client.requests, "post", lambda *a, **k: _Resp())
    with pytest.raises(mcp_client.McpError) as excinfo:
        mcp_client.McdMcpClient(token="x").call_tool("now-time-info")
    assert not isinstance(excinfo.value, mcp_client.McpAuthError)
    assert "doctor" not in str(excinfo.value)


# ---------------------------------------------------------------------- #
def _main() -> None:
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            if inspect.signature(fn).parameters:
                continue          # 需要 fixture 的交给 pytest，这里只跑无参的
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
