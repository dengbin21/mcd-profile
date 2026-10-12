"""图片工具：商品缩略图下载 / 转 data-uri（HTML 自包含）/ 读取为数组（PNG 嵌入）。

设计底线：**全程优雅降级**——无网络、下载失败、缺依赖时一律返回空，
让上层渲染自动退回纯文字，绝不让「配图」拖垮主流程。
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

# 默认缓存目录：.cache/menu_img/（已进 .gitignore，可安全写入）
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "menu_img"

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _ext_of(url: str) -> str:
    path = url.lower().split("?", 1)[0]
    for e in _MIME:
        if path.endswith(e):
            return e
    return ".png"


def download(url: str, dest_dir: str | Path | None = None, timeout: int = 12) -> str | None:
    """下载图片到本地缓存，返回本地路径；失败返回 None。已存在则直接复用。"""
    if not url or not url.lower().startswith(("http://", "https://")):
        return None
    dest_dir = Path(dest_dir) if dest_dir else CACHE_DIR
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    dest = dest_dir / (hashlib.md5(url.encode("utf-8")).hexdigest()[:16] + _ext_of(url))
    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)
    try:
        import requests

        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return str(dest)
    except Exception:  # noqa: BLE001 —— 网络/磁盘任意失败都降级
        return None


def download_many(urls: dict[str, str], dest_dir: str | Path | None = None) -> dict[str, str]:
    """批量下载：{key: url} → {key: 本地路径}（失败的键不出现）。"""
    out: dict[str, str] = {}
    for key, url in urls.items():
        p = download(url, dest_dir=dest_dir)
        if p:
            out[key] = p
    return out


def to_data_uri(src: str) -> str:
    """本地文件 → ``data:...;base64``；http(s) → 原样返回；非法/缺失 → 空串。

    本地文件转 data-uri 后，HTML 卡片**单文件自包含**，脱网也能看到商品图。
    """
    if not src:
        return ""
    if src.lower().startswith(("http://", "https://")):
        return src
    p = Path(src)
    if not p.exists():
        return ""
    mime = _MIME.get(p.suffix.lower(), "image/png")
    try:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:{mime};base64,{b64}"


def load_array(src: str):
    """读取本地图片为 numpy 数组（供 matplotlib imshow）；失败返回 None。"""
    if not src:
        return None
    p = Path(src)
    if not p.exists():
        return None
    try:
        import matplotlib.image as mpimg

        return mpimg.imread(str(p))
    except Exception:  # noqa: BLE001
        try:
            import numpy as np
            from PIL import Image

            return np.asarray(Image.open(p).convert("RGB"))
        except Exception:  # noqa: BLE001
            return None
