"""麦麦预热台 · McPreheat：把官方营销活动日历变成一张「倒计时备战卡」。

为什么做这个
------------
``campaign-calendar`` 在绝大多数作品里只是「把活动列出来给你看」——
一个静态列表，看完没有任何行动理由。

但把它和 **券的到期时间** 交叉起来，就会出现一个真实的冲突：

    距「周末欢乐桶限时回归」还有 15 天
    你手里的「满30减5」10-12 到期
    → 这张券等不到那天

这个冲突是**算出来的**，不是编的：券的到期日来自 ``query-my-coupons``
的 ``instructions.availableTime``，活动日期来自 ``campaign-calendar``。
它同时具备三样东西——**紧迫感（倒计时）、行动理由（先用掉）、可比较（备战度评级）**，
这就是本产品的钩子。

全程只读：不领券、不抽奖、不下单。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .models import CampaignEvent
from .textpack import CopyPack, TextResolver, pick_grade_word

# 「多久之内到期」算紧急
URGENT_DAYS = 7

# 备战度扣分/加分权重（纯规则、可解释，产物里会原样披露）
#
# 配平原则一：**扣分必须压得住加分**。早期版本给 S 太容易——
# 「3 张券里有 1 张赶不上活动」仍被评为 S（弹药充足），这是自相矛盾的。
# 现在一张 miss 就 -25，配合 +5/+5 的小额加分，有冲突必定掉到 A 以下。
#
# 配平原则二：**临期扣分必须封顶**。临期券是「快过期的弹药」，不是缺口——
# 不封顶的话，手里 10 张券全在 7 天内到期就会 -100 直接触底，
# 卡片上写着「裸奔进场，建议先清券」，可这人手上是全场弹药最足的那个。
# 语义被算反了，所以只扣前 3 张。
PENALTY_MISS = 25      # 每张等不到活动的券
PENALTY_URGENT = 10    # 每张 7 天内到期（且尚未计入 miss）
URGENT_CAP = 3         # 临期扣分最多算 3 张——券多不是罪
PENALTY_NO_COUPON = 20 # 活动当天一张券都不剩
BONUS_RUNNING = 5      # 今天本来就有活动在进行
BONUS_POINTS = 5       # 积分够兑换门槛

_GRADE = ((85, "S"), (70, "A"), (50, "B"))
_GRADE_WORD = {
    "S": "弹药充足，稳了",
    "A": "大体就绪，还能补",
    "B": "有缺口，先看冲突",
    "C": "裸奔进场，建议先清券",
}


# ---------------------------------------------------------------------- #
# 日期解析
# ---------------------------------------------------------------------- #
_DATE_SEP = re.compile(r"[.\-/年]")
_TAIL = re.compile(r"[月日号].*$")

# 官方券面到期文案里出现过「今日」——这是**无歧义**的自然语言，不是模糊表述，
# 认它不算猜。其余读不懂的一律按「不知道」处理并**计数披露**（见 parse_until）。
TODAY_WORDS = ("今日", "今天")


def _date_candidates(text: str) -> list[date]:
    """按出现顺序抠出文案里的**所有**日期。

    为什么必须抠全：``query-my-coupons`` 的 ``availableTime`` 真实返回过
    ``2026.10.05-2026.10.11`` 这种**区间**写法。早先只取前三个数字段，
    于是这张**明天才到期**的券被算成 5 天前就过期——预热卡上凭空多出一条
    「已过期、等不到活动」的假冲突，备战度还被白扣 25 分。
    区间的每一段都要抠出来，交给调用方决定取首（开始）还是取尾（截止）。
    """
    s = (text or "").strip()
    if not s:
        return []
    # 只取日期部分，丢掉时间
    s = s.split(" ")[0].split("T")[0]
    s = _TAIL.sub("", s)
    parts = [p for p in _DATE_SEP.split(s) if p]
    if len(parts) < 2:
        return []
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return []
    out: list[date] = []
    y, i = date.today().year, 0
    while i < len(nums):
        if nums[i] >= 1000 and i + 3 <= len(nums):      # 带年的三段：2026.10.16
            y, m, d, i = nums[i], nums[i + 1], nums[i + 2], i + 3
        elif i + 2 <= len(nums):                        # 只有月日 → 用当前年兜底
            m, d, i = nums[i], nums[i + 1], i + 2
        else:
            break
        try:
            out.append(date(y, m, d))
        except ValueError:                              # 非法日期（如 10 月 40 日）丢弃
            pass
    return out


def parse_when(text: str) -> date | None:
    """活动日期：取文案里的**第一个**日期。

    支持：``2026.10.16 23:59`` / ``2026-10-16`` / ``2026/10/16``。
    区间写法按**开始日**算（活动的第一天）。
    解析不出来返回 ``None``——**宁可当成「不知道」，也不猜一个日期出来。**
    """
    ds = _date_candidates(text)
    return ds[0] if ds else None


def parse_until(text: str) -> date | None:
    """券的「有效期至」：取文案里的**最后一个**日期。

    ``2026.10.05-2026.10.11`` 的有效期截止是 **10-11**，不是 10-05——
    取第一个日期会把「明天到期」说成「5 天前已过期」。
    """
    ds = _date_candidates(text)
    return ds[-1] if ds else None


def parse_server_time(text: str) -> date | None:
    """``now-time-info`` / 样例里的服务器时间（``2026-10-09 16:48:16``）。"""
    return parse_when(text or "")


# ---------------------------------------------------------------------- #
# 数据结构
# ---------------------------------------------------------------------- #
@dataclass
class CouponWatch:
    """一张券在「预热」视角下的状态。"""

    title: str
    until_text: str = ""
    until: date | None = None
    days_to_expire: int | None = None   # 距今还有几天到期（已过期为负）
    survives: bool | None = None        # 能否撑到目标活动当天
    unparsed: bool = False              # 写了到期文案但读不懂——必须披露，不能静默丢

    @property
    def expired(self) -> bool:
        return self.days_to_expire is not None and self.days_to_expire < 0

    @property
    def urgent(self) -> bool:
        return (self.days_to_expire is not None
                and 0 <= self.days_to_expire <= URGENT_DAYS)

    @property
    def tight(self) -> bool:
        """撑得到活动，但到期日就在眼前——「压线过关」，值得单独标出来。"""
        return self.survives is True and self.urgent


@dataclass
class Preheat:
    today: date
    server_time: str = ""
    target: CampaignEvent | None = None
    target_date: date | None = None
    days_left: int | None = None        # 距目标活动天数（活动当天为 0）
    running: list[CampaignEvent] = field(default_factory=list)   # 今日进行中
    upcoming: list[CampaignEvent] = field(default_factory=list)  # 其余未来活动
    unparsed_count: int = 0         # 日期解析不出来的活动条数——必须披露，不能静默丢
    coupon_unparsed_count: int = 0  # 到期文案读不懂的券数——同上，否则这批券凭空消失
    coupons: list[CouponWatch] = field(default_factory=list)
    points: float = 0.0
    redeem_floor: float | None = None   # 最便宜的积分兑换门槛
    redeemable: int = 0                 # 当前积分够兑几件
    score: int = 0
    grade: str = "C"
    headline: str = ""
    tips: list[str] = field(default_factory=list)
    # 模型可在 copy.preheat 里整句覆写「钩子句」与「评级词」（高于规则句式）
    grade_word_override: str = ""

    # ---- 派生视图 ----
    @property
    def missing(self) -> list[CouponWatch]:
        """等不到活动当天的券——钩子的主体。"""
        return [c for c in self.coupons if c.survives is False]

    @property
    def surviving(self) -> list[CouponWatch]:
        return [c for c in self.coupons if c.survives is True]

    @property
    def urgent(self) -> list[CouponWatch]:
        return [c for c in self.coupons if c.urgent and c.survives is not False]

    @property
    def grade_word(self) -> str:
        return self.grade_word_override or _GRADE_WORD.get(self.grade, "")

    @property
    def progress(self) -> float:
        """倒计时进度：已走过的比例（0..1），用于画进度环。"""
        if not self.days_left or self.days_left <= 0:
            return 1.0
        span = max(self.days_left, 1)
        # 以 30 天为预热窗口，超过 30 天就当成刚起步
        return round(min(1.0 - span / 30.0, 1.0), 3) if span < 30 else 0.0


# ---------------------------------------------------------------------- #
# 构建
# ---------------------------------------------------------------------- #
def pick_target(campaigns: list[CampaignEvent], today: date) -> CampaignEvent | None:
    """挑最近一场**还没开始**的活动作为预热对象。

    两个刻意的选择：

    1. **不用 ``stage`` 字段**——真实接口里 stage 未必可靠（样例就 today/future 混着来），
       一律按日期判断；
    2. **严格取 ``d > today``**——今天已经在跑的活动归到 ``running``，不能当倒计时目标，
       否则倒计时恒为 0，整个钩子就没了。
    """
    best: CampaignEvent | None = None
    best_d: date | None = None
    for c in campaigns or []:
        d = parse_when(c.date)
        if not d or d <= today:
            continue
        if best_d is None or d < best_d:
            best, best_d = c, d
    return best


def watch_coupons(coupons, today: date, target_date: date | None) -> list[CouponWatch]:
    """把券的到期文案翻译成「还能不能撑到活动当天」。

    ``coupons`` 接受任意带 ``title`` / ``available_until`` 属性的对象
    （``src.models.Coupon`` 或 duck-typed 的字典/对象都行）。

    到期文案有三种结局，每一种都必须**看得见**：

    * 解析出日期 → 正常参与冲突判断；
    * 写了但读不懂（如「长期有效」）→ 标 ``unparsed``，由 ``Preheat`` 计数披露。
      真实接口里出现过「今日」——今天到期的券本该是**最紧急**的一张，
      早先它读不懂就被静默丢弃，三个清单里一个都不出现，等于凭空消失；
    * 根本没写 → 同样不参与判断，但不算「读不懂」，不进披露计数。
    """
    out: list[CouponWatch] = []
    for c in coupons or []:
        title = getattr(c, "title", None)
        until_text = getattr(c, "available_until", None)
        if title is None and isinstance(c, dict):
            title = c.get("title", "")
            until_text = c.get("available_until", "") or c.get("until", "")
        title = title or ""
        until_text = until_text or ""
        until = parse_until(until_text)
        if until is None and until_text.strip() in TODAY_WORDS:
            until = today                    # 「今日」= 今天到期，无歧义
        w = CouponWatch(title=title, until_text=until_text, until=until)
        if until:
            w.days_to_expire = (until - today).days
            if target_date:
                w.survives = until >= target_date
        elif until_text.strip():
            w.unparsed = True
        out.append(w)
    # 快过期的排前面——用户最先该看到的
    out.sort(key=lambda w: (w.days_to_expire is None, w.days_to_expire or 0))
    return out


def urgent_penalty_count(pre: Preheat) -> int:
    """计入扣分的临期券张数（封顶）。

    「快过期」是提醒，不是罪状——**持券多的人不该被扣成裸奔**，
    所以只对最紧急的前 ``URGENT_CAP`` 张计分。
    """
    return min(len(pre.urgent), URGENT_CAP)


def score_of(pre: Preheat) -> tuple[int, str]:
    """备战度评分。纯规则、可解释——产物里会逐条列出加减项。"""
    if pre.target is None:
        # 没有预热对象时，只评价券包的健康度
        s = 80 - PENALTY_URGENT * urgent_penalty_count(pre)
        s = max(0, min(100, int(s)))
    else:
        s = 100
        s -= PENALTY_MISS * len(pre.missing)
        s -= PENALTY_URGENT * urgent_penalty_count(pre)
        if not pre.surviving:
            s -= PENALTY_NO_COUPON
        if pre.running:
            s += BONUS_RUNNING
        if pre.redeem_floor and pre.points >= pre.redeem_floor:
            s += BONUS_POINTS
        s = max(0, min(100, int(s)))
    for floor, g in _GRADE:
        if s >= floor:
            return s, g
    return s, "C"


def build_preheat(campaigns: list[CampaignEvent], coupons, *, today: date | None = None,
                  server_time: str = "", points: float = 0.0,
                  redeem_points: list[float] | None = None,
                  copy: CopyPack | None = None) -> Preheat:
    """组装预热台。

    ``redeem_points`` 是积分商城各商品所需积分；据此算「当前积分够兑几件」。

    ``copy`` 为 WorkBuddy 生成的文案包（可选）：
    先按 ``ph.*`` 文案键改写规则句式，再允许 ``copy.preheat`` 整句覆写
    ``headline`` / ``grade_word`` / ``tips``（**后者优先级更高**）。
    """
    parsed_server = parse_server_time(server_time)
    today = today or parsed_server or date.today()

    pre = Preheat(today=today, server_time=server_time, points=float(points or 0.0))

    # ---- 活动分桶：按日期，不按 stage ----
    # 与档案系（analyze_activity 信 stage）不同，这里一律按日期判；
    # 解析不出来的**必须计数并披露**——否则真实接口返回中文日期时，
    # 预热台会静默退化成「没有可预热的活动」，而 campaign 命令仍正常显示，两处打架。
    for c in campaigns or []:
        d = parse_when(c.date)
        if d is None:
            pre.unparsed_count += 1
            continue
        if d == today:
            pre.running.append(c)
        elif d > today:
            pre.upcoming.append(c)
    pre.running.sort(key=lambda c: c.title)
    pre.upcoming.sort(key=lambda c: parse_when(c.date) or today)

    # ---- 预热对象 ----
    target = pick_target(campaigns, today)
    if target is not None:
        pre.target = target
        pre.target_date = parse_when(target.date)
        if pre.target_date:
            pre.days_left = (pre.target_date - today).days

    # ---- 券 ----
    pre.coupons = watch_coupons(coupons, today, pre.target_date)
    # 到期文案读不懂的券：不参与任何判断，但**必须数出来露出去**——
    # 否则用户会以为自己没这张券（真实接口里「今日」就差点这么消失）。
    pre.coupon_unparsed_count = sum(1 for c in pre.coupons if c.unparsed)

    # ---- 积分 ----
    pts = [p for p in (redeem_points or []) if p and p > 0]
    if pts:
        pre.redeem_floor = min(pts)
        pre.redeemable = sum(1 for p in pts if pre.points >= p)

    tx = TextResolver(copy)
    pre.score, pre.grade = score_of(pre)
    pre.headline = _headline(pre, tx)
    pre.tips = _tips(pre, tx)

    # 模型整句覆写（优先级高于规则句式）：给了就用，没给不动
    if copy is not None:
        hl = str(copy.preheat.get("headline") or "").strip()
        if hl:
            pre.headline = hl
        # 评级词支持「整词字符串」或 {"S"/"A"/"B"/"C": 词} 两种写法
        gw = pick_grade_word(copy.preheat, pre.grade).strip()
        if gw:
            pre.grade_word_override = gw
        ov = copy.preheat.get("tips")
        if isinstance(ov, list) and ov:
            pre.tips = [str(x) for x in ov]
    return pre


def _headline(pre: Preheat, tx=None) -> str:
    """钩子文案：一句话把「倒计时」和「冲突」同时说出来。

    句式全部走 ``ph.hook_*`` 文案键，模型可改写（``--copy``）；
    未注入文案包时用 ``TextResolver(None)`` 的默认值，结果与规则期完全一致。
    """
    tx = tx or TextResolver(None)
    if pre.target is None:
        if pre.unparsed_count and not pre.running and not pre.upcoming:
            # 活动拿得到、日期读不懂：必须说清是「读不懂」而不是「没有」
            return tx("ph.hook_unparsed", n=pre.unparsed_count)
        if pre.running:
            return tx("ph.hook_running", title=pre.running[0].title)
        return tx("ph.hook_none")
    title = pre.target.title
    d = pre.days_left or 0
    if d <= 0:
        return tx("ph.hook_today", title=title)
    miss = len(pre.missing)
    if miss:
        return tx("ph.hook_conflict", title=title, d=d, n=miss)
    if d <= 3:
        return tx("ph.hook_ready", title=title, d=d)
    return tx("ph.hook_plain", title=title, d=d)


def _tips(pre: Preheat, tx=None) -> list[str]:
    """行动建议。每条都是**算出来的**，不是通用鸡汤。

    句式走 ``ph.tip_*`` 文案键；模型也可在 ``copy.preheat.tips`` 里整段重写。
    """
    tx = tx or TextResolver(None)
    tips: list[str] = []
    for c in pre.missing[:3]:
        left = c.days_to_expire or 0
        if left < 0:
            tips.append(tx("ph.tip_expired", title=c.title))
        elif left == 0:
            # 「还剩 0 天到期」没人看得懂——今天到期就说今天。
            tips.append(tx("ph.tip_missing_today", title=c.title,
                           target=(pre.target.title if pre.target else "活动")))
        else:
            tips.append(tx("ph.tip_missing", title=c.title, n=left,
                           target=(pre.target.title if pre.target else "活动")))
    for c in pre.urgent[:2]:
        if c.days_to_expire == 0:
            tips.append(tx("ph.tip_urgent_today", title=c.title))
        else:
            tips.append(tx("ph.tip_urgent", title=c.title, n=c.days_to_expire))
    if pre.target and not pre.surviving and pre.coupons:
        tips.append(tx("ph.tip_no_coupon"))
    if pre.redeem_floor and pre.points >= pre.redeem_floor:
        tips.append(tx("ph.tip_points", points=pre.points, n=pre.redeemable))
    if pre.running:
        tips.append(tx("ph.tip_running",
                       titles="、".join(c.title for c in pre.running[:2])))
    if not tips:
        tips.append(tx("ph.tip_healthy"))
    return tips


def remaining_parts(pre: Preheat) -> tuple[int, int, int, int]:
    """距目标活动的 (天, 时, 分, 秒)，用于实时倒计时。

    只有日期没有时刻，按当天 00:00 起算；已开始则全 0。
    """
    if not pre.target_date or not pre.days_left or pre.days_left <= 0:
        return (0, 0, 0, 0)
    start = datetime(pre.target_date.year, pre.target_date.month, pre.target_date.day)
    now = datetime(pre.today.year, pre.today.month, pre.today.day)
    secs = int((start - now).total_seconds())
    if secs <= 0:
        return (0, 0, 0, 0)
    return (secs // 86400, secs % 86400 // 3600, secs % 3600 // 60, secs % 60)
