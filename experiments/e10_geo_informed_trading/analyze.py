"""Offline analysis over e10.db: coverage + candidate pre-news move detection.

Run once after the watcher has been collecting for >= 24h (ideally 48h).
Produces REPORT.md and populates the flagged_events table.

Framing rule: if candidate/control flag-rate ratio < 1.5×, the report verdict
is "null result — no signal distinguishable from control noise". No event is
ever described as "suspicious" or "consistent with informed trading". The
strongest allowed phrasing is "unexplained by our monitored feed set".

Manual-review rubric: see MANUAL_REVIEW_RUBRIC.md. Pre-committed disqualifier
checklist must be applied before any flag earns the `unexplained-by-monitored-feeds`
verdict.

Run:
    uv run python experiments/e10_geo_informed_trading/analyze.py
    uv run python experiments/e10_geo_informed_trading/analyze.py --coverage-only
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).parent
DEFAULT_DB = HERE / "e10.db"
REPORT = HERE / "REPORT.md"
FEEDS_YAML = HERE / "feeds.yaml"

# Detection parameters (documented in README.md).
WINDOW_MIN = 10
MIN_VOLUME_DELTA_USD = 500
Z_THRESHOLD = 3.0
FEED_SILENT_HARD_MINUTES = 180          # full exclusion if relevant feed silent this long at event start
FEED_SILENT_SOFT_MINUTES = 60           # ⚠️ low-confidence mark if any relevant feed silent >this in window
NEWS_LOOKBACK_MIN = 60
CO_MOVEMENT_Z_THRESHOLD = 1.0
MIN_SNAPSHOT_SPAN_HOURS = 6

# Ratio → verdict language. Pre-committed; don't tune after seeing data.
VERDICT_THRESHOLDS = [
    (1.0, "null result — control flags at or above candidate rate"),
    (1.5, "null result — no signal distinguishable from control noise"),
    (3.0, "weak signal; individual events may or may not survive the manual review rubric"),
    (float("inf"),
     "candidate signal above control baseline; apply decision gate from README "
     "and the disqualifier checklist from MANUAL_REVIEW_RUBRIC.md to top events"),
]


FLAGGED_SCHEMA = """
CREATE TABLE flagged_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL,
  t_move_start INTEGER,
  t_move_end INTEGER,
  price_before REAL,
  price_after REAL,
  z_score REAL,
  volume_delta REAL,
  first_matching_news_ts INTEGER,
  news_lead_minutes REAL,
  feeds_healthy_relevant INTEGER,
  low_confidence INTEGER,
  feeds_detail_json TEXT,
  nearby_markets_json TEXT,
  manual_verdict TEXT
);
"""


# ---- loaders ----

def load_markets(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT market_id, slug, question, theme,
                  keywords_json, end_ts, is_control
           FROM markets""",
        conn,
    )


def load_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT market_id, ts, best_bid, best_ask, last_trade_price, mid, volume_24hr
           FROM snapshots ORDER BY market_id, ts""",
        conn,
    )
    df["ts"] = df["ts"].astype("int64")
    return df


def load_news(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT id, source, title, url, pub_ts, seen_ts, best_ts FROM news_items",
        conn,
    )


def load_matches(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT news_id, market_id, match_keyword_count
           FROM news_market_matches WHERE market_id != '__nomatch__'""",
        conn,
    )


def load_feed_health(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT source, ts, items_received, last_pub_ts FROM feed_health ORDER BY ts",
        conn,
    )


def load_feed_themes() -> dict[str, set[str]]:
    """Return {feed_name: set of theme tags it covers}."""
    with open(FEEDS_YAML) as f:
        data = yaml.safe_load(f)
    return {f["name"]: set(f.get("themes") or ["global"]) for f in data.get("feeds", [])}


# ---- theme grouping ----

def theme_group(market_theme: str | None) -> str:
    """Coarse group used to match market themes to feed `themes` tags in feeds.yaml."""
    if not market_theme:
        return "global"
    t = market_theme.lower()
    if t.startswith(("iran-", "israel-")):
        return "middle-east"
    if t.startswith("russia-ukraine") or "ukraine" in t:
        return "ukraine"
    if t.startswith(("china-", "taiwan")):
        return "asia"
    if t.startswith(("uk-", "europe")):
        return "uk"
    if t.startswith("control-"):
        return "global"
    return "global"


def relevant_feeds_for(market_theme: str | None, feed_themes: dict[str, set[str]]) -> set[str]:
    """Set of feed names whose themes cover this market's theme group (or 'global')."""
    group = theme_group(market_theme)
    out = set()
    for feed_name, themes in feed_themes.items():
        if group in themes or "global" in themes:
            out.add(feed_name)
    return out


# ---- coverage ----

def coverage_summary(markets: pd.DataFrame, snaps: pd.DataFrame, news: pd.DataFrame,
                     matches: pd.DataFrame, health: pd.DataFrame) -> str:
    lines = ["## Coverage", ""]
    lines.append(f"- generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- markets tracked: {len(markets)}  "
                 f"(geo={len(markets[markets.is_control == 0])}, "
                 f"control={len(markets[markets.is_control == 1])})")
    lines.append(f"- snapshots: {len(snaps):,}")
    if len(snaps):
        span_h = (snaps.ts.max() - snaps.ts.min()) / 3_600_000
        lines.append(f"- snapshot span: {span_h:.2f} hours  "
                     f"({_fmt_ms(snaps.ts.min())} → {_fmt_ms(snaps.ts.max())})")
        per_market = snaps.groupby("market_id").ts.count()
        lines.append(f"- snapshots per market: min={per_market.min()} "
                     f"median={int(per_market.median())} max={per_market.max()}")
    lines.append(f"- news items: {len(news):,}")
    if len(news):
        lines.append("- news by source:")
        for src, count in news.source.value_counts().items():
            last_ts = news[news.source == src].best_ts.max()
            lines.append(f"    - {src}: {count} items, latest={_fmt_ms(last_ts)}")
    lines.append(f"- news→market matches: {len(matches):,}")
    return "\n".join(lines)


def _fmt_ms(ms: int | float | None) -> str:
    if ms is None or (isinstance(ms, float) and np.isnan(ms)):
        return "n/a"
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, OSError):
        return "n/a"


# ---- per-market observed hours (for rate normalisation) ----

def observed_hours_per_market(snaps: pd.DataFrame) -> dict[str, float]:
    """For each market, compute (max_ts - min_ts) / 1h. Markets with only one
    snapshot get 0 — they don't contribute to the rate denominator."""
    out: dict[str, float] = {}
    if snaps.empty:
        return out
    for cid, sub in snaps.groupby("market_id"):
        if len(sub) < 2:
            out[cid] = 0.0
            continue
        out[cid] = float((sub.ts.max() - sub.ts.min()) / 3_600_000)
    return out


# ---- feed health at event granularity ----

def feed_window_activity(news: pd.DataFrame, t_start_ms: int, t_end_ms: int,
                         all_feed_names: set[str]) -> dict[str, dict]:
    """For each feed, report activity during the window:
       items_in_window: count of news_items
       last_pub_in_window: timestamp of latest item (or None)
       silent_minutes: minutes since last pub before/in window end.

    Window used for silence check: [t_start_ms - FEED_SILENT_SOFT_MINUTES*60_000, t_end_ms].
    """
    lookback_ms = FEED_SILENT_SOFT_MINUTES * 60_000
    win_lo = t_start_ms - lookback_ms
    win_hi = t_end_ms
    out: dict[str, dict] = {}
    for feed in all_feed_names:
        sub = news[(news.source == feed) & (news.best_ts >= win_lo) & (news.best_ts <= win_hi)]
        last = int(sub.best_ts.max()) if len(sub) else None
        if last:
            silent_min = max(0.0, (t_end_ms - last) / 60_000)
        else:
            # No items in window — feed effectively silent for ≥ lookback.
            silent_min = (t_end_ms - win_lo) / 60_000
        out[feed] = {
            "items": int(len(sub)),
            "last_pub_ts": last,
            "silent_minutes": round(silent_min, 1),
        }
    return out


def feeds_healthy_hard(t_start_ms: int, health: pd.DataFrame, relevant_feeds: set[str]) -> int:
    """Hard filter: return 1 iff every RELEVANT feed has had a publish in the
    last FEED_SILENT_HARD_MINUTES as-of t_start_ms. Used for event admission."""
    if health.empty or not relevant_feeds:
        return 0
    cutoff = t_start_ms - FEED_SILENT_HARD_MINUTES * 60_000
    for src in relevant_feeds:
        sub = health[(health.source == src) & (health.ts <= t_start_ms)]
        if sub.empty:
            return 0
        last_pub = sub.last_pub_ts.dropna().max() if sub.last_pub_ts.notna().any() else None
        if last_pub is None or last_pub < cutoff:
            return 0
    return 1


# ---- detection ----

def build_windows_for_market(market_id: str, snaps: pd.DataFrame) -> pd.DataFrame:
    sub = snaps[snaps.market_id == market_id].copy()
    if sub.empty or len(sub) < 3:
        return pd.DataFrame()
    sub["bucket"] = (sub.ts // (WINDOW_MIN * 60_000)) * (WINDOW_MIN * 60_000)
    g = sub.groupby("bucket").agg(
        price_first=("mid", "first"),
        price_last=("mid", "last"),
        volume_first=("volume_24hr", "first"),
        volume_last=("volume_24hr", "last"),
        n=("ts", "count"),
    )
    g["delta_price"] = g.price_last - g.price_first
    g["volume_delta"] = (g.volume_last - g.volume_first).fillna(0)
    g["volume_delta_positive"] = g.volume_delta.clip(lower=0)
    return g.reset_index()


def news_match_index(news: pd.DataFrame, matches: pd.DataFrame) -> dict[str, np.ndarray]:
    m = matches.merge(news[["id", "best_ts"]], left_on="news_id", right_on="id")
    return {cid: np.sort(g.best_ts.values) for cid, g in m.groupby("market_id")}


def first_matching_news(ts_start: int, match_ts: np.ndarray | None) -> int | None:
    if match_ts is None or len(match_ts) == 0:
        return None
    lo = ts_start - NEWS_LOOKBACK_MIN * 60_000
    in_window = match_ts[(match_ts >= lo) & (match_ts <= ts_start + WINDOW_MIN * 60_000)]
    return int(in_window[0]) if len(in_window) else None


def baseline_sigma(windows: pd.DataFrame, match_ts: np.ndarray | None) -> float | None:
    if windows.empty:
        return None
    if match_ts is None or len(match_ts) == 0:
        clean = windows
    else:
        pad = 30 * 60_000
        mask = np.ones(len(windows), dtype=bool)
        buckets = windows.bucket.values
        for i, b in enumerate(buckets):
            if ((match_ts >= b - pad) & (match_ts <= b + WINDOW_MIN * 60_000 + pad)).any():
                mask[i] = False
        clean = windows[mask]
    deltas = clean.delta_price.dropna()
    if len(deltas) < 10:
        return None
    s = float(deltas.std())
    return s if s > 0 else None


def detect_flagged_events(
    markets: pd.DataFrame, snaps: pd.DataFrame, news: pd.DataFrame,
    matches: pd.DataFrame, health: pd.DataFrame, feed_themes: dict[str, set[str]],
) -> pd.DataFrame:
    if snaps.empty:
        return pd.DataFrame()
    idx = news_match_index(news, matches)
    per_market_windows: dict[str, pd.DataFrame] = {}
    per_market_sigma: dict[str, float | None] = {}
    theme_by_market: dict[str, str] = dict(zip(markets.market_id, markets.theme))
    all_feed_names = set(feed_themes.keys())

    for cid in markets.market_id:
        w = build_windows_for_market(cid, snaps)
        per_market_windows[cid] = w
        per_market_sigma[cid] = baseline_sigma(w, idx.get(cid))

    rows = []
    for cid, w in per_market_windows.items():
        sigma = per_market_sigma.get(cid)
        if w.empty or sigma is None:
            continue
        theme = theme_by_market.get(cid)
        relevant = relevant_feeds_for(theme, feed_themes)
        end_ts_s = markets.loc[markets.market_id == cid, "end_ts"]
        end_ts = int(end_ts_s.iloc[0]) if len(end_ts_s) and pd.notna(end_ts_s.iloc[0]) else None
        start_ts = int(w.bucket.min())
        match_ts_arr = idx.get(cid)

        for _, row in w.iterrows():
            if pd.isna(row.delta_price):
                continue
            z = abs(row.delta_price) / sigma
            if z < Z_THRESHOLD:
                continue
            ts_start = int(row.bucket)
            ts_end = ts_start + WINDOW_MIN * 60_000
            if ts_start < start_ts + 30 * 60_000:
                continue
            if end_ts and ts_end > end_ts - 60 * 60_000:
                continue
            if row.volume_delta_positive < MIN_VOLUME_DELTA_USD:
                continue
            # Theme-aware hard filter.
            fh = feeds_healthy_hard(ts_start, health, relevant)
            if not fh:
                continue
            # Soft per-feed activity map — surfaced in report and sets low_confidence.
            activity = feed_window_activity(news, ts_start, ts_end, all_feed_names)
            relevant_silence = [
                (f, activity[f]["silent_minutes"])
                for f in relevant if activity.get(f, {}).get("silent_minutes", 0) > FEED_SILENT_SOFT_MINUTES
            ]
            low_conf = 1 if relevant_silence else 0
            news_ts = first_matching_news(ts_start, match_ts_arr)
            lead_min = ((ts_start - news_ts) / 60_000) if news_ts is not None else None
            nearby = []
            if theme:
                for other_cid, other_w in per_market_windows.items():
                    if other_cid == cid or theme_by_market.get(other_cid) != theme:
                        continue
                    other_sigma = per_market_sigma.get(other_cid)
                    if other_sigma is None or other_w.empty:
                        continue
                    match = other_w[other_w.bucket == ts_start]
                    if match.empty or pd.isna(match.delta_price.iloc[0]):
                        continue
                    zo = abs(match.delta_price.iloc[0]) / other_sigma
                    if zo >= CO_MOVEMENT_Z_THRESHOLD:
                        nearby.append({"market_id": other_cid, "z": round(float(zo), 2)})
            rows.append({
                "market_id": cid,
                "t_move_start": ts_start,
                "t_move_end": ts_end,
                "price_before": float(row.price_first) if pd.notna(row.price_first) else None,
                "price_after": float(row.price_last) if pd.notna(row.price_last) else None,
                "z_score": round(float(z), 2),
                "volume_delta": round(float(row.volume_delta_positive), 2),
                "first_matching_news_ts": news_ts,
                "news_lead_minutes": round(float(lead_min), 1) if lead_min is not None else None,
                "feeds_healthy_relevant": fh,
                "low_confidence": low_conf,
                "feeds_detail_json": json.dumps({
                    "relevant_feeds": sorted(relevant),
                    "activity": activity,
                }),
                "nearby_markets_json": json.dumps(nearby),
            })
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values(
            by=["news_lead_minutes", "z_score"],
            ascending=[False, False],
            na_position="last",
        ).reset_index(drop=True)
    return df


def persist_flagged(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    conn.execute("DROP TABLE IF EXISTS flagged_events")
    conn.executescript(FLAGGED_SCHEMA)
    if df.empty:
        conn.commit()
        return
    conn.executemany(
        """INSERT INTO flagged_events
           (market_id, t_move_start, t_move_end, price_before, price_after,
            z_score, volume_delta, first_matching_news_ts, news_lead_minutes,
            feeds_healthy_relevant, low_confidence, feeds_detail_json,
            nearby_markets_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        df[[
            "market_id", "t_move_start", "t_move_end", "price_before", "price_after",
            "z_score", "volume_delta", "first_matching_news_ts", "news_lead_minutes",
            "feeds_healthy_relevant", "low_confidence", "feeds_detail_json",
            "nearby_markets_json",
        ]].itertuples(index=False, name=None),
    )
    conn.commit()


# ---- report ----

def classify_ratio(ratio: float) -> str:
    for bound, label in VERDICT_THRESHOLDS:
        if ratio < bound:
            return label
    return VERDICT_THRESHOLDS[-1][1]


def build_report(markets: pd.DataFrame, snaps: pd.DataFrame, news: pd.DataFrame,
                 matches: pd.DataFrame, health: pd.DataFrame,
                 flagged: pd.DataFrame) -> str:
    hours_by_mkt = observed_hours_per_market(snaps)
    is_control_by_id = dict(zip(markets.market_id, markets.is_control))
    slug_by_id = dict(zip(markets.market_id, markets.slug))
    theme_by_id = dict(zip(markets.market_id, markets.theme))

    cand_market_hours = sum(h for cid, h in hours_by_mkt.items() if is_control_by_id.get(cid) == 0)
    ctrl_market_hours = sum(h for cid, h in hours_by_mkt.items() if is_control_by_id.get(cid) == 1)

    if not flagged.empty:
        geo_flags = flagged[flagged.market_id.map(lambda c: is_control_by_id.get(c, 0) == 0)]
        ctrl_flags = flagged[flagged.market_id.map(lambda c: is_control_by_id.get(c, 0) == 1)]
    else:
        geo_flags = ctrl_flags = pd.DataFrame()

    cand_rate = (len(geo_flags) / cand_market_hours) if cand_market_hours > 0 else 0.0
    ctrl_rate = (len(ctrl_flags) / ctrl_market_hours) if ctrl_market_hours > 0 else 0.0
    ratio = (cand_rate / ctrl_rate) if ctrl_rate > 0 else float("inf") if cand_rate > 0 else 0.0
    verdict = classify_ratio(ratio)

    lines: list[str] = []
    lines.append("# e10 REPORT\n")

    # Headline: the control comparison.
    lines.append("## Control-vs-candidate flag rate (headline)\n")
    lines.append(f"- candidate markets: {int((markets.is_control == 0).sum())} markets, "
                 f"{cand_market_hours:.1f} market-hours observed, {len(geo_flags)} flags")
    lines.append(f"- control markets:   {int((markets.is_control == 1).sum())} markets, "
                 f"{ctrl_market_hours:.1f} market-hours observed, {len(ctrl_flags)} flags")
    lines.append(f"- candidate flag rate: {cand_rate * 1000:.2f} per 1k market-hours")
    lines.append(f"- control   flag rate: {ctrl_rate * 1000:.2f} per 1k market-hours")
    if ctrl_rate > 0:
        lines.append(f"- **ratio: {ratio:.2f}×**")
    else:
        lines.append(f"- **ratio: n/a** (control flags = 0)")
    lines.append("")
    lines.append(f"### Verdict\n\n**{verdict}**\n")
    lines.append("Reference — decision gate thresholds (pre-committed):")
    for bound, label in VERDICT_THRESHOLDS:
        b = "∞" if bound == float("inf") else f"{bound}"
        lines.append(f"- ratio < {b}× → {label}")
    lines.append("")
    lines.append("Phrasing rule enforced by this report: no event is described "
                 "as \"suspicious\", \"consistent with informed trading\", \"insider-like\", "
                 "or \"leak\". Strongest allowed phrasing is "
                 "`unexplained by our monitored feed set`. This is pre-committed.\n")

    # Coverage stats second.
    lines.append(coverage_summary(markets, snaps, news, matches, health))
    lines.append("")

    # Flagged events table third.
    lines.append("## Flagged events\n")
    lines.append(f"- total flags: {len(flagged)} (candidate={len(geo_flags)}, control={len(ctrl_flags)})")
    low_conf_total = int(flagged.low_confidence.sum()) if len(flagged) else 0
    lines.append(f"- ⚠️ low-confidence (theme-relevant feed silent >{FEED_SILENT_SOFT_MINUTES}m in event window): {low_conf_total}")
    lines.append("")
    if flagged.empty:
        lines.append("_No events passed the filter._")
    else:
        lines.append("### Top 20 by news-lead\n")
        lines.append("Conf = ⚠️ if any theme-relevant feed silent >" f"{FEED_SILENT_SOFT_MINUTES}m in window.\n")
        lines.append("| # | conf | slug | theme | c/ctrl | z | Δprice | volΔ$ | lead_min | first_news | nearby |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for i, row in flagged.head(20).iterrows():
            slug = slug_by_id.get(row.market_id, row.market_id[:10])
            theme = theme_by_id.get(row.market_id, "?")
            is_ctrl = "ctrl" if is_control_by_id.get(row.market_id, 0) else "cand"
            dprice = (row.price_after or 0) - (row.price_before or 0)
            news_ts = _fmt_ms(row.first_matching_news_ts) if row.first_matching_news_ts else "—"
            lead = f"{row.news_lead_minutes:+.1f}" if pd.notna(row.news_lead_minutes) else "—"
            nearby = json.loads(row.nearby_markets_json or "[]")
            conf = "⚠️" if row.low_confidence else " "
            lines.append(
                f"| {i+1} | {conf} | {slug[:42]} | {theme} | {is_ctrl} | {row.z_score:.2f} | "
                f"{dprice:+.3f} | {row.volume_delta:,.0f} | {lead} | {news_ts} | {len(nearby)} |"
            )
        lines.append("")
        lines.append("### Per-event feed activity (top 10)\n")
        lines.append("For each event: silent_minutes per theme-relevant feed during "
                     f"[t_start − {FEED_SILENT_SOFT_MINUTES}min, t_end].\n")
        for i, row in flagged.head(10).iterrows():
            detail = json.loads(row.feeds_detail_json or "{}")
            relevant = detail.get("relevant_feeds") or []
            activity = detail.get("activity") or {}
            slug = slug_by_id.get(row.market_id, row.market_id[:10])[:50]
            lines.append(f"**#{i+1} {slug}** ({_fmt_ms(row.t_move_start)})")
            lines.append("")
            lines.append("| feed | silent_min | items_in_window | last_pub |")
            lines.append("|---|---|---|---|")
            for f in relevant:
                a = activity.get(f) or {}
                silent = a.get("silent_minutes")
                mark = " ⚠️" if silent is not None and silent > FEED_SILENT_SOFT_MINUTES else ""
                lines.append(f"| {f}{mark} | {silent} | {a.get('items')} | {_fmt_ms(a.get('last_pub_ts'))} |")
            lines.append("")

    # Manual review instructions last.
    lines.append("## Manual review\n")
    lines.append("See `MANUAL_REVIEW_RUBRIC.md` for the six disqualifier checks that must be applied "
                 "before any flag can be labeled `unexplained-by-monitored-feeds`. Fill `manual_verdict` "
                 "in the `flagged_events` table per row. No verdict other than the ones specified in the rubric "
                 "is admissible for the decision gate.\n")
    lines.append("SQL for verdict entry:")
    lines.append("```")
    lines.append("UPDATE flagged_events SET manual_verdict = '<label>' WHERE id = <n>;")
    lines.append("```")
    return "\n".join(lines)


# ---- main ----

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--coverage-only", action="store_true")
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    markets = load_markets(conn)
    snaps = load_snapshots(conn)
    news = load_news(conn)
    matches = load_matches(conn)
    health = load_feed_health(conn)
    feed_themes = load_feed_themes()

    print(coverage_summary(markets, snaps, news, matches, health))
    print()

    if args.coverage_only:
        conn.close()
        return

    span_h = (snaps.ts.max() - snaps.ts.min()) / 3_600_000 if len(snaps) else 0
    if span_h < MIN_SNAPSHOT_SPAN_HOURS:
        print(f"SKIP DETECTION: snapshot span {span_h:.2f}h < {MIN_SNAPSHOT_SPAN_HOURS}h minimum")
        print("Re-run after more data is collected.")
        conn.close()
        return

    flagged = detect_flagged_events(markets, snaps, news, matches, health, feed_themes)
    print(f"detection: {len(flagged)} flagged events")
    persist_flagged(conn, flagged)

    report = build_report(markets, snaps, news, matches, health, flagged)
    REPORT.write_text(report)
    print(f"wrote {REPORT}")
    conn.close()


if __name__ == "__main__":
    main()
