"""档案渲染包：Markdown 档案 + 可分享卡片（HTML / PNG）。

对外接口与原 ``src/report.py`` 完全一致——
- :func:`render_markdown`  Markdown 档案（终端可读）
- :func:`render_card_html` HTML 分享卡（暗黑潮酷 · 千人千面）
- :func:`render_card_png`  竖版长图 PNG（朋友圈 / 小红书）
- :func:`build_advice`     规则建议（CopyPack 未覆写时的回退）

内部分工：``base``（共享 helper）→ ``markdown`` / ``html`` / ``png`` 三渲染器。
"""
from __future__ import annotations

from .base import build_advice
from .html import render_card_html
from .markdown import render_markdown
from .png import render_card_png

__all__ = ["render_markdown", "render_card_html", "render_card_png", "build_advice"]
