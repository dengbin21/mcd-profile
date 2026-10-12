"""报告通用设计 token —— McSolve 战报与 McPreheat 预热卡共用。

**为什么要有这个模块**：两张卡片最初各复制了一份 CSS，细节已经漂移——
区块标题一个是 14px 灰色、另一个是 16px 金色；面板内边距、页脚颜色、
CTA 间距、评分徽章尺寸也各不相同。摆在一起看像两个产品。

这里抽出公共外壳，两张卡片共用同一套设计语言；各自的
主视觉（战报的价格区 / 预热台的倒计时区）仍留在自己模块里。

配色沿用 ``src.theme`` 的「优惠猎人」（麦当劳品牌金）家族，与档案卡片同族。
"""
from __future__ import annotations

REPO_URL = "https://github.com/dengbin21/mcd-profile"

# 评级 → 强调色（McSolve 战报与 McPreheat 预热卡共用同一把颜色尺）
GRADE_COLOR = {"S": "#FFC72C", "A": "#17C3A2", "B": "#4D7CFE", "C": "#98938B"}


def esc(s: str) -> str:
    """HTML 转义，但放行 ``<br>``——模型文案靠它换行，其余标签一律挡掉。

    文案来自模型，**不能直接插进 HTML**：否则一句带 ``<script>`` 的文案
    就能把分享卡变成注入载体。这里白名单只留换行。
    """
    if not s:
        return ""
    out = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
           .replace('"', "&quot;"))
    return out.replace("&lt;br&gt;", "<br>").replace("&lt;/br&gt;", "<br>")


def html_wrap(title: str, css: str, body: str) -> str:
    """公共 HTML 文档骨架：McSolve / McPreheat 两张卡片共用同一外壳。"""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{css}</style></head>
<body><div class="wrap">

{body}

</div></body></html>"""


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
