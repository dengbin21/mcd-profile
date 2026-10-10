"""营养数据：为「健康画像」把订单里的商品名映射到官方营养值。

数据源优先 mcd-mcp 的 ``list-nutrition-foods``，失败回退本地快照。
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "nutrition_snapshot.json"

# 每日参考值（成年人轻体力活动，用于“折合占每日比例”）
DAILY_REFERENCE = {"energyKcal": 2000, "protein": 60, "fat": 60, "carbohydrate": 300, "sodium": 2000}


@dataclass
class Food:
    productName: str
    energyKcal: float
    protein: float
    fat: float
    carbohydrate: float
    sodium: float
    calcium: float = 0.0

    def to_dict(self) -> dict:
        return {
            "productName": self.productName,
            "energyKcal": self.energyKcal,
            "protein": self.protein,
            "fat": self.fat,
            "carbohydrate": self.carbohydrate,
            "sodium": self.sodium,
            "calcium": self.calcium,
        }


def _norm(name: str) -> str:
    """归一化：去空白/括号/引号，模糊匹配用。"""
    return re.sub(r"[\s（）()【】\[\]\"“”·•®™\-—]+", "", name).lower()


# 规格/品牌前后缀（匹配时弱化）
_NOISE = ("大杯", "中杯", "小杯", "迷你", "盒装", "麦咖啡", "1块", "2块", "3块", "4块", "5块",
          "（1块）", "（2块）", "（3块）", "（4块）", "（5块）")


def _core(name: str) -> str:
    n = _norm(name)
    for w in _NOISE:
        n = n.replace(_norm(w), "")
    return n


def to_food(raw: dict) -> Food:
    return Food(
        productName=raw["productName"],
        energyKcal=float(raw.get("energyKcal") or 0),
        protein=float(raw.get("protein") or 0),
        fat=float(raw.get("fat") or 0),
        carbohydrate=float(raw.get("carbohydrate") or 0),
        sodium=float(raw.get("sodium") or 0),
        calcium=float(raw.get("calcium") or 0),
    )


def parse_nutrition_text(text: str) -> list[dict]:
    """解析服务端返回的营养文本（形如 ``[160]{productName,...}:\\n  名字,...``）。"""
    idx = text.find("[")
    body = text[idx:] if idx >= 0 else text
    rows: list[dict] = []
    for line in body.splitlines()[1:]:
        parts = [p.strip() for p in line.strip().split(",")]
        if len(parts) != 9:
            continue
        name = parts[0]
        if not name:
            continue

        def num(x: str) -> float:
            try:
                return float(x)
            except (TypeError, ValueError):
                return 0.0

        rows.append({
            "productName": name, "energyKj": num(parts[2]), "energyKcal": num(parts[3]),
            "protein": num(parts[4]), "fat": num(parts[5]),
            "carbohydrate": num(parts[6]), "sodium": num(parts[7]), "calcium": num(parts[8]),
        })
    if not rows:
        raise ValueError("营养文本解析为空")
    return rows


def load_snapshot() -> list[Food]:
    with DATA_FILE.open(encoding="utf-8") as fh:
        return [to_food(x) for x in json.load(fh)]


def fetch_foods(client=None, use_remote: bool = True) -> tuple[list[Food], str]:
    """获取营养数据，返回 (foods, source)。"""
    if use_remote and client is not None:
        try:
            result = client.call_tool("list-nutrition-foods")
            if isinstance(result, str):
                return [to_food(x) for x in parse_nutrition_text(result)], "remote"
            if isinstance(result, list) and result and isinstance(result[0], dict):
                return [to_food(x) for x in result], "remote"
        except Exception:  # noqa: BLE001 —— 远端异常回退本地快照
            pass
    return load_snapshot(), "snapshot"


# ---------------------------------------------------------------------- #
# 订单商品名 → 营养库匹配
# ---------------------------------------------------------------------- #
class NutritionIndex:
    """把营养库建成可按名字检索的索引，供订单商品映射。"""

    def __init__(self, foods: list[Food]):
        self.foods = foods
        self._by_name = {_norm(f.productName): f for f in foods}
        self._by_core = {}
        for f in foods:
            self._by_core.setdefault(_core(f.productName), f)

    def match(self, name: str, threshold: float = 0.82) -> Food | None:
        """三级匹配：归一化精确 → 核心名精确 → 相似度。"""
        if not name:
            return None
        n = _norm(name)
        if n in self._by_name:
            return self._by_name[n]
        c = _core(name)
        if c in self._by_core:
            return self._by_core[c]
        # 包含关系
        cands = [f for f in self.foods if c and (_core(f.productName) in c or c in _core(f.productName))]
        if cands:
            cands.sort(key=lambda f: abs(len(_core(f.productName)) - len(c)))
            return cands[0]
        best, best_score = None, 0.0
        for f in self.foods:
            score = difflib.SequenceMatcher(None, c, _core(f.productName)).ratio()
            if score > best_score:
                best_score, best = score, f
        return best if best_score >= threshold else None

    def nutrition_for(self, name: str) -> Food | None:
        return self.match(name)
