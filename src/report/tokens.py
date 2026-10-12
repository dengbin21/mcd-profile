"""报告通用设计 token —— McSolve 战报与 McPreheat 预热卡共用。

**为什么要有这个模块**：两张卡片最初各复制了一份 CSS，细节已经漂移——
区块标题一个是 14px 灰色、另一个是 16px 金色；面板内边距、页脚颜色、
CTA 间距、评分徽章尺寸也各不相同。摆在一起看像两个产品。

这里抽出公共外壳，两张卡片共用同一套设计语言；各自的
主视觉（战报的价格区 / 预热台的倒计时区）仍留在自己模块里。

配色取自 ``src.theme`` 的「优惠猎人」（麦当劳品牌金），与既有档案卡片同族。
"""
from __future__ import annotations

from ..theme import THEMES

_BRAND = THEMES.get("优惠猎人", next(iter(THEMES.values())))

INK = _BRAND.ink            # 主文字
MUTED = _BRAND.muted        # 次文字
PRIMARY = _BRAND.primary    # 主强调（品牌金）
ACCENT = _BRAND.accent      # 次强调

BG = "#0B0A08"              # 页面底色
PANEL = "#12100C"           # 面板
PANEL_IN = "#1A1710"        # 面板内嵌块

REPO_URL = "https://github.com/dengbin21/mcd-profile"

# ---------------------------------------------------------------------- #
# 公共外壳
# ---------------------------------------------------------------------- #
REPORT_BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0B0A08;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#F6F4EF}
.wrap{max-width:1080px;margin:0 auto;padding:28px 24px 40px}

.sec{margin-top:20px;border-radius:22px;padding:24px 22px;background:#12100C;
  border:1px solid rgba(255,255,255,.07)}
.h{font-size:14px;letter-spacing:.18em;color:#98938B;margin-bottom:16px}

.list{margin-top:12px;list-style:none}
.list li{padding:9px 0;border-bottom:1px solid rgba(255,255,255,.06);
  font-size:15px;line-height:1.5}
.list li:last-child{border-bottom:0}

.chips{display:flex;flex-wrap:wrap;gap:9px}
.chip{padding:7px 13px;border-radius:999px;background:rgba(255,199,44,.12);
  color:#FFE38A;font-size:14px}
.chip.dim{background:rgba(255,255,255,.06);color:#98938B}

.badge{width:76px;height:76px;border-radius:21px;display:flex;align-items:center;
  justify-content:center;font-size:42px;font-weight:800;color:#171205}
.stats{display:flex;gap:14px;text-align:center}
.stat{flex:1;background:#1A1710;border-radius:16px;padding:16px 10px}
.snum{font-size:26px;font-weight:800;color:#FFC72C}
.slab{font-size:12px;color:#98938B;margin-top:6px;line-height:1.5}

.note{margin-top:14px;padding:10px 14px;border-radius:12px;font-size:13px;
  line-height:1.7;background:rgba(255,199,44,.08);
  border:1px solid rgba(255,199,44,.22);color:#E8C86A}
.warn{margin-top:10px;font-size:12px;color:#8A6A2E}

.foot{margin-top:22px;text-align:center;font-size:13px;color:#7C766D;line-height:1.9}
.cta{margin-top:14px;text-align:center;font-size:16px;font-weight:700;color:#FFC72C}
"""
