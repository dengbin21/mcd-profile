"""可视化点餐菜单（menu_view）：把门店菜单渲染成「带图带价」的网页。

解决一个交互痛点：**终端 CLI 与选择卡片都渲染不了图片**，只能给 URL。
本模块把 ``query-meals`` 拿到的富菜单（117 款商品的图 + 价 + 名）
铺成一份可浏览的 HTML——支持**类目筛选 / 关键词搜索 / 点选购物车**，
点完可**一键复制「点餐话术」**（如「我要点：麦辣鸡腿汉堡×2（麦当劳××餐厅，到店取餐）」），
粘贴回 WorkBuddy 对话即可走「按名解析→算价→确认下单」；也可复制 ``code:qty``
清单交给 ``eat --items ...``。**页面负责看图挑，对话负责算价下单。**

设计：
- 图片默认直连官方 CDN（体积小）；``embed=True`` 时下载并转 ``data:`` URI 自包含。
- 缺图 / 断网优雅降级为占位块，不影响浏览与选餐。
"""
from __future__ import annotations

import html
import json

from . import images


def _card(it, embed: bool = False) -> str:
    """单个商品卡：图 + 名 + 价 + 折扣 + code。"""
    src = ""
    if it.image:
        if embed:
            src = images.to_data_uri(it.image)
        else:
            src = it.image
    img = (f'<img class="mimg" src="{html.escape(src)}" alt="" loading="lazy">' if src
           else '<div class="mimg ph">🍔</div>')
    orig = (f'<span class="morig">¥{it.original_price:.2f}</span>'
            if it.original_price and it.original_price > it.price else "")
    deal = (f'<span class="mdeal">省¥{it.discount:.2f}</span>' if it.discount else "")
    cat = html.escape(getattr(it, "category", "") or "")
    return (
        f'<div class="card" data-code="{html.escape(it.code)}" '
        f'data-name="{html.escape(it.name or "")}" data-cat="{cat}" '
        f'data-price="{it.price:.2f}">'
        f'{img}'
        f'<div class="mname">{html.escape(it.name or it.code)}</div>'
        f'<div class="mprice"><b>¥{it.price:.2f}</b>{orig}{deal}</div>'
        f'<div class="mcode">#{html.escape(it.code)}</div>'
        f'<div class="qty" hidden>'
        f'<button class="minus" type="button">−</button>'
        f'<span class="qn">1</span>'
        f'<button class="plus" type="button">＋</button></div>'
        f'</div>'
    )


def render_menu_html(store_name: str, store_code: str, menu, *,
                     mode: str = "到店取餐", embed: bool = False) -> str:
    """渲染门店菜单为完整 HTML 字符串。"""
    in_cat = {c for _, codes in menu.categories for c in codes}
    groups = list(menu.categories)
    others = [it.code for it in menu.items.values() if it.code not in in_cat and it.name]
    if others:
        groups.append(("其他", others))

    # 类目筛选 chips
    chips = ['<button class="chip on" data-cat="all" type="button">全部</button>']
    sections = []
    total = 0
    for cname, codes in groups:
        rows = [menu.items[c] for c in codes if c in menu.items and menu.items[c].name]
        if not rows:
            continue
        total += len(rows)
        chips.append(f'<button class="chip" data-cat="{html.escape(cname)}" type="button">'
                     f'{html.escape(cname)} <i>{len(rows)}</i></button>')
        sections.append(f'<div class="grid">{"".join(_card(it, embed) for it in rows)}</div>')

    with_img = sum(1 for it in menu.items.values() if it.image)
    with_price = sum(1 for it in menu.items.values() if it.price)

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(store_name)} · 可视化菜单</title>
<style>
:root{{--bg:#0E0C08;--bg2:#1C170E;--panel:rgba(255,255,255,.04);
  --ink:#F6F4EF;--muted:#98938B;--primary:#FFC72C;--accent:#DA291C;}}
*{{box-sizing:border-box;}}
body{{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#241A06,var(--bg) 60%);
  color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;}}
.wrap{{max-width:1080px;margin:0 auto;padding:22px 18px 120px;}}
header h1{{margin:0 0 2px;font-size:22px;}}
header .sub{{color:var(--muted);font-size:12.5px;}}
.kpis{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 6px;}}
.kpi{{background:var(--panel);border:1px solid rgba(255,255,255,.08);border-radius:12px;
  padding:8px 12px;font-size:12.5px;}}
.kpi b{{color:var(--primary);font-size:15px;}}
.bar{{position:sticky;top:0;z-index:9;display:flex;gap:10px;flex-wrap:wrap;align-items:center;
  padding:12px 0;background:linear-gradient(180deg,var(--bg) 70%,transparent);}}
#q{{flex:1;min-width:180px;background:var(--panel);border:1px solid rgba(255,255,255,.12);
  border-radius:10px;color:var(--ink);padding:9px 12px;outline:none;}}
#q::placeholder{{color:var(--muted);}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;}}
.chip{{background:var(--panel);border:1px solid rgba(255,255,255,.12);color:var(--ink);
  border-radius:999px;padding:6px 12px;font-size:12.5px;cursor:pointer;transition:.15s;}}
.chip i{{color:var(--muted);font-style:normal;font-size:11px;}}
.chip:hover{{border-color:var(--primary);}}
.chip.on{{background:var(--primary);color:#1a1200;border-color:var(--primary);font-weight:700;}}
.chip.on i{{color:#5c4a00;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:14px;margin:14px 0 26px;}}
.card{{position:relative;background:var(--panel);border:1px solid rgba(255,255,255,.09);
  border-radius:14px;padding:10px;cursor:pointer;transition:.15s;}}
.card:hover{{border-color:rgba(255,199,44,.55);transform:translateY(-2px);}}
.card.sel{{border-color:var(--primary);box-shadow:0 0 0 2px rgba(255,199,44,.35) inset;}}
.mimg{{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:10px;background:rgba(255,255,255,.05);}}
.mimg.ph{{display:flex;align-items:center;justify-content:center;font-size:34px;}}
.mname{{font-size:13px;margin-top:8px;line-height:1.35;height:36px;overflow:hidden;}}
.mprice{{margin-top:4px;display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;}}
.mprice b{{color:var(--primary);font-size:15px;}}
.morig{{color:var(--muted);text-decoration:line-through;font-size:11.5px;}}
.mdeal{{background:rgba(218,41,28,.18);color:#FF7A6B;border-radius:6px;padding:1px 5px;font-size:10.5px;}}
.mcode{{color:var(--muted);font-size:10px;margin-top:5px;}}
.qty{{display:flex;align-items:center;gap:8px;margin-top:8px;justify-content:center;
  background:rgba(0,0,0,.28);border-radius:9px;padding:4px;}}
.qty button{{width:26px;height:26px;border-radius:7px;border:0;background:var(--primary);
  color:#1a1200;font-size:16px;font-weight:800;cursor:pointer;line-height:1;}}
.qty .qn{{min-width:22px;text-align:center;font-weight:700;}}
.dock{{position:fixed;left:0;right:0;bottom:0;background:rgba(14,12,8,.94);
  border-top:1px solid rgba(255,255,255,.12);backdrop-filter:blur(10px);}}
.dock .inner{{max-width:1080px;margin:0 auto;padding:10px 18px;display:flex;gap:12px;align-items:center;}}
.dock .cnt{{font-size:13px;color:var(--muted);white-space:nowrap;}}
.dock .cnt b{{color:var(--primary);}}
#cart{{flex:1;background:var(--panel);border:1px solid rgba(255,255,255,.1);border-radius:9px;
  color:var(--ink);padding:8px 10px;font:12px ui-monospace,Menlo,monospace;min-height:36px;resize:none;}}
.copy{{background:var(--accent);color:#fff;border:0;border-radius:9px;padding:9px 16px;
  font-weight:700;cursor:pointer;white-space:nowrap;}}
.copy:hover{{filter:brightness(1.1);}}
.copy.alt{{background:var(--panel);border:1px solid rgba(255,255,255,.15);color:var(--muted);font-weight:500;}}
.copy.alt:hover{{color:var(--ink);}}
.empty{{color:var(--muted);text-align:center;padding:40px;}}
</style></head>
<body><div class="wrap">
<header>
  <h1>{html.escape(store_name)} <span style="color:var(--muted);font-size:14px;">· {html.escape(mode)}</span></h1>
  <div class="sub">门店 code：{html.escape(store_code)}　·　数据来自麦当劳官方 MCP <code>query-meals</code></div>
  <div class="kpis">
    <div class="kpi">在售 <b>{total}</b> 款</div>
    <div class="kpi">带图 <b>{with_img}</b></div>
    <div class="kpi">带价 <b>{with_price}</b></div>
    <div class="kpi">类目 <b>{len([g for g in groups])}</b></div>
  </div>
</header>

<div class="bar">
  <input id="q" placeholder="搜索商品名 / code…">
  <div class="chips">{''.join(chips)}</div>
</div>

<div class="empty" id="none" hidden>没有匹配的商品</div>
{''.join(sections)}
</div>

<div class="dock"><div class="inner">
  <div class="cnt">已选 <b id="n">0</b> 件　<span style="opacity:.7">点卡片选择，±调数量</span></div>
  <textarea id="cart" readonly placeholder="选好后这里会出现点餐话术，一键复制粘贴回对话即可点单"></textarea>
  <button class="copy" id="cp" type="button">复制话术</button>
  <button class="copy alt" id="cpc" type="button">复制清单</button>
</div></div>

<script>
const cards=[...document.querySelectorAll('.card')];
const sel={{}};
const $=s=>document.querySelector(s);
const STORE={json.dumps(store_name, ensure_ascii=False)};
const MODE={json.dumps(mode, ensure_ascii=False)};
const names={{}};
cards.forEach(c=>names[c.dataset.code]=c.dataset.name);
let rawList='';
function applyFilter(){{
  const cat=document.querySelector('.chip.on').dataset.cat;
  const q=($('#q').value||'').trim().toLowerCase();
  let shown=0;
  cards.forEach(c=>{{
    const okCat=(cat==='all'||c.dataset.cat===cat);
    const okQ=!q||c.dataset.name.toLowerCase().includes(q)||c.dataset.code.includes(q);
    const ok=okCat&&okQ; c.style.display=ok?'':'none'; if(ok)shown++;
  }});
  $('#none').hidden=shown>0;
}}
function sentence(){{
  const parts=Object.entries(sel).map(([code,v])=>names[code]+'×'+v.qty);
  if(!parts.length)return '';
  return '我要点：'+parts.join('、')+'（'+STORE+'，'+MODE+'）';
}}
function sync(){{
  let n=0,lines=[];
  Object.entries(sel).forEach(([code,v])=>{{n+=v.qty;lines.push(code+':'+v.qty);}});
  $('#n').textContent=n;
  rawList=lines.join(' ');
  $('#cart').value=sentence();
}}
cards.forEach(c=>{{
  const code=c.dataset.code;
  c.querySelector('.qty').addEventListener('click',e=>e.stopPropagation());
  c.addEventListener('click',()=>{{
    if(!sel[code]) sel[code]={{qty:1}};
    c.classList.add('sel');
    c.querySelector('.qty').hidden=false;
    c.querySelector('.qn').textContent=sel[code].qty;
    sync();
  }});
  c.querySelector('.minus').addEventListener('click',()=>{{
    if(!sel[code])return;
    sel[code].qty--; 
    if(sel[code].qty<=0){{delete sel[code];c.classList.remove('sel');c.querySelector('.qty').hidden=true;}}
    else c.querySelector('.qn').textContent=sel[code].qty;
    sync();
  }});
  c.querySelector('.plus').addEventListener('click',()=>{{
    if(!sel[code])return;
    sel[code].qty++; c.querySelector('.qn').textContent=sel[code].qty; sync();
  }});
}});
document.querySelectorAll('.chip').forEach(ch=>ch.addEventListener('click',()=>{{
  document.querySelectorAll('.chip').forEach(x=>x.classList.remove('on'));
  ch.classList.add('on'); applyFilter();
}}));
$('#q').addEventListener('input',applyFilter);
function bindCopy(btn, getText, label){{
  btn.addEventListener('click',async()=>{{
    const t=getText(); if(!t)return;
    try{{await navigator.clipboard.writeText(t);btn.textContent='已复制 ✓';
      setTimeout(()=>btn.textContent=label,1400);}}catch(e){{$('#cart').select();}}
  }});
}}
bindCopy($('#cp'),()=>$('#cart').value||'','复制话术');
bindCopy($('#cpc'),()=>rawList,'复制清单');
</script>
</body></html>
"""
