"""麦麦最优解 · McSolve：把 ``calculate-price`` 当「价格预言机」用的组合求解器。

核心认知
--------
``calculate-price`` 是**只读、免费、不产生订单**的接口——可以在不下单、
不花钱的前提下，知道任意商品组合的**真实实付价**。

全场都把它当「下单前的最后一步」，只调一次、用完即弃。
本模块把它当**模拟器**反复调用：本地穷举候选 → 剪枝排序 → 对 Top N 个候选
逐一调官方接口验价 → 取官方认证的最低价。

调用量控制（关键可行性点）
--------------------------
100+ 款商品的组合空间是天文数字，不能逐个验价。因此分两段：

1. **本地枚举（免费）**：按券规则与预算剪枝，枚举出数千种候选，用菜单价粗估排序；
2. **官方验价（有成本）**：只对 Top N（默认 30）个候选调 ``calculate-price``。

本地粗估只用于**排序**，最终价格一律以官方验价为准——绝不拿估算当结果。
"""
from __future__ import annotations

import itertools
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .models import CartItem, MenuItem, OrderQuote

# 样例数据目录（离线可复现：菜单 / 券面文案，供 McSolve 演示与测试）
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_sample_menu() -> tuple[dict[str, MenuItem], "Menu"]:
    """离线样例菜单：``data/menu_sample.json``（脱敏，结构与官方 query-meals 一致）。

    公开给测试与离线演示复现 McSolve；联网时请改用真实 ``query-meals``。
    """
    from .ordering import Menu

    data = json.loads((_DATA_DIR / "menu_sample.json").read_text(encoding="utf-8"))
    items: dict[str, MenuItem] = {}
    for code, v in (data.get("meals") or {}).items():
        if not isinstance(v, dict):
            continue
        items[str(code)] = MenuItem(
            code=str(code), name=v.get("name", "") or "",
            price=float(v.get("currentPrice") or 0),
            original_price=float(v.get("originalPrice") or 0),
        )
    cats: list[tuple[str, list[str]]] = []
    for cat in data.get("categories") or []:
        cname = cat.get("name", "商品")
        codes: list[str] = []
        for m in cat.get("meals") or []:
            code = str(m.get("code", ""))
            if not code:
                continue
            codes.append(code)
            it = items.get(code)
            if it is not None:
                it.category = cname
                it.tags = list(m.get("tags") or [])
        if codes:
            cats.append((cname, codes))
    freq = str((data.get("frequent") or {}).get("code", "") or "")
    if freq in items:
        items[freq].tags = sorted(set(items[freq].tags) | {"我的常点"})
    return items, Menu(categories=cats, frequent_code=freq, items=items)


def sample_coupon_titles() -> list[str]:
    """离线样例券面文案：取自 archive_sample / scene_sample 的脱敏数据。"""
    titles: list[str] = []
    for name in ("archive_sample.json", "scene_sample.json"):
        try:
            d = json.loads((_DATA_DIR / name).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 —— 样例缺失不致命
            continue
        for c in d.get("coupons") or []:
            t = (c or {}).get("title")
            if t:
                titles.append(str(t))
        for t in d.get("storeCoupons") or []:
            if t:
                titles.append(str(t))
    return titles


# 追加池上限：从全菜单里挑出最值得「凑单」的商品数
POOL_LIMIT = 24
# 单次最多追加几件
MAX_ADD_DEFAULT = 3
# 官方验价候选数（控制接口调用量）
VERIFY_TOP_N = 30

# ---- 护栏：组合数随 max_add 组合爆炸，必须设硬上限 ----
# C(24,1..4) ≈ 12.9k 可接受；C(24,5) ≈ 54k 起，本地枚举已经明显变慢且无收益
MAX_ADD_HARD = 4
MAX_ENUM = 20_000

# ---- 凑单池打分权重（本地排序用，不对外宣称）----
W_FREE_HIT = 100.0    # 被「免费券」点名的商品：不点白不点
W_SELF_SAVE = 2.0     # 商品自身已有折扣的优先
W_PRICE_PENALTY = 0.05  # 越贵越难凑门槛，轻微惩罚


# ---------------------------------------------------------------------- #
# 券规则解析
# ---------------------------------------------------------------------- #
@dataclass
class CouponRule:
    """一条从券面文案解析出的规则。仅用于本地粗估排序，最终以官方验价为准。"""

    title: str
    kind: str = "unknown"      # threshold 满减 / bundle 多件折扣 / percent 折扣
                               # / free 免费 / bogo 买一送一 / unknown
    threshold: float = 0.0     # 门槛金额（元）
    need: int = 0              # bundle：需要几件才生效
    off: float = 0.0           # 优惠额（元）或折扣率（0.6 表示 6 折）
    free_name: str = ""        # 免费商品名关键词

    @property
    def readable(self) -> str:
        if self.kind == "threshold":
            return f"满{self.threshold:g}减{self.off:g}"
        if self.kind == "bundle":
            return f"{self.need}件{self.off * 10:g}折"
        if self.kind == "percent":
            return f"{self.off * 10:g}折"
        if self.kind == "free":
            return f"免费{self.free_name}"
        if self.kind == "bogo":
            return "买一送一"
        return self.title


_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _to_int(s: str) -> int:
    """支持「三件」「2件」两种写法。"""
    s = (s or "").strip()
    if s.isdigit():
        return int(s)
    return _CN_NUM.get(s, 0)


_RE_THRESHOLD = re.compile(r"满\s*(\d+(?:\.\d+)?)\s*元?\s*(?:减|省|立减)\s*(\d+(?:\.\d+)?)")
_RE_BUNDLE = re.compile(r"([0-9一二三四五六七八九十两]+)\s*件.*?(\d+(?:\.\d+)?)\s*折")
_RE_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*折")
_RE_FREE = re.compile(r"免费\s*(.{1,12}?)(?:券|$)")
_RE_BOGO_NAMED = re.compile(r"(.{1,10}?)\s*买一?送一")
_RE_BOGO = re.compile(r"买一?送一|第?二?份半价")


def parse_coupons(titles: list[str]) -> list[CouponRule]:
    """把券面文案（如「满30减5元券」「三件任选6折」「免费中薯条」）解析成规则。

    解析不出的一律降级为 ``unknown``——**宁可不估，也不瞎估**。
    """
    rules: list[CouponRule] = []
    seen: set[str] = set()
    for t in titles or []:
        title = (t or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        r = CouponRule(title=title)

        m = _RE_THRESHOLD.search(title)
        mb = _RE_BUNDLE.search(title)
        if m:
            r.kind = "threshold"
            r.threshold = float(m.group(1))
            r.off = float(m.group(2))
        elif mb and 0 < float(mb.group(2)) < 10 and _to_int(mb.group(1)) >= 2:
            # 「三件任选6折」：必须凑够件数才生效——这是凑单的关键约束
            r.kind = "bundle"
            r.need = _to_int(mb.group(1))
            r.off = round(float(mb.group(2)) / 10.0, 3)
        else:
            mb2 = _RE_BOGO_NAMED.search(title)
            if mb2:
                # 「中薯条买一送一」：必须真的点了 2 件中薯条才成立
                r.kind = "bogo"
                r.free_name = mb2.group(1).strip()
            elif _RE_BOGO.search(title):
                r.kind = "bogo"
            else:
                mf = _RE_FREE.search(title)
                if mf:
                    r.kind = "free"
                    r.free_name = mf.group(1).strip()
                else:
                    mp = _RE_PERCENT.search(title)
                    if mp and 0 < float(mp.group(1)) < 10:
                        r.kind = "percent"
                        r.off = round(float(mp.group(1)) / 10.0, 3)
        rules.append(r)
    return rules


def estimate_discount(items: list[MenuItem], rules: list[CouponRule]) -> float:
    """本地粗估优惠额（**只用于给候选排序**，不对外宣称）。

    注意件数约束：像「三件任选6折」这种券，件数不够就不该估出折扣，
    否则「只点必选」会被误判成全场最划算 —— 那就退化成「少买最省」了。
    """
    subtotal = sum(i.price for i in items)
    count = len(items)
    names = " ".join(i.name for i in items)
    best = 0.0
    for r in rules:
        if r.kind == "threshold" and subtotal >= r.threshold:
            best = max(best, r.off)
        elif (r.kind == "bundle" and count >= r.need) or r.kind == "percent":
            # bundle 需凑够件数、percent 无门槛，两者的折扣算式相同
            best = max(best, subtotal * (1.0 - r.off))
        elif r.kind == "free" and r.free_name and r.free_name in names:
            for i in items:
                if r.free_name in i.name:
                    best = max(best, i.price)
        elif r.kind == "bogo":
            if r.free_name:
                # 买一送一：送一份同款，故要求真的点了 2 件该商品
                hits = [i for i in items if r.free_name in i.name]
                if len(hits) >= 2:
                    best = max(best, min(i.price for i in hits))
            elif count >= 2:
                best = max(best, subtotal * 0.1)   # 不知道送什么，保守给一成
    return round(min(best, subtotal), 2)


# ---------------------------------------------------------------------- #
# 候选
# ---------------------------------------------------------------------- #
@dataclass
class Candidate:
    """一个待验价的候选组合。"""

    codes: tuple[str, ...] = ()
    est_original: float = 0.0
    est_paid: float = 0.0

    @property
    def key(self) -> frozenset[str]:
        return frozenset(self.codes)

    @property
    def est_rate(self) -> float:
        """粗估省钱率。**排序主指标**——见下方「为什么不用实付最低」。"""
        if not self.est_original:
            return 0.0
        return round((self.est_original - self.est_paid) / self.est_original, 4)


@dataclass
class Solution:
    """求解结果（价格一律来自官方验价）。"""

    items: list[CartItem] = field(default_factory=list)
    original: float = 0.0
    paid: float = 0.0
    discount: float = 0.0
    grade: str = "C"
    baseline_paid: float = 0.0     # 只点「想吃的那几样」的实付（直觉点法）
    baseline_items: list[CartItem] = field(default_factory=list)
    saved: float = 0.0             # baseline - paid
    enum_count: int = 0            # 本地枚举了几种（剪枝前）
    valid_count: int = 0           # 通过预算剪枝的候选数
    verify_count: int = 0          # 送去官方验价的候选数
    verify_ok: int = 0             # 验价成功返回的次数
    fail_count: int = 0            # 验价失败（网络/协议/业务）次数
    rules: list[CouponRule] = field(default_factory=list)
    nutrition: dict = field(default_factory=dict)
    max_kcal: float = 0.0          # 热量上限（0 = 不限），枚举/选优时按 kcal_map 剪枝

    @property
    def save_rate(self) -> float:
        return round(self.discount / self.original, 3) if self.original else 0.0

    @property
    def item_names(self) -> list[str]:
        return [i.name or i.product_code for i in self.items]

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def avg_price(self) -> float:
        return round(self.paid / self.count, 2) if self.count else 0.0

    @property
    def baseline_count(self) -> int:
        return len(self.baseline_items)

    @property
    def baseline_avg(self) -> float:
        return round(self.baseline_paid / self.baseline_count, 2) if self.baseline_count else 0.0

    @property
    def extra_count(self) -> int:
        return max(self.count - self.baseline_count, 0)


def grade_of(save_rate: float) -> str:
    """省钱率 → 评级。纯规则、可解释。"""
    if save_rate >= 0.45:
        return "S"
    if save_rate >= 0.30:
        return "A"
    if save_rate >= 0.15:
        return "B"
    return "C"


def is_better(rate: float, paid: float, best_rate: float,
              best_paid: float | None) -> bool:
    """选优判据：**省钱率优先，同率取实付更低**。

    最终选优（:func:`solve`）与验价进度的「新最优」通报**必须共用这一把尺**——
    否则进度里宣告的「新的最优」会按实付挑、最终答案却按省钱率挑，
    两者对不上，进度就变成了噪音。
    """
    return (best_paid is None
            or rate > best_rate + 1e-9
            or (abs(rate - best_rate) < 1e-9 and paid < best_paid))


# ---------------------------------------------------------------------- #
# 追加池与枚举
# ---------------------------------------------------------------------- #
def _free_keywords(rules: list[CouponRule]) -> list[str]:
    return [r.free_name for r in rules if r.kind == "free" and r.free_name]


def build_pool(menu_items: dict[str, MenuItem], rules: list[CouponRule],
               exclude: set[str], limit: int = POOL_LIMIT) -> list[MenuItem]:
    """挑出最值得「凑单」的商品池。

    排序依据：① 免费券点名的商品最优先（不点白不点）；
    ② 自身折扣力度大的；③ 价格低、容易凑到门槛的。
    """
    frees = _free_keywords(rules)
    scored: list[tuple[float, float, MenuItem]] = []
    for code, it in menu_items.items():
        if code in exclude or not it.name or it.price <= 0:
            continue
        bonus = W_FREE_HIT if any(f and f in it.name for f in frees) else 0.0
        save = max(it.original_price - it.price, 0.0)
        score = bonus + save * W_SELF_SAVE - it.price * W_PRICE_PENALTY
        scored.append((-score, it.price, it))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in scored[:limit]]


def effective_max_add(pool_size: int, max_add: int, cap: int = MAX_ENUM) -> int:
    """把 ``max_add`` 收敛到组合数不超过 ``cap`` 的最大可行值。

    ``max_add`` 是用户可传的，而 C(24, k) 增长极快（k=5 就 4 万+）。
    这里不靠"跑到一半截断"（那会只枚举出靠前的组合、结果有偏），
    而是**事先算好**能完整枚举到第几件，保证剪掉的是整层、不是半层。
    """
    if pool_size <= 0 or max_add <= 0:
        return 0
    total = 0
    for k in range(1, min(max_add, pool_size) + 1):
        total += math.comb(pool_size, k)
        if total > cap:
            return k - 1
    return min(max_add, pool_size)


def enumerate_candidates(must: list[str], menu_items: dict[str, MenuItem],
                         rules: list[CouponRule], *, budget: float = 0.0,
                         max_add: int = MAX_ADD_DEFAULT,
                         pool_limit: int = POOL_LIMIT,
                         kcal_map: dict[str, float] | None = None,
                         max_kcal: float = 0.0) -> tuple[list[Candidate], int]:
    """本地枚举候选：必选 + 0..max_add 件追加，按预算/热量剪枝。

    返回 ``(通过剪枝的候选, 剪枝前枚举总数)``——两者都如实上报：
    「试了多少种」用总数，别让约束把数字剪没了。

    热量剪枝说明：``kcal_map`` 是 ``code -> 单份 kcal``（营养库查不到的记 0，
    是**下界**）。只剪「下界已超限」的候选——绝不会误杀合规候选，
    也不会因为缺营养数据而高估热量；覆盖率在产物里另行披露。

    列表第一项恒为 baseline（只点必选），它是「你的直觉点法」的对照基准。
    """
    must = [c for c in must if c in menu_items]
    must_items = [menu_items[c] for c in must]
    must_sum = sum(i.price for i in must_items)

    def _kcal(items: list[MenuItem]) -> float:
        if kcal_map is None:
            return 0.0
        return sum(kcal_map.get(i.code, 0.0) for i in items)

    out: list[Candidate] = []
    base_paid = max(must_sum - estimate_discount(must_items, rules), 0.0)
    out.append(Candidate(codes=tuple(must), est_original=round(must_sum, 2),
                         est_paid=round(base_paid, 2)))

    pool = build_pool(menu_items, rules, exclude=set(must), limit=pool_limit)
    if not pool or max_add <= 0:
        return out, len(out)

    max_add = min(max_add, MAX_ADD_HARD)
    max_add = effective_max_add(len(pool), max_add, MAX_ENUM)
    if max_add <= 0:
        return out, len(out)

    total = len(out)
    for k in range(1, max_add + 1):
        for combo in itertools.combinations(pool, k):
            total += 1
            items = must_items + list(combo)
            subtotal = sum(i.price for i in items)
            if budget and subtotal > budget * 1.25:      # 留 25% 余量给优惠拉回
                continue
            if max_kcal and _kcal(items) > max_kcal:     # 热量下界已超限才剪
                continue
            est_paid = max(subtotal - estimate_discount(items, rules), 0.0)
            if budget and est_paid > budget:
                continue
            out.append(Candidate(
                codes=tuple(must) + tuple(i.code for i in combo),
                est_original=round(subtotal, 2), est_paid=round(est_paid, 2)))
    return out, total


def pick_verify_batch(cands: list[Candidate], top_n: int = VERIFY_TOP_N) -> list[Candidate]:
    """从候选中挑出送去官方验价的一批。

    排序主指标是**粗估省钱率**而非实付——否则「只点必选、什么都不加」永远最优，
    求解器就退化成劝人少买了。省钱率才度量「划算」，凑单的价值也才体现得出来。

    保证：① baseline 必验（对照基准）；② 同商品集合只验一次。
    """
    baseline = cands[0] if cands else None
    seen: set[frozenset[str]] = set()
    uniq: list[Candidate] = []
    for c in cands:
        if c.key in seen:
            continue
        seen.add(c.key)
        uniq.append(c)

    rest = sorted([c for c in uniq if c is not baseline],
                  key=lambda c: (-c.est_rate, c.est_paid, len(c.codes)))
    batch = ([baseline] if baseline else []) + rest[:max(top_n - 1, 0)]
    return batch


# ---------------------------------------------------------------------- #
# 求解主流程
# ---------------------------------------------------------------------- #
def _verify_batch(batch: list[Candidate], pricer, *, workers: int = 1,
                  on_progress=None) -> list[tuple[int, float, float, float]]:
    """对一批候选逐一验价，返回成功的 ``(候选下标, 原价, 实付, 优惠)``。

    ``workers > 1`` 时并发——真实模式下 30 次串行 HTTP 是整条链路唯一的耗时点，
    并发能把它压到 1/4 左右。``quote()`` 不修改会话、``requests`` 每次新建连接，
    因此并发是安全的；``ex.map`` 保证结果顺序与输入一致（baseline 仍在首位）。

    单个候选失败（网络抖动 / 业务拒绝）**不影响其余候选**，只计入失败数。
    """
    def run(item: tuple[int, Candidate]):
        idx, c = item
        try:
            original, paid, discount = pricer([(code, 1) for code in c.codes])
        except Exception:                                     # noqa: BLE001
            return None
        if original is None or paid is None:
            return None
        if paid <= 0 and original <= 0:
            return None
        return (idx, float(original), float(paid), float(discount or 0.0))

    items = list(enumerate(batch))
    out: list[tuple[int, float, float, float]] = []
    done = 0

    if workers <= 1 or len(items) <= 1:
        for it in items:
            res = run(it)
            done += 1
            _report(on_progress, done, res)
            if res:
                out.append(res)
        return out

    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
        for res in pool.map(run, items):     # 按输入顺序产出，异常已在 run 内吞掉
            done += 1
            _report(on_progress, done, res)
            if res:
                out.append(res)
    return out


def _report(on_progress, done: int, res) -> None:
    """回调格式 ``(已完成数, 本次实付 or None, 本次省钱率 or 0.0)``。

    传 paid 之外再传省钱率：进度展示与最终选优必须用同一把尺
    （省钱率优先、同率取实付更低），否则进度宣告的「新的最优」
    会与最终答案对不上。
    """
    if on_progress:
        if res:
            original, paid, discount = res[1], res[2], res[3]
            on_progress(done, paid, (discount / original) if original else 0.0)
        else:
            on_progress(done, None, 0.0)


def solve(must: list[str], menu_items: dict[str, MenuItem], rules: list[CouponRule],
          pricer, *, budget: float = 0.0, max_add: int = MAX_ADD_DEFAULT,
          top_n: int = VERIFY_TOP_N, nutrition_lookup=None,
          workers: int = 1, on_progress=None,
          kcal_map: dict[str, float] | None = None,
          max_kcal: float = 0.0) -> Solution:
    """求解最优组合。

    ``pricer`` 是验价器：``pricer(list[tuple[code, qty]]) -> (original, paid, discount)``。
    真实模式下它调 ``calculate-price``；离线模式下用本地规则估算（仅用于演示）。

    ``workers`` 控制验价并发度（真实模式的提速开关；离线模式恒为 1 也无妨）。

    ``kcal_map``（code -> 单份 kcal，查不到的记 0）配合 ``max_kcal`` 做**热量约束**：
    枚举阶段剪「热量下界已超限」的候选，选优阶段再过滤一次，保证最终答案
    同时满足预算与热量两个上限。
    """
    cands, total_seen = enumerate_candidates(must, menu_items, rules, budget=budget,
                                             max_add=max_add, kcal_map=kcal_map,
                                             max_kcal=max_kcal)
    batch = pick_verify_batch(cands, top_n=top_n)
    results = _verify_batch(batch, pricer, workers=workers, on_progress=on_progress)

    sol = Solution(rules=list(rules), enum_count=total_seen, valid_count=len(cands),
                   verify_count=len(batch), verify_ok=len(results),
                   fail_count=len(batch) - len(results), max_kcal=max_kcal)
    best_rate = -1.0
    best_paid: float | None = None

    def _kcal_of(codes) -> float:
        if kcal_map is None:
            return 0.0
        return sum(kcal_map.get(c, 0.0) for c in codes)

    for idx, original, paid, discount in results:
        if budget and paid > budget:
            continue
        if max_kcal and _kcal_of(batch[idx].codes) > max_kcal:
            continue

        # 第一个候选即 baseline（只点必选）
        if idx == 0:
            sol.baseline_paid = paid
            sol.baseline_items = [_cart(code, menu_items) for code in batch[0].codes]

        # 主指标省钱率，同率时取实付更低者——「划算」优先于「便宜」
        rate = (discount / original) if original else 0.0
        if is_better(rate, paid, best_rate, best_paid):
            best_rate, best_paid = rate, paid
            sol.original, sol.paid, sol.discount = original, paid, discount
            sol.items = [_cart(code, menu_items) for code in batch[idx].codes]

    if sol.items:
        sol.grade = grade_of(sol.save_rate)
        sol.saved = round(sol.baseline_paid - sol.paid, 2)     # 可能为负（多花多得）
        if nutrition_lookup:
            sol.nutrition = nutrition_lookup([i.name for i in sol.items])
    return sol


def _cart(code: str, menu_items: dict[str, MenuItem]) -> CartItem:
    it = menu_items.get(code)
    return CartItem(
        product_code=code,
        name=it.name if it else code,
        quantity=1,
        price=it.price if it else 0.0,
        image=it.image if it else "",
    )


# ---------------------------------------------------------------------- #
# 真实验价器（调 calculate-price）
# ---------------------------------------------------------------------- #
def make_remote_pricer(client, session, menu):
    """返回一个调官方 ``calculate-price`` 的验价器。

    单个候选失败直接抛出，由 :func:`_verify_batch` 统一记账——
    一个组合算不出来不该拖垮整次求解，但**失败次数必须在产物里披露**。
    """
    from .ordering import quote as calc_quote

    def pricer(pairs: list[tuple[str, int]]):
        cart = [CartItem(product_code=c, quantity=q) for c, q in pairs]
        q: OrderQuote = calc_quote(client, session, cart, menu)
        return q.original, q.paid, q.discount

    return pricer


# ---------------------------------------------------------------------- #
# 离线验价器（按菜单价 + 券规则本地估算，仅供演示）
# ---------------------------------------------------------------------- #
def eat_plan(sol: "Solution", store_code: str = "") -> dict:
    """把最优解翻译成宿主 agent 可直接执行的「下一步点餐计划」——solve→eat 闭环。

    CLI 已移除，这里不再产出命令行，而是与官方 ``create-order`` 参数对齐的
    结构化指令（``storeCode`` / ``items[].productCode|quantity``）。是否真正下单
    由宿主 agent 按 SKILL.md 护栏执行：先 ``calculate-price`` 算价、再请用户
    显式确认。无解时返回空 dict（调用方不产出「下一步」）。
    """
    if not sol.items:
        return {}
    plan: dict = {
        "tool": "create-order",
        "items": [
            {"productCode": i.product_code, "quantity": max(int(i.quantity), 1)}
            for i in sol.items
        ],
        "guardrail": "调用前先 calculate-price 算价，并请用户显式确认后再下单",
    }
    if store_code:
        plan["storeCode"] = store_code
    return plan


def make_offline_pricer(menu_items: dict[str, MenuItem], rules: list[CouponRule]):
    """离线演示用：**不调接口**，按菜单价与券规则本地估算。

    口径必须在产物里声明：离线为演示估算，真实价格以官方验价为准。
    """
    def pricer(pairs: list[tuple[str, int]]):
        items: list[MenuItem] = []
        for code, qty in pairs:
            it = menu_items.get(code)
            if not it:
                continue
            items.extend([it] * max(int(qty), 1))
        subtotal = sum(i.price for i in items)
        discount = estimate_discount(items, rules)
        paid = round(max(subtotal - discount, 0.0), 2)
        return round(subtotal, 2), paid, round(discount, 2)

    return pricer
