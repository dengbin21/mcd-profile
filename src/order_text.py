"""点餐话术解析（order_text）：把「人说的话」变成「机器可点的单」。

这是点餐闭环里**最容易被人工搞错**的一环（见 2026-10 编码错位事故：
手抄编码 `9900015008` 被官方接口认成另一款商品）。本模块负责：

1. :func:`parse_items` —— 解析点餐清单，兼容 ``code:qty``、商品名、
   菜单页一键话术（``商品名×2``）、以及整句自然语言（含「我要点：」
   开场白与「（门店，取餐方式）」括注）；
2. :func:`resolve_cart` —— 把名称换成官方编码：**精确 → 子串 → 相似度**
   三级匹配；歧义 / 无唯一匹配时抛结构化异常（带候选列表），
   **绝不瞎猜**——由上层 CLI 呈现候选、让用户拍板。

全部为纯函数、零副作用（不打印、不联网），便于离线单测。
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from .models import CartItem, MenuItem

# 数量标记：菜单页话术用「×2」，也有人写「x2」「*2」「＊2」
_QTY_MARKS = ("×", "＊", "*", "x", "X")

# 开场白（整句话术直接粘贴时剥离）
_LEADINS = (
    "我要点：", "我要点:", "我要吃：", "我要吃:", "帮我点：", "帮我点:",
    "我要点", "我要吃", "帮我点", "请给我", "来个",
)

# 相似度自动命中的门槛：最高分足够高，且明显高于第二名
_FUZZY_MIN = 0.75
_FUZZY_GAP = 0.05


# ---------------------------------------------------------------------- #
# ① 清单解析
# ---------------------------------------------------------------------- #
def _strip_paren_note(t: str) -> str:
    """去掉「（门店，取餐方式）」之类的括注——括号成对时整体剥离。"""
    for lp, rp in (("（", "）"), ("(", ")")):
        while lp in t and rp in t:
            t = t[:t.index(lp)] + " " + t[t.index(rp) + 1:]
    return t


def _merge_qty_marks(flat: list[str]) -> list[str]:
    """合并被空格拆散的数量标记：``["麦辣鸡腿堡", "x", "2"]`` → ``["麦辣鸡腿堡x2"]``。"""
    merged: list[str] = []
    pending = ""
    for tok in (t.strip() for t in flat):
        if not tok:
            continue
        if tok in _QTY_MARKS:                       # 单独的标记，等下一个数字
            pending = tok
            continue
        if pending and tok.isdigit():               # 「x」+「2」 → 并到前一个词
            if merged:
                merged[-1] += pending + tok
            pending = ""
            continue
        if pending:                                  # 标记后面不是数字：原样保留，避免吞词
            if merged:
                merged[-1] += pending
            pending = ""
        if len(tok) > 1 and tok[0] in _QTY_MARKS and tok[1:].isdigit():
            if merged:                              # 已是「x2」→ 并到前一个词
                merged[-1] += tok
                continue
        merged.append(tok)
    return merged


def _split_qty(spec: str) -> tuple[str, int]:
    """从单个词条里拆出 (key, qty)：兼容 ``:`` / ``：`` / ``×`` 数量标记。"""
    key, sep, qty = spec.partition(":")
    if not sep:
        key, sep, qty = spec.partition("：")
    if not sep:
        for mark in _QTY_MARKS:
            idx = spec.rfind(mark)
            if idx > 0 and spec[idx + 1:].strip().isdigit():
                key, sep, qty = spec[:idx], ":", spec[idx + 1:]
                break
    key = key.strip()
    try:
        n = int(qty) if qty.strip() else 1
    except ValueError:
        n = 1
    return key, max(1, n)


def parse_items(specs: list[str]) -> list[tuple[str, int]]:
    """解析点餐清单，返回 ``(编码或名称, 数量)`` 列表。

    兼容写法：
    - 分隔符：空格 / ``,`` / ``，`` / ``、`` / ``;`` / ``；``
    - 数量：``:2`` / ``：2`` / ``×2`` / ``x2`` / ``*2``（含带空格的 ``x 2``）
    - 整句话术：``我要点：麦辣鸡腿汉堡×2、圆筒冰淇淋×1（门店，到店取餐）``
    """
    flat: list[str] = []
    for s in specs or []:
        t = _strip_paren_note(str(s))
        for pre in _LEADINS:
            t = t.replace(pre, " ")
        t = t.replace("、", ",").replace("，", ",").replace("；", ",")
        for part in t.replace(";", ",").replace("\t", " ").split():
            flat.extend(part.split(","))

    pairs: list[tuple[str, int]] = []
    for spec in _merge_qty_marks(flat):
        key, n = _split_qty(spec)
        if key:
            pairs.append((key, n))
    return pairs


# ---------------------------------------------------------------------- #
# ② 名称 → 编码（三级匹配，绝不瞎猜）
# ---------------------------------------------------------------------- #
@dataclass
class _ResolveFailure(Exception):
    """名称解析失败（歧义 / 无匹配）。携带结构化候选，供上层展示。"""

    key: str = ""
    candidates: list[MenuItem] = field(default_factory=list)          # 歧义候选
    suggestions: list[tuple[float, MenuItem]] = field(default_factory=list)  # 无匹配建议


class AmbiguousItem(_ResolveFailure):
    """「圆筒」这类词匹配到多款——必须让用户选，不许猜。"""


class UnknownItem(_ResolveFailure):
    """没有足够像的唯一匹配——列出最像的几款供用户参考。"""


def resolve_one(key: str, menu_items: dict[str, MenuItem]) -> MenuItem:
    """单个「编码或名称」→ 菜单商品。失败抛 :class:`AmbiguousItem` / :class:`UnknownItem`。"""
    hits = [it for it in menu_items.values() if it.name == key]
    if not hits:
        hits = [it for it in menu_items.values() if key in (it.name or "")]
    if not hits:
        scored = sorted(
            ((difflib.SequenceMatcher(None, key, it.name or "").ratio(), it)
             for it in menu_items.values() if it.name),
            key=lambda x: -x[0],
        )
        top = scored[0]
        if top[0] >= _FUZZY_MIN and (len(scored) == 1 or top[0] - scored[1][0] >= _FUZZY_GAP):
            hits = [top[1]]
        else:
            raise UnknownItem(key=key, suggestions=scored[:5])
    if len(hits) > 1:
        raise AmbiguousItem(key=key, candidates=hits)
    return hits[0]


@dataclass
class ResolvedCart:
    """解析成功的购物车 + 人类可读的对照说明（key → 官方名（编码））。"""

    cart: list[CartItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def resolve_cart(pairs: list[tuple[str, int]], menu) -> ResolvedCart:
    """把 ``(编码或名称, 数量)`` 全部换成 :class:`CartItem`。

    ``menu`` 为 :class:`src.ordering.Menu`（用其 ``items`` 字典）。
    失败即抛异常、不返回半成品购物车——保证「要么全对，要么重来」。
    """
    rc = ResolvedCart()
    for key, qty in pairs:
        if key.isdigit():                            # 编码直传，不做名称解析
            rc.cart.append(CartItem(product_code=key, quantity=qty))
            continue
        it = resolve_one(key, menu.items)
        rc.notes.append(f"「{key}」→ {it.name}（{it.code}）")
        rc.cart.append(CartItem(product_code=it.code, name=it.name, price=it.price,
                                image=it.image, quantity=qty))
    return rc
