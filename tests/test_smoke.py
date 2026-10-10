"""轻量自检：不联网、不依赖 pytest，直接 `python tests/test_smoke.py` 即可运行。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import images                                                    # noqa: E402
from src.archive import build_archive, load_meal_report_sample            # noqa: E402
from src.textpack import CopyPack, build_copy_brief, text_defaults            # noqa: E402
from src.models import (CartItem, MealReport, MenuItem, OrderQuote,       # noqa: E402
                        TakeWay)
from src.nutrition import load_snapshot, NutritionIndex                   # noqa: E402
from src.ordering import Menu, menu_probe_fields                     # noqa: E402
from src.menu_view import render_menu_html                                # noqa: E402
from src.report import render_markdown, render_card_html                  # noqa: E402
from src.theme import THEMES, DEFAULT_THEME, build_badges, build_quips, theme_for  # noqa: E402


def test_offline_archive():
    a = build_archive(None, use_remote=False)
    assert a.meta["order_total"] == 19, f"样例应为 19 单，实际 {a.meta['order_total']}"
    assert a.consumption.refunded_count == 1, "应识别出 1 单退款"
    assert a.consumption.order_count == 18, "有效订单应为 18"
    assert 0 < a.health.coverage <= 100, "营养覆盖率应在 (0,100]"


def test_nutrition_match():
    idx = NutritionIndex(load_snapshot())
    assert idx.match("猪柳蛋麦满分") is not None
    assert idx.match("大杯鲜萃咖啡") is not None
    assert idx.match("中薯条").productName == "中薯条"
    # 大杯/小杯规格归一化后仍能命中
    hit = idx.match("小杯玉米杯")
    assert hit is not None and "玉米杯" in hit.productName


def test_persona_and_report():
    a = build_archive(None, use_remote=False)
    assert a.persona.label, "人格标签不应为空"
    assert a.persona.radar and all(0 <= v <= 100 for v in a.persona.radar.values())
    md = render_markdown(a)
    assert "麦麦档案" in md and "消费画像" in md and "健康画像" in md
    html = render_card_html(a)
    assert "<svg" in html and a.persona.label in html


def test_extra_domains():
    """新增域：省钱 / 习惯 / 活动 / 权益拓展 / 工具覆盖。"""
    a = build_archive(None, use_remote=False)
    # 省钱画像
    assert a.savings.enriched_orders > 0, "样例应含优惠明细"
    assert a.savings.total_discount > 0, "累计优惠应大于 0"
    assert 0 < a.savings.discount_rate < 1
    # 习惯画像（官方「我的常点」）
    assert a.habit.frequent_name, "应解析出官方常点"
    assert a.habit.peak_slot, "应有最活跃时段"
    # 活动画像
    assert a.activity.current or a.activity.upcoming, "应有活动数据"
    # 权益拓展
    assert a.benefit.redeem_count > 0, "应有可兑换商品"
    assert a.benefit.available_coupon_count > 0, "应有可领取券"
    assert a.benefit.lottery_activity, "应有抽奖活动"
    # 报告章节齐全
    md = render_markdown(a)
    for kw in ("省钱画像", "习惯画像", "权益画像", "近期活动", "工具覆盖清单"):
        assert kw in md, f"报告应含「{kw}」"


def test_theme_and_badges():
    """千人千面：主题映射、徽章墙、金句。"""
    a = build_archive(None, use_remote=False)
    th = theme_for(a.persona)
    assert th is not None and th.primary.startswith("#"), "主题应有十六进制主色"
    assert th is DEFAULT_THEME or th.name in {t.name for t in THEMES.values()}
    badges = build_badges(a)
    assert badges, "样例应能生成徽章"
    assert len(badges) <= 9, "徽章墙最多 9 枚（3×3）"
    assert all(b.title for b in badges)
    quips = build_quips(a)
    assert quips and len(quips) <= 4
    # 主题名应出现在 Markdown 标题区
    assert th.name in render_markdown(a)


def test_meal_report_combined_archive():
    """点餐闭环：战报 + 历史画像合体（离线样例战报）。"""
    rep = load_meal_report_sample()
    assert rep is not None, "应能加载脱敏战报样例"
    assert rep.items and rep.paid_amount > 0
    assert rep.kcal > 0, "战报应算出本单热量"
    a = build_archive(None, use_remote=False, order_report=rep)
    assert a.order_report is not None
    md = render_markdown(a)
    assert "本次点餐战报" in md and rep.store_name in md
    assert "成就徽章墙" in md and "麦门金句" in md
    html = render_card_html(a)
    assert "本次点餐战报" in html and rep.store_name in html


def test_ordering_models():
    """点餐模型：算价 / 战报派生字段。"""
    q = OrderQuote(paid=42.0, original=63.5, discount=21.5,
                   items=[CartItem("SAMPLE-1", "巨无霸套餐", 1)], take_way_list=[TakeWay("1", "堂食")])
    assert abs(q.discount_rate - 0.339) < 0.01
    mr = MealReport(items=[CartItem("a", "甲", 2), CartItem("b", "乙", 1)],
                    original_amount=100.0, discount_amount=30.0, kcal=1100.0)
    assert mr.item_count == 3
    assert mr.bigmac_equiv == 2.0
    assert abs(mr.discount_rate - 0.3) < 1e-9


def test_full_text_override():
    """除数值外，全部文字均可由 CopyPack 覆写（区块标题/指标名/雷达维度/徽章名）。"""
    a = build_archive(None, use_remote=False)
    badges = build_badges(a)
    cp = CopyPack(
        source="test",
        persona_label="试验称号",
        labels={
            "sec.consumption": "消费力透视",          # 仅出现在 Markdown
            "sec.radar": "战力透视",                  # 仅出现在 HTML/PNG
            "lbl.total_spend": "总花销",
            "lbl.kpi_save_rate": "省下占比{rate}%",   # 占位符必须被保留并填充
        },
        radar={k: k + "·改" for k in a.persona.radar},
        badge_title={badges[0].title: "新徽章名"} if badges else {},
    )
    assert cp.active, "含覆写字段时 active 应为 True"

    md = render_markdown(a, cp)
    html = render_card_html(a, cp)
    # 覆写的区块标题生效，且旧标题消失
    assert "消费力透视" in md and "消费画像" not in md       # Markdown 专属键
    assert "战力透视" in html and "麦门战力雷达" not in html  # 卡片专属键
    # 指标名覆写（Markdown 消费表）
    assert "总花销" in md
    # 占位符被真实数值填充（不应残留 "{rate}"）
    assert "{rate}" not in html and "省下占比" in html
    # 雷达维度名覆写（HTML 内联 SVG 标签）
    assert "·改" in html
    # 徽章名覆写
    if badges:
        assert "新徽章名" in md
    # 数值仍由规则计算：全文仍包含真实金额
    assert "¥" in md


def test_brief_exports_full_text():
    """brief 导出全部文字默认值 + 动态文字（雷达维度/徽章名）。"""
    a = build_archive(None, use_remote=False)
    brief = build_copy_brief(a)
    tm = brief["text_map"]
    assert "sec.consumption" in tm and tm["sec.consumption"] == "消费画像"
    assert set(tm) == set(text_defaults()), "text_map 应覆盖整个注册表"
    assert brief["dynamic_text"]["radar"], "应导出雷达维度名"
    assert all(k in brief["schema"] for k in ("labels", "radar", "badge_title"))


def _mock_menu() -> Menu:
    """构造一份「带图带价」的 mock 菜单，用于离线验证菜单解析。"""
    m = Menu()
    m.items = {
        "F1": MenuItem("F1", "我的常点堡", image="http://img/f1.png", price=15.0, original_price=20.0),
        "H1": MenuItem("H1", "人气热卖·鸡翅", image="http://img/h1.png", price=12.5),
        "H2": MenuItem("H2", "人气热卖·薯条", image="http://img/h2.png", price=9.0),
        "X1": MenuItem("X1", "人气标签·派", image="http://img/x1.png", price=6.0, tags=["人气"]),
        "N1": MenuItem("N1", "普通汉堡", image="http://img/n1.png", price=11.0),
    }
    m.frequent_code = "F1"
    m.categories = [("人气热卖", ["H1", "H2"]), ("主食", ["N1"])]
    return m


def test_menu_probe_fields():
    """菜单质量统计：款数 / 带图 / 带价 / 类目数 / 常点。"""
    m = _mock_menu()
    f = menu_probe_fields(m)
    assert f["items"] == 5
    assert f["with_image"] == 5
    assert f["with_price"] == 5
    assert f["categories"] == 2
    assert f["frequent"] == "F1"
    # 折扣派生
    it = m.items["F1"]
    assert it.discount == 5.0 and abs(it.discount_rate - 0.25) < 1e-9


def test_image_datauri_and_degrade():
    """图片工具：data-uri 自包含 + 全链路优雅降级（缺文件 / 空值 / 远程原样）。"""
    # 空值 / 远程 / 缺失文件
    assert images.to_data_uri("") == ""
    assert images.to_data_uri("https://x/y.png") == "https://x/y.png"
    assert images.to_data_uri("/no/such/file.png") == ""
    # 真实文件 → data:image/...;base64，且可被读回为数组（PNG 嵌入路径）
    import tempfile
    from pathlib import Path as _P
    with tempfile.TemporaryDirectory() as d:
        p = _P(d) / "t.png"
        try:
            from PIL import Image
            Image.new("RGB", (4, 4), (200, 30, 30)).save(p)
        except Exception:  # noqa: BLE001 —— 无 PIL 则跳过真实文件部分
            return
        uri = images.to_data_uri(str(p))
        assert uri.startswith("data:image/png;base64,"), f"应为 png data-uri，实际 {uri[:30]}"
        arr = images.load_array(str(p))
        assert arr is not None and getattr(arr, "shape", (0,))[0] == 4
    # 批量下载：非法 URL 一律跳过（不抛异常）
    assert images.download_many({"a": "", "b": "notaurl"}) == {}


def test_report_items_with_images():
    """分享卡：战报商品缩略图（Markdown 带图链接 / HTML data-uri），且不再有「本店推荐」区块。"""
    rep = load_meal_report_sample()
    assert rep is not None
    rep.items[0].image = "http://img/dish.png"          # 给战报首项配图
    a = build_archive(None, use_remote=False, order_report=rep)
    # HTML：商品缩略图出现；不再有任何推荐区块
    html = render_card_html(a)
    assert "http://img/dish.png" in html, "战报商品缩略图应出现在分享卡"
    assert "本店推荐" not in html, "推荐区块应已彻底移除"
    # Markdown：战报商品名转为带图链接
    md = render_markdown(a)
    assert "本店推荐" not in md
    assert "http://img/dish.png" in md, "Markdown 战报商品应带图链接"


def test_menu_view_render():
    """可视化菜单：卡片带 code/名/价/图，类目 chip 到位，缺图降级为占位块。"""
    m = Menu()
    m.items = {
        "A1": MenuItem("A1", "巨无霸", image="http://img/a1.png", price=26.0, original_price=30.0),
        "A2": MenuItem("A2", "无图薯条", image="", price=9.0),
    }
    m.categories = [("主食", ["A1"]), ("小食", ["A2"])]
    doc = render_menu_html("测试餐厅", "9999", m, mode="到店取餐")
    assert "<!DOCTYPE html>" in doc and 'lang="zh-CN"' in doc
    # 卡片：code / 名 / 价 / 图
    assert 'data-code="A1"' in doc and "巨无霸" in doc and "¥26.00" in doc
    assert "http://img/a1.png" in doc
    # 折扣标签（原价 30 → 省 4 元）
    assert "省¥4.00" in doc and "¥30.00" in doc
    # 类目 chip（含「其他」兜底不误伤）与统计
    assert 'data-cat="主食"' in doc and 'data-cat="小食"' in doc
    assert "在售" in doc
    # 无图商品降级为占位块（不写出空的 src）
    assert 'src=""' not in doc
    assert "mimg ph" in doc
    # 下单清单输出区（供复制给 eat --items）
    assert 'id="cart"' in doc and "复制清单" in doc
    # 一键复制点餐话术（粘贴回对话即可点单）
    assert "复制话术" in doc and "我要点：" in doc and 'id="cp"' in doc and 'id="cpc"' in doc


def test_parse_items_formats():
    """点餐清单解析：编码/名称/话术多种写法都能解析出正确数量。"""
    from src.order_text import parse_items

    def as_map(specs):
        return dict(parse_items(specs))

    assert as_map(["1440:2", "515837:1"]) == {"1440": 2, "515837": 1}
    assert as_map(["麦辣鸡腿堡:2,圆筒冰淇淋"]) == {"麦辣鸡腿堡": 2, "圆筒冰淇淋": 1}
    assert as_map(["麦辣鸡腿堡：2，圆筒冰淇淋"]) == {"麦辣鸡腿堡": 2, "圆筒冰淇淋": 1}
    # 菜单页话术：「名称×N」「名称xN」「名称 xN」「名称*N」数量不能丢
    assert as_map(["麦辣鸡腿汉堡×2", "圆筒冰淇淋×1"]) == {"麦辣鸡腿汉堡": 2, "圆筒冰淇淋": 1}
    assert as_map(["麦辣鸡腿堡 x2,巨无霸*1"]) == {"麦辣鸡腿堡": 2, "巨无霸": 1}
    # 整句话术（含开场白与「（门店，取餐方式）」括注）也能直接吃下
    sentence = "我要点：麦辣鸡腿汉堡×2、圆筒冰淇淋×1（麦当劳南京徐庄路餐厅，到店取餐）"
    assert as_map([sentence]) == {"麦辣鸡腿汉堡": 2, "圆筒冰淇淋": 1}


def test_resolve_cart():
    """名称→编码三级匹配：精确 / 子串 / 歧义拒绝 / 无匹配建议 / 编码直传。"""
    from src.order_text import AmbiguousItem, UnknownItem, resolve_cart

    m = _mock_menu()
    # 精确匹配 + 编码直传（菜单里不存在的数字编码原样入车），购物车信息齐全
    rc = resolve_cart([("人气标签·派", 2), ("515837", 1)], m)
    assert [it.product_code for it in rc.cart] == ["X1", "515837"]
    assert rc.cart[0].name == "人气标签·派" and rc.cart[0].price == 6.0
    assert rc.cart[0].quantity == 2 and rc.cart[0].image
    assert rc.notes and "X1" in rc.notes[0]
    assert rc.cart[1].quantity == 1 and not rc.cart[1].name
    # 子串匹配（唯一时自动选中）
    rc = resolve_cart([("鸡翅", 1)], m)
    assert rc.cart[0].product_code == "H1"
    # 歧义（多款命中）→ 拒绝瞎猜，带候选
    try:
        resolve_cart([("人气热卖", 1)], m)
        raise AssertionError("歧义词应抛 AmbiguousItem")
    except AmbiguousItem as e:
        assert e.key == "人气热卖"
        assert {it.code for it in e.candidates} == {"H1", "H2"}
    # 无匹配 → 抛 UnknownItem，带建议（相似度降序）
    try:
        resolve_cart([("板烧鸡腿堡", 1)], m)
        raise AssertionError("无匹配词应抛 UnknownItem")
    except UnknownItem as e:
        assert e.key == "板烧鸡腿堡"
        assert e.suggestions and len(e.suggestions) <= 5


def test_quote_mismatch_guard():
    """算价护栏：菜单名 ≠ 官方算价名 ⇒ mismatches 记录错位（防止点了 A 下单成 B）。"""
    from src.ordering import OrderingSession, quote

    class _FakeClient:
        def call_tool(self, name, arguments=None):
            return {
                "price": 1725, "originalPrice": 2300, "discount": 575,
                "takeWayList": [{"code": "1", "title": "堂食"}],
                "productList": [{"productCode": "1440", "productName": "麦辣鸡腿汉堡"}],
            }

    m = _mock_menu()
    m.items["1440"] = MenuItem("1440", "麦辣鸡腿汉堡", image="http://img/1440.png", price=23.0)
    sess = OrderingSession(store_code="1990262")
    # 一致：正常算价，名称/价/图回填到位
    q = quote(_FakeClient(), sess, [CartItem("1440")], menu=m)
    assert not q.mismatches
    assert q.paid == 17.25 and q.original == 23.0 and q.discount == 5.75
    assert q.items[0].name == "麦辣鸡腿汉堡" and q.items[0].price == 23.0
    assert q.take_way_list and q.take_way_list[0].name == "堂食"
    # 不一致：mismatches 记下（菜单名, 官方名），由 CLI 拒绝下单
    m.items["1440"] = MenuItem("1440", "酥酥多笋卷三件套", price=25.0)
    q = quote(_FakeClient(), sess, [CartItem("1440")], menu=m)
    assert q.mismatches == [("1440", "酥酥多笋卷三件套", "麦辣鸡腿汉堡")]


def test_png_cjk_font():
    """PNG 分享卡：CJK 字体探测应命中真实注册字体，渲染不报错且产出有效文件。"""
    import tempfile
    from matplotlib import font_manager

    from src.report.png import _cjk_sans_serif, render_card_png

    fonts = _cjk_sans_serif()
    assert fonts, "CJK 字体探测不应为空"
    # 探测出的字体必须真实注册在 matplotlib
    available = {f.name for f in font_manager.fontManager.ttflist}
    assert fonts[0] in available, f"{fonts[0]} 应已注册"
    # 若系统确有 CJK 字体（非 DejaVu 兜底），findfont 不应退回 DejaVu Sans
    if fonts != ["DejaVu Sans"]:
        from matplotlib.font_manager import FontProperties, findfont
        resolved = findfont(FontProperties(family=fonts[0]))
        assert "DejaVuSans" not in resolved, "应命中真实 CJK 字体而非 DejaVu 兜底"
    # 真实渲染一张 demo 卡片：不抛异常、文件存在且有内容
    a = build_archive(None, use_remote=False)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "card.png"
        ok = render_card_png(a, out)
        assert ok is not None and out.exists() and out.stat().st_size > 10_000


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n全部 {len(fns)} 项自检通过 ✅")
