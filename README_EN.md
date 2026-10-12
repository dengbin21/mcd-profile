# McProfile · McDonald's Agent Skill

[中文](./README.md) | [English](./README_EN.md)

![tests](https://github.com/dengbin21/mcd-profile/actions/workflows/tests.yml/badge.svg)
![license](https://img.shields.io/github/license/dengbin21/mcd-profile)
![python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)

> **Before you eat, order every meal for the least money; after you eat, get a McPersona card you can show off.**
>
> Tell your AI agent "I want a McChicken, how do I order it to save the most?" and it enumerates
> thousands of combinations, has each one **verified against the official McDonald's `calculate-price`
> API**, and returns an **S/A/B/C-rated optimal solution + a shareable report card** — all read-only,
> **no order is placed, not a single cent is spent**.
>
> After you eat, ask "what's my McPersona" — every order becomes a **one-of-a-kind McPersona card**:
> the same profile renders a different poster for different people.
>
> And ask "when do my coupons expire" — it doesn't just tell you whether they'll survive the next
> campaign; it tells you **what the expiring ones are worth: money you're silently throwing away**.

This is an **Agent Skill**: `SKILL.md` defines the workflow and triggers, while the **deterministic
algorithms live in the bundled `src/` code** (coupon parsing / combo enumeration / rating / date
parsing / 6-dimension portrait / persona detection / coupon value lookup), which your **host AI agent**
(WorkBuddy / Codex / any client that supports Skills + MCP) **reuses instead of re-implementing on
every session**. All data comes from the official McDonald's MCP (`mcd-mcp`, 20 read-only tools).
Which means:

- **One directory to install**: drop this package (`SKILL.md` + `src/`) into your client's skills
  directory and it works — no extra Python setup needed;
- The algorithms are implemented and covered by **106 offline self-tests** — reproducible and reliable;
- Read-only first: solving / preheating / archiving only call query tools — no coupon claiming, no
  lottery, no ordering;
- The only write operation, `create-order`, is an **optional ordering loop, off by default**, and
  requires explicit confirmation.

⭐ **Liked it? A star is the biggest support → [github.com/dengbin21/mcd-profile](https://github.com/dengbin21/mcd-profile)**

![Demo — McPersona card (vertical long image)](./docs/demo-card.png)

---

## Why it's different

| # | Selling point | Why it's different |
|---|---|---|
| 1 | **McPersona card (the signature)** | After you eat, you get a shareable card: persona detection + one-of-a-kind themes — the same profile renders a **different poster for different people**. "Before-eating" tools all save money; we also give you emotional value "after eating" |
| 2 | **Prices verified by the official API, never guessed** | Enumeration and pricing are strictly separated: every candidate combo is sent to the official `calculate-price` to get the **real amount payable**; local estimation is used only for ranking — the architecture makes it impossible for the model to invent prices |
| 3 | **Gut vs. optimum + S/A/B/C rating** | Not just the answer, but "where your instinct lost, and what ¥0.4 extra buys you" — educative + persuasive; others only give "recommended vs. alternatives" |
| 4 | **Silent cost: what expiring coupons are worth** | Each coupon's face value is **looked up from the menu** (threshold = discount / fixed-price = original − price / buy-one-get-one & free = item price), summed as "you have N coupons expiring in 30 days worth ¥Y — not using them is throwing money away"; unparsable coupons are counted as 0 and disclosed, **never fabricated** |
| 5 | **Budget × calorie dual constraints** | One sentence satisfies both "stay under budget" and "stay under calorie limit"; calories are matched against the official nutrition database with honest coverage reporting — unmatchable items are treated as a lower bound, never wrongly killed |
| 6 | **Algorithm-backed, reproducible results** | Coupon parsing / enumeration / rating / dates / portrait / persona / coupon value are implemented in `src/` with 106 offline self-tests — the host agent reuses them instead of re-writing each session; read-only first, the only write `create-order` is off by default and needs explicit confirmation |

---

## Quick start (2 steps)

1. **Install the package**: drop this repo (`SKILL.md` + `src/` algorithm code) into your client's
   (WorkBuddy / Codex etc.) skills directory — the host agent will reuse the deterministic
   algorithms in `src/`; no extra Python setup needed.
2. **Configure the official McDonald's MCP** (one-time): get a Token at
   **https://open.mcd.cn/mcp**, then add an entry to your client's MCP config (WorkBuddy
   `~/.workbuddy/mcp.json` example):

   ```json
   {
     "mcpServers": {
       "mcd-mcp": {
         "type": "streamablehttp",
         "url": "https://mcp.mcd.cn",
         "headers": { "Authorization": "Bearer <your-real-token>" }
       }
     }
   }
   ```

   ⚠️ The token must be real; restart the client and confirm `mcd-mcp` is connected (i.e. the tool
   list shows `calculate-price`).

3. **Just talk normally.** Once the host agent reads `SKILL.md` it knows which tools to call:

| You say | Which path |
|---|---|
| "How do I order this cheapest" / "I want X, how to save" | **McSolve**: `query-meals` + `calculate-price` ×30 verified orders |
| "When do my coupons expire" / "Will they survive the campaign" | **McPreheat**: `campaign-calendar` × coupon expiry |
| "How much did I spend/save at McDonald's" / "What's my McPersona" | **archive**: `order-list` → 6-dimension portrait + persona card |
| "Order me a…" | Ordering loop (dry-run by default, needs explicit confirmation) |

## The three signature plays

### ① McSolve · the "McOptimal" solver (before eating)

Treat the official `calculate-price` as a **price oracle** and call it repeatedly:

```
query-meals            full menu (with images and prices)
query-my-coupons       coupons you hold (with expiry)
query-store-coupons    store campaign coupons
available-coupons      claimable "McSave" coupons
        ↓   local pruning by coupon thresholds, enumerating candidate combos
calculate-price × 30   official price verification per order     ★ engine
list-nutrition-foods   nutrition for the optimal solution
```

- The primary metric is **savings rate**, not lowest amount payable — otherwise the solver degrades
  into "persuading you to order less";
- Local estimation is only for ranking; **the final price always comes from official verification**;
- Supports **budget × calorie dual constraints** (one sentence caps both payable and calories);
- Outputs "your gut order vs. algorithm optimum" comparison + S/A/B/C rating + report long-image.

### ② McPreheat · the preheat desk (before eating)

Cross the official campaign calendar with **your coupons' expiry dates**:

> 7 days until "Autumn limited-edition new product launch" — but you have 1 coupon expiring in
> 3 days. **That coupon won't survive until then.**

- Conflicts are **computed** (coupon expiry < campaign start), not copywritten;
- Outputs countdown + conflict list + readiness score S/A/B/C + preheat card.

### ③ archive · 6-dimension review + McPersona card (after eating)

Translate your order history into a personal profile you can read and share:

- Spend / Savings / Health / Habits / Benefits / Campaigns — **six portraits**;
- **McPersona** + one-of-a-kind themes (colors/badges/one-liners): the same profile renders a
  different poster for different people;
- Also outputs an **MCP tool coverage list**, making "how much MCP capability was used" visible.

## McDonald's MCP capabilities used (20 read-only + 1 optional write)

| Domain | Tools |
|---|---|
| Orders | `order-list`, `query-order` |
| Benefits | `query-my-account`, `query-my-coupons`, `query-my-prizes`, `query-lottery-info`, `available-coupons` |
| Mall | `mall-order-list`, `mall-order-detail`, `mall-points-products` |
| Scenario | `query-nearby-stores`, `delivery-query-addresses`, `delivery-query-stores`, `query-meals`, `query-meal-detail`, `query-store-coupons`, `calculate-price` |
| Marketing | `campaign-calendar`, `now-time-info` |
| Nutrition | `list-nutrition-foods` |
| **Ordering (optional write)** | `create-order` — only on explicit user confirmation |

> **Deliberately unused**: `cancel-order` / `mall-create-order` / `party-order-create` /
> `auto-bind-coupons` / `draw-lottery` / `delivery-create-address` etc.
> Detailed call flows, fields and business value: **[MCP_INTEGRATION.md](./MCP_INTEGRATION.md)**.

## Safety

- **Read-only first**: solving / preheating / archiving only call query tools; `calculate-price`
  verification places no order.
- **Ordering is the only write operation and is off by default**: no `create-order` before explicit
  confirmation — only a price preview; before placing an order, list store/items/amount payable;
  keep the `orderId` after a successful order so it can be reversed.
- **Honest scope**: `order-list` returns only the latest ~10 orders, positioned as "review" not
  "annual statement"; coupon redemption usually requires the coupon-bound product code (the official
  wallet API does not return it), so pricing follows the coupon price the official API auto-matches
  per account — this is explicitly disclosed in the online report.
- **Privacy**: the token lives only in your client's MCP config — never in logs, never in outputs.
- **Disclaimer**: conclusions are for personal review only, not medical or nutritional advice.

## Repo layout

```
mcd-profile/
├── 📦 SKILL.md              ★ Skill core (triggers / plays / tool mapping / safety) — the "brain" for the host agent
├── 📦 src/                  ★ Skill core: deterministic algorithm code (reused by the host agent)
│   ├── solver.py            McSolve: coupon parsing / enumeration pruning / selection / rating
│   ├── preheat.py           McPreheat: date parsing / conflict detection / readiness scoring
│   ├── analysis.py          archive 6-dimension portrait
│   ├── persona.py           McPersona detection (with no-order fallback)
│   ├── nutrition.py         nutrition matching
│   ├── models.py            domain models + response parsing + unit conversion
│   └── ...(rendering / copy layer, for verification & output generation)
├── 📦 data/                 Skill core: anonymized samples (offline fallback / reproducibility)
├── 📦 assets/               Skill core: image assets (assets/logo.png brand logo)
│
├── tests/                   Project docs: 103 offline self-tests (algorithm reliability)
├── README.md / README_EN.md   Project docs: usage (Chinese / English)
├── MCP_INTEGRATION.md       Project docs: McDonald's MCP integration reference
├── CONTEST_DECLARATION.md   Project docs: contest declaration
├── workbuddy.md             Project docs: WorkBuddy dev context (contest verification)
├── LICENSE                  Project metadata
└── docs/demo-card.png       Project docs: README hero image
```

> **Skill core** (all you need to install into WorkBuddy): `SKILL.md` + `src/` + `data/` + `assets/` —
> a standard skill package: one directory, `SKILL.md` definition, resources in subdirectories,
> self-contained. **Everything else is project documentation**, irrelevant to running the skill.

> Architecture: `SKILL.md` describes the workflow; **deterministic logic (coupon parsing /
> enumeration / rating / dates / portrait / persona) is carried by the `src/` code** — the host agent
> reuses those functions instead of re-implementing them every session, so results are reproducible.
> To run the code, read the matching file under `src/` and execute it in your tool environment;
> the 103 self-tests can be verified with `python -m pytest tests/ -q`.

## License

MIT.

> Disclaimer: this is a personal contest entry and is not affiliated with McDonald's.
