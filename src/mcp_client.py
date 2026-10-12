"""mcd-mcp 极简客户端（MCP Streamable HTTP / JSON-RPC 2.0）。

**只在真正联网时才需要 `requests`**：本模块对 requests 是**惰性导入**，
离线算法（券解析 / 枚举 / 日期 / 画像 / 人格）与 Markdown / HTML 产物
完全不依赖任何第三方包。

Token 的取用顺序与「只配 MCP」一致：显式传参 → 环境变量 ``MCD_MCP_TOKEN``
→ **客户端的 MCP 配置文件**（见 :func:`token_from_mcp_config`），
因此宿主 agent 复用 ``src/`` 时不需要再让用户单独导出环境变量。
"""
from __future__ import annotations

import itertools
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

DEFAULT_URL = "https://mcp.mcd.cn"

# 常见 MCP 客户端的配置文件位置（按优先级排列）
CONFIG_CANDIDATES: tuple[str, ...] = (
    "~/.workbuddy/mcp.json",
    "~/.workbuddy/.mcp.json",
    "~/.codebuddy/.mcp.json",
    "~/.codebuddy/mcp.json",
    "~/.cursor/mcp.json",
    ".mcp.json",
)

# ${VAR} / ${VAR:-default} 形式的占位符
_PLACEHOLDER_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}$")


def _expand(value: Any) -> str:
    """展开配置里的 ``${ENV}`` 占位符；**展开为空时返回空串**（不把字面量当 Token）。

    历史上踩过这个坑：配置里写 ``${MCD_MCP_TOKEN}`` 而环境变量没设，
    把字面量原样当 Token 发出去就是 401——宁可跳过这条配置继续找下一个。
    """
    if not isinstance(value, str):
        return ""
    s = value.strip()
    m = _PLACEHOLDER_RE.match(s)
    if m:
        return (os.environ.get(m.group(1)) or "").strip()
    return s


def token_from_mcp_config() -> tuple[str, str]:
    """从客户端的 MCP 配置里找 mcd-mcp 的 Token，返回 ``(token, 配置文件路径)``。

    只认「名字或 url 含 mcd」的那条服务；取不到返回 ``("", "")``。
    配置内容只在本进程内使用，**不落盘、不进产物、不打印**。
    """
    for raw in CONFIG_CANDIDATES:
        path = Path(raw).expanduser()
        if not path.is_file():
            continue
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        servers = cfg.get("mcpServers") if isinstance(cfg, dict) else None
        if not isinstance(servers, dict):
            continue
        for name, conf in servers.items():
            if not isinstance(conf, dict):
                continue
            url = str(conf.get("url") or "")
            if "mcd" not in str(name).lower() and "mcd" not in url.lower():
                continue
            headers = conf.get("headers") or {}
            tok = _expand(headers.get("Authorization") or "")
            if tok.lower().startswith("bearer "):
                tok = tok[7:].strip()
            if tok:
                return tok, str(path)
    return "", ""


def resolve_token(explicit: str | None = None) -> tuple[str, str]:
    """按「显式传参 → 环境变量 → 客户端配置」取 Token，返回 ``(token, 来源)``。

    来源取值：``"explicit"`` / ``"env:MCD_MCP_TOKEN"`` / 配置文件路径 / ``""``（没找到）。
    """
    if explicit:
        return explicit, "explicit"
    env = (os.environ.get("MCD_MCP_TOKEN") or "").strip()
    if env:
        return env, "env:MCD_MCP_TOKEN"
    return token_from_mcp_config()


def _require_requests():
    """惰性导入 requests——离线算法路径不需要它。"""
    try:
        import requests  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise McpError(
            "联网调用 mcd-mcp 需要 requests：`pip install requests`"
            "（离线算法与 Markdown/HTML 产物不需要它）"
        ) from exc
    return requests


class McpError(RuntimeError):
    """MCP 调用异常（网络、协议或业务错误）。"""


class McpAuthError(McpError):
    """凭据问题：没配 Token / Token 无效或已过期。

    单独成类是因为它**不是**「服务坏了」，而是「还没证明你是谁」——
    该给用户的动作是去配 Token，不是重试。实测没有 Token 时 mcd-mcp 只回一个
    403，如果不单独识别，用户看到的就是一串看不懂的 HTTP 错误。
    """


def _explain(exc: Exception, name: str) -> McpError:
    """把 HTTP 状态码翻译成「下一步该做什么」。

    401/403 是新手的第一次遭遇（Token 没配或过期），只回状态码等于什么都没说；
    其余保持原样抛出——不为「友好」掩盖真实问题。
    """
    status = getattr(exc.response, "status_code", 0) or 0
    if status in (401, 403):
        return McpAuthError(
            f"mcd-mcp 拒绝了这次调用（HTTP {status}）：Authorization 头缺失、无效或已过期。\n"
            "  · 申请 / 续期 Token：https://open.mcd.cn/mcp\n"
            "  · 配好后自检：重启客户端，确认 mcd-mcp 已连接（工具列表里有 calculate-price）"
        )
    if status == 429:
        return McpError(
            f"调用 {name} 失败：HTTP 429 触发限流。可调低验价并发后重试。"
        )
    return McpError(f"调用 {name} 失败：{exc}")


class McdMcpClient:
    """与 mcd-mcp 服务通信的最小客户端。

    用法::

        client = McdMcpClient(token="xxx")
        data = client.call_tool("order-list")            # 返回 structuredContent.data
    """

    def __init__(self, url: str = DEFAULT_URL, token: str | None = None, timeout: int = 30):
        self.url = url
        token, source = resolve_token(token)
        self.token = token or None
        # Token 来源只用于自检提示（如 doctor），**不回显 Token 本身**
        self.token_source = source
        self.timeout = timeout
        self._ids = itertools.count(1)
        # 调用日志：每次 call_tool 记录 {name, ok, error}，供「工具覆盖清单」使用
        self.calls: list[dict[str, Any]] = []
        # McSolve 会并发验价（多个线程同时 call_tool），id 生成与调用日志必须加锁
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # 底层协议
    # ------------------------------------------------------------------ #
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用一个 MCP 工具，返回 ``structuredContent.data``（无则回退解析文本）。"""
        try:
            data = self._call_tool_once(name, arguments)
        except Exception as exc:  # noqa: BLE001 —— 记录失败后继续抛出
            with self._lock:
                self.calls.append({"name": name, "ok": False, "error": str(exc)})
            raise
        with self._lock:
            self.calls.append({"name": name, "ok": True, "error": ""})
        return data

    def _next_id(self) -> int:
        with self._lock:
            return next(self._ids)

    def _call_tool_once(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        requests = _require_requests()
        if not self.token:
            # 拿不到 Token 就别发请求——mcd-mcp 只会回一个看不懂的 403
            raise McpAuthError(
                "没有可用的 Token（已查：显式传参 / 环境变量 MCD_MCP_TOKEN / 客户端 MCP 配置）。\n"
                "  · 申请 Token：https://open.mcd.cn/mcp\n"
                "  · 或把它配进客户端的 mcp.json（`mcd-mcp` → headers.Authorization）"
            )
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
        try:
            resp = requests.post(
                self.url, json=payload, headers=self._headers(), timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:  # 4xx / 5xx：状态码决定该给什么建议
            raise _explain(exc, name) from exc
        except requests.RequestException as exc:  # 网络层错误
            raise McpError(f"调用 {name} 失败：{exc}") from exc

        message = self._decode(resp)
        if "error" in message:
            raise McpError(f"{name} 协议错误：{message['error']}")
        return self._extract(message.get("result", {}))

    # ------------------------------------------------------------------ #
    # 解析
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode(resp: Any) -> dict[str, Any]:
        """兼容标准 JSON 与 SSE（text/event-stream）两种响应。"""
        ctype = resp.headers.get("Content-Type", "")
        text = resp.text or ""
        if "text/event-stream" in ctype or text.lstrip().startswith("event:"):
            for line in reversed(text.splitlines()):
                line = line.strip()
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    try:
                        return json.loads(payload)
                    except json.JSONDecodeError:
                        continue
            raise McpError("无法解析 SSE 响应")
        return json.loads(text)

    @staticmethod
    def _extract(result: dict[str, Any]) -> Any:
        """优先取 structuredContent.data，其次解析 content[].text 中的内嵌 JSON。"""
        sc = result.get("structuredContent")
        if isinstance(sc, dict) and "data" in sc:
            if sc.get("success") is False:
                raise McpError(sc.get("message") or "业务失败")
            return sc.get("data")

        for block in result.get("content", []):
            text = block.get("text", "")
            idx = text.find('{"success"')
            if idx >= 0:
                try:
                    raw = json.loads(text[idx:])
                except json.JSONDecodeError:
                    continue
                if raw.get("success") is False:
                    raise McpError(raw.get("message") or "业务失败")
                return raw.get("data")
        raise McpError("响应中未找到可用数据")
