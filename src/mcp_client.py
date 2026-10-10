"""mcd-mcp 极简客户端（MCP Streamable HTTP / JSON-RPC 2.0）。

只依赖 requests，封装麦当劳官方 MCP Server 的工具调用，
供「麦麦档案」的数据采集与（可选）下单闭环复用。
"""
from __future__ import annotations

import itertools
import json
import os
import threading
from typing import Any

import requests

DEFAULT_URL = "https://mcp.mcd.cn"


class McpError(RuntimeError):
    """MCP 调用异常（网络、协议或业务错误）。"""


class McdMcpClient:
    """与 mcd-mcp 服务通信的最小客户端。

    用法::

        client = McdMcpClient(token="xxx")
        data = client.call_tool("order-list")            # 返回 structuredContent.data
    """

    def __init__(self, url: str = DEFAULT_URL, token: str | None = None, timeout: int = 30):
        self.url = url
        self.token = token or os.environ.get("MCD_MCP_TOKEN")
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
        except requests.RequestException as exc:  # 网络层错误
            raise McpError(f"调用 {name} 失败：{exc}") from exc

        message = self._decode(resp)
        if "error" in message:
            raise McpError(f"{name} 协议错误：{message['error']}")
        return self._extract(message.get("result", {}))

    def list_tools(self) -> list[dict[str, Any]]:
        """返回服务端声明的工具清单。"""
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": "tools/list", "params": {}}
        resp = requests.post(self.url, json=payload, headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        return self._decode(resp).get("result", {}).get("tools", [])

    # ------------------------------------------------------------------ #
    # 解析
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode(resp: requests.Response) -> dict[str, Any]:
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
