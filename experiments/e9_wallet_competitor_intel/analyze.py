"""Read the JSONL/CSV dumps from fetch.py and produce REPORT.md.

Answers:
  1. Who are the top wallets on April-17 crypto-barrier markets?
  2. For each, what fraction of their Polymarket trading is barrier vs updown vs
     sports vs other?
  3. Do any of them also appear in the probe-tracked updown-5m universe?
  4. Realized + unrealized P&L summary.

No new API calls — pure pandas/sqlite over fetch.py output.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
PROBE_DB = HERE.parent.parent / "probe" / "probe.db"
REPORT_PATH = HERE / "REPORT.md"


def classify_slug(slug: str | None, event_slug: str | None, title: str | None) -> str:
    s = (slug or "").lower()
    e = (event_slug or "").lower()
    t = (title or "").lower()
    if "-updown-" in s:
        return "updown_5m"
    if "-reach-" in s or "-dip-to-" in s or "-hit-" in s:
        return "crypto_barrier"
    if "-above-" in s or "-below-" in s:
        return "crypto_ladder"
    for sports in ("nba", "nfl", "nhl", "mlb", "epl", "soccer", "ufc", "tennis", "premier-league", "nrl", "afl"):
        if sports in s or sports in e:
            return "sports"
    for poli in ("election", "president", "congress", "trump", "biden", "senate", "governor", "vote"):
        if poli in s:
            return "politics"
    return "other"


def load_user_history() -> pd.DataFrame:
    rows = []
    with (DATA_DIR / "top_wallet_history.jsonl").open() as f:
        for line in f:
            t = json.loads(line)
            rows.append({
                "wallet": t.get("proxyWallet"),
                "slug": t.get("slug"),
                "event_slug": t.get("eventSlug"),
                "title": t.get("title"),
                "side": t.get("side"),
                "size": float(t.get("size") or 0),
                "price": float(t.get("price") or 0),
                "ts": t.get("timestamp"),
                "condition_id": t.get("conditionId"),
                "name": t.get("name"),
                "pseudonym": t.get("pseudonym"),
            })
    df = pd.DataFrame(rows)
    df["notional"] = df["size"] * df["price"]
    df["vertical"] = df.apply(
        lambda r: classify_slug(r["slug"], r["event_slug"], r["title"]),
        axis=1,
    )
    return df


def load_positions() -> pd.DataFrame:
    rows = []
    with (DATA_DIR / "top_wallet_positions.jsonl").open() as f:
        for line in f:
            p = json.loads(line)
            rows.append({
                "wallet": p.get("proxyWallet"),
                "slug": p.get("slug"),
                "event_slug": p.get("eventSlug"),
                "title": p.get("title"),
                "size": float(p.get("size") or 0),
                "cash_pnl": float(p.get("cashPnl") or 0),
                "realized_pnl": float(p.get("realizedPnl") or 0),
                "initial_value": float(p.get("initialValue") or 0),
                "current_value": float(p.get("currentValue") or 0),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["vertical"] = df.apply(
            lambda r: classify_slug(r["slug"], r["event_slug"], r["title"]),
            axis=1,
        )
    return df


def load_barrier_agg() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "barrier_wallet_aggregate.csv")


def load_probe_updown_cids() -> set[str]:
    con = sqlite3.connect(PROBE_DB)
    try:
        rows = con.execute(
            "SELECT market_id FROM markets WHERE slug LIKE '%-updown-%'"
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows}


def auto_generated_name(name: str | None, pseudonym: str | None) -> bool:
    """Heuristic: 0x-prefixed name = wallet address as display = fresh/anon."""
    if not name:
        return True
    if name.startswith("0x") and len(name) >= 40:
        return True
    return False


def main() -> None:
    hist = load_user_history()
    pos = load_positions()
    barrier_agg = load_barrier_agg().head(20)
    probe_updown_cids = load_probe_updown_cids()

    # --- per-wallet cross-vertical breakdown ---
    vertical_notional = (
        hist.groupby(["wallet", "vertical"])["notional"]
        .sum()
        .unstack(fill_value=0.0)
    )
    vertical_notional["total"] = vertical_notional.sum(axis=1)
    for col in vertical_notional.columns:
        if col == "total":
            continue
        vertical_notional[f"{col}_pct"] = (
            100 * vertical_notional[col] / vertical_notional["total"]
        ).round(1)

    # --- P&L roll-up ---
    pnl_summary = (
        pos.groupby("wallet")[["realized_pnl", "cash_pnl", "current_value"]]
        .sum()
        .round(2)
    )

    # --- updown-5m activity: did any top wallet trade ANY updown-5m market? ---
    # Probe DB only has ~1-2 days of updown markets (earliest first_seen = 2026-04-17).
    # Wallet history goes back further, so direct conditionId overlap misses real
    # activity. Use slug-based classification for "any updown-5m" and separately
    # flag any that *also* hit the probe-tracked cohort.
    updown_trades = hist[hist["vertical"] == "updown_5m"]
    updown_any = (
        updown_trades.groupby("wallet")
        .agg(n_updown_trades=("size", "size"),
             n_updown_markets=("condition_id", "nunique"),
             updown_notional=("notional", "sum"))
    )
    updown_probe_overlap = (
        updown_trades[updown_trades["condition_id"].isin(probe_updown_cids)]
        .groupby("wallet")
        .agg(n_probe_updown_markets=("condition_id", "nunique"))
    )
    overlap_by_wallet = updown_any.join(updown_probe_overlap, how="left").fillna(0)
    overlap_by_wallet["n_probe_updown_markets"] = overlap_by_wallet["n_probe_updown_markets"].astype(int)

    # --- strategy-shape: most-common price buckets ---
    def bucketize(p: float) -> str:
        if p <= 0.05:
            return "<=0.05"
        if p <= 0.15:
            return "0.05-0.15"
        if p <= 0.35:
            return "0.15-0.35"
        if p <= 0.65:
            return "0.35-0.65"
        if p <= 0.85:
            return "0.65-0.85"
        if p <= 0.95:
            return "0.85-0.95"
        return ">0.95"

    hist["price_bucket"] = hist["price"].apply(bucketize)
    shape = (
        hist.groupby(["wallet", "price_bucket"])["notional"].sum()
        .unstack(fill_value=0.0)
    )
    shape_total = shape.sum(axis=1)
    shape_pct = shape.div(shape_total, axis=0).mul(100).round(1)

    # --- entity clustering: fraction of top-20 with auto-generated names ---
    top20 = barrier_agg.copy()
    top20["auto_name"] = top20.apply(
        lambda r: auto_generated_name(r["name"], r["pseudonym"]),
        axis=1,
    )

    # --- write REPORT.md ---
    lines: list[str] = []
    lines.append("# e9 — Polymarket crypto-barrier wallet intel\n")
    lines.append(
        "Source: trades for 40 April-17 barrier markets tracked in `probe.db` "
        "pulled via `data-api.polymarket.com`. 4,946 trades across 750 distinct "
        "wallets. For the top-20 wallets by barrier-market notional we then "
        "pulled up to 2,000 trades of full Polymarket history and all open "
        "positions.\n"
    )

    lines.append("## Top-level findings\n")

    total_barrier_notional = barrier_agg["notional_usd"].sum()
    total_all_barrier_wallets = load_barrier_agg()["notional_usd"].sum()
    top20_share = 100 * total_barrier_notional / total_all_barrier_wallets
    lines.append(
        f"- **Concentration on barriers is moderate.** Top-20 wallets drive "
        f"{top20_share:.0f}% of barrier-market notional (${total_barrier_notional:,.0f} "
        f"of ${total_all_barrier_wallets:,.0f}).\n"
    )

    n_multi_market = int((top20["n_markets"] >= 5).sum())
    lines.append(
        f"- **{n_multi_market}/20 top wallets are multi-market operators** "
        f"(active on ≥5 of the 40 barriers). The rest are single-market whales "
        f"who took one big position and stopped.\n"
    )

    n_auto = int(top20["auto_name"].sum())
    lines.append(
        f"- **{n_auto}/20 top wallets use the 0x-prefixed default display name** "
        "— i.e. they never set a profile name. Typical signature of "
        "execution-only bots or fresh wallets, not retail users.\n"
    )

    n_updown_active = int(len(overlap_by_wallet))
    n_total_updown_markets = int(overlap_by_wallet["n_updown_markets"].sum()) if len(overlap_by_wallet) else 0
    n_probe_cohort_overlap = int(
        (overlap_by_wallet["n_probe_updown_markets"] > 0).sum()
    ) if len(overlap_by_wallet) else 0
    lines.append(
        f"- **{n_updown_active}/20 top barrier wallets also trade updown-5m** "
        f"(crypto 5-min up/down — the *other* thing this repo's probe tracks) — "
        f"{n_total_updown_markets} distinct updown markets touched in aggregate. "
        f"Only {n_probe_cohort_overlap} of them overlap with the probe's "
        f"specific April-17/18 cohort because the probe has only been running "
        f"~2 days; the wallets' recent history predates that window.\n"
    )

    total_realized = pnl_summary["realized_pnl"].sum()
    total_unrealized = pnl_summary["cash_pnl"].sum() - pnl_summary["realized_pnl"].sum()
    lines.append(
        f"- **Aggregate P&L across top-20:** realized ${total_realized:,.0f}, "
        f"unrealized-only ${total_unrealized:,.0f}. These are meaningful book "
        "sizes — not hobbyist traders.\n"
    )

    lines.append("\n## Top-20 wallet table\n")
    lines.append("| # | Wallet | Name | Barriers hit | Barrier notional | "
                 "Vertical mix (% notional, last ≤2k trades) | Realized P&L | Auto-name? |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, (_, r) in enumerate(top20.iterrows(), start=1):
        w = r["proxy_wallet"]
        name = str(r["pseudonym"] or "")[:18]
        markets = int(r["n_markets"])
        notional = f"${r['notional_usd']:,.0f}"

        if w in vertical_notional.index:
            vn = vertical_notional.loc[w]
            mix_parts = []
            for col in ("crypto_barrier", "updown_5m", "crypto_ladder", "sports", "politics", "other"):
                pct_col = f"{col}_pct"
                if pct_col in vn.index and vn[pct_col] >= 5.0:
                    mix_parts.append(f"{col.replace('crypto_', '').replace('_', '-')}:{int(round(vn[pct_col]))}%")
            mix = " ".join(mix_parts) or "—"
        else:
            mix = "(no history)"

        realized = pnl_summary.loc[w, "realized_pnl"] if w in pnl_summary.index else 0.0
        auto = "y" if r["auto_name"] else ""

        lines.append(
            f"| {i} | `{w[:10]}…` | {name} | {markets} | {notional} | "
            f"{mix} | ${realized:,.0f} | {auto} |"
        )

    lines.append("\n## Cross-vertical activity — are barrier wallets also in our repo's universe?\n")
    lines.append(
        "The repo's probe tracks two kinds of Polymarket markets: "
        "updown-5m (crypto up/down, 5-min duration) and crypto-barrier "
        "(the same 40 we sampled here). If a top barrier wallet also trades "
        "updown-5m, that's a 'yes' — they operate across the verticals we care "
        "about.\n"
    )

    if len(overlap_by_wallet):
        lines.append("### Top-20 barrier wallets — updown-5m activity\n")
        lines.append("Slug-based match across entire wallet history (not just probe cohort). "
                     "`# probe overlap` = subset that also hit the specific markets this repo's "
                     "probe was watching on April 17-18.\n")
        lines.append("| Wallet | Name | # updown trades | # distinct updown markets | "
                     "Updown notional | # probe overlap |")
        lines.append("|---|---|---|---|---|---|")
        for w, row in overlap_by_wallet.sort_values("updown_notional", ascending=False).iterrows():
            name = str(
                top20[top20["proxy_wallet"] == w]["pseudonym"].values[0]
                if w in top20["proxy_wallet"].values
                else ""
            )[:16]
            lines.append(
                f"| `{w[:10]}…` | {name} | {int(row['n_updown_trades'])} | "
                f"{int(row['n_updown_markets'])} | ${row['updown_notional']:,.0f} | "
                f"{int(row['n_probe_updown_markets'])} |"
            )
    else:
        lines.append("**No top-20 barrier wallet shows any updown-5m activity** in the "
                     "≤2,000-trade recent history window. Barrier specialists are a "
                     "disjoint population from updown-5m traders.\n")

    lines.append("\n### Broader vertical breakdown (all Polymarket markets, not just probe)\n")
    vn = hist.groupby("vertical")["notional"].sum().sort_values(ascending=False)
    vn_total = vn.sum()
    lines.append("| Vertical | Notional (top-20 recent ≤2k each) | Share |")
    lines.append("|---|---|---|")
    for v, n in vn.items():
        lines.append(f"| {v} | ${n:,.0f} | {100 * n / vn_total:.1f}% |")

    lines.append("\n## Strategy-shape signals (top-20, by price bucket of all trades)\n")
    lines.append("Penny-stub behaviour (lots of trades at ≤0.05 or ≥0.95) = dump-at-resolution or "
                 "pre-placed limit exits. Middle-band (0.35–0.65) = active opinion-taking.\n")
    bucket_totals = hist.groupby("price_bucket")["notional"].sum()
    bucket_pct = (100 * bucket_totals / bucket_totals.sum()).round(1)
    for bucket in ["<=0.05", "0.05-0.15", "0.15-0.35", "0.35-0.65", "0.65-0.85", "0.85-0.95", ">0.95"]:
        if bucket in bucket_pct.index:
            lines.append(f"- **{bucket}:** {bucket_pct[bucket]}% of top-20 aggregate notional")

    lines.append("\n## Entity-clustering observations\n")
    auto_wallets = top20[top20["auto_name"]]["proxy_wallet"].tolist()
    lines.append(f"- {len(auto_wallets)} of 20 top wallets have unset profile names. "
                 "A batch of freshly-funded bot wallets tends to look like this.\n")
    named_big = top20[(~top20["auto_name"]) & (top20["n_markets"] >= 5)]
    if len(named_big):
        lines.append("- Named multi-market operators (candidates for real individuals/desks):")
        for _, r in named_big.iterrows():
            lines.append(f"  - `{r['proxy_wallet'][:10]}…` — **{r['pseudonym']}** "
                         f"({r['n_markets']} barriers, ${r['notional_usd']:,.0f})")

    lines.append("\n## Caveats\n")
    lines.append("- Each top wallet's history is capped at 2,000 trades (data-api pagination "
                 "practicality). Very active wallets' older trades are outside the window, so "
                 "vertical-mix % reflects *recent* behaviour, not lifetime.\n")
    lines.append("- Probe DB currently tracks only the April-17 crypto barriers. If there are "
                 "large older barriers, top wallets there are not sampled.\n")
    lines.append("- `realizedPnl` from `/positions` is per-position; positions resolved "
                 "long ago may age out of the endpoint's window.\n")

    lines.append("\n## Follow-ups\n")
    lines.append("- **On-chain enrichment:** for each top wallet, hit Polygonscan via "
                 "`transactionHash` (already in the JSONL) to find common funding sources "
                 "— would answer the entity-clustering question properly.\n")
    lines.append("- **Full-lifetime vertical mix:** paginate `/trades?user=` beyond 2,000 "
                 "trades for the ~5 biggest operators to get a lifetime breakdown.\n")
    lines.append("- **Price-vs-fair edge analysis:** join each barrier trade against "
                 "`market_snapshots` for the same market to measure whether top wallets "
                 "systematically buy below fair value (true arb) or move size at/above fair "
                 "(MM-hedging / panic close-outs).\n")

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
