"""Agent E — stratify sports T-7d calibration by market sub-category.

Sub-categories (via slug keyword rules):
    game_outcome : head-to-head team/player match on a specific date
    futures      : season-long / championship / MVP / award / standings
    props        : individual player/event props (pole, fastest lap, first-X,
                   coin-toss, performance, anthem, constructor-1st, etc.)
    totals       : over/under on points / goals / runs / sets
    spreads      : point / goal spreads
    uncategorized: doesn't cleanly match any rule

Outputs written to experiments/e23_stratification/e_subcategory/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
IN_PARQUET = (BASE.parents[1]
              / "e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet")

# --------------------------------------------------------------------------- #
# Bucketing (same scheme as e16)
# --------------------------------------------------------------------------- #
BUCKETS = [(i / 100.0, (i + 5) / 100.0) for i in range(0, 100, 5)]


def bucket_label(p: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "0.95-1.00"


def bucket_mid(p: float) -> float:
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return lo + 0.025
    return 0.975


# --------------------------------------------------------------------------- #
# Slug parsing rules
# --------------------------------------------------------------------------- #
# Rule ordering matters — checked top-to-bottom; first match wins.
# Rationale in DECISIONS.md.

# Regex pieces
_RE_DATE = re.compile(r"-\d{4}-\d{2}-\d{2}(-|$)")
_RE_TEAM_DATE_HEAD = re.compile(
    r"^[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-\d{4}-\d{2}-\d{2}"
)
_RE_TENNIS_MATCH = re.compile(
    r"^(atp|wta|us-open)-[a-z0-9]+-v?s?-?[a-z0-9]+-\d{4}-\d{2}-\d{2}"
)
_RE_UFC_MATCH_DATED = re.compile(r"^ufc-[a-z0-9]+-vs-[a-z0-9]+-\d{4}-\d{2}-\d{2}$")

# SPREAD indicators
_RE_SPREAD = re.compile(r"-spread-|-handicap-")

# TOTALS indicators — require explicit total/over/under marker. Avoid team
# abbreviations like "tot" for Tottenham by requiring suffix-total or explicit
# "over"/"under" word boundary.
_RE_TOTAL = re.compile(
    r"(-total-\d|-match-total-|-ou-|-over-under-|total-ou-|"
    r"-over-\d|-under-\d|-btts|\d+pt\d+$)"
)

# FUTURES — championship / season / MVP / award / standings / playoffs
_FUTURES_KEYWORDS = [
    "championship",
    "mvp",
    "world-series",
    "super-bowl",       # super-bowl-winner, not super-bowl-lx-safety
    "stanley-cup",
    "world-cup",
    "club-world-cup",
    "finals-",
    "-finals",
    "conference",
    "coach-of-the-year",
    "rookie-of-the-year",
    "defensive-rookie",
    "offensive-rookie",
    "-champion",
    "premier-league",  # will-X-win-the-premier-league
    "champions-league",
    "europa-league",
    "ipl",
    "indian-premier-league",
    "finish-in-the-top",
    "finish-top",
    "win-group",
    "advance-in",
    "advance-to",
    "make-the-nba-playoffs",
    "make-the-mlb-playoffs",
    "make-the-nfl-playoffs",
    "make-the-nhl-playoffs",
    "win-the-nba",
    "win-the-nfl",
    "win-the-afc",
    "win-the-nfc",
    "win-the-al",
    "win-the-nl",
    "win-the-eastern-conference",
    "win-the-western-conference",
    "win-the-national-league",
    "win-the-american-league",
    "drivers-champion",
    "constructors-cup",
    "constructors-championship",
    "nba-finals",
    "nhl-finals",
    "mvp-",
    "protector-of-the-year",
    "top-goalscorer",
    "top-fantasy",
    "conn-smythe",
    "to-advance",
    "win-gold",
    "gold-medal",
    "win-the-eurovision",
    "series-winner",       # e.g. celtics-vs-heat-series-winner
    "finals-mvp",
]

# PROPS — narrow event-level props on game day
_PROPS_KEYWORDS = [
    "pole-position",
    "pole-winner",
    "-pole",
    "fastest-lap",
    "pit-stop",
    "safety-car",
    "sprint-qualif",
    "sprint-winner",
    "constructor-scores-1st",
    "constructor-pole",
    "constructor-fastest",
    "driver-pole-position",
    "driver-podium",
    "driver-pole",
    "practice-",
    "-practice-1",
    "-practice-2",
    "first-goal",
    "first-scorer",
    "first-touchdown",
    "first-set-winner",
    "set-winner-",
    "coin-toss",
    "anthem",
    "halftime-show",
    "kendrick-lamar-perform",
    "perform-humble",
    "perform-all-the-stars",
    "perform-squabble",
    "trump-attend",
    "elon-musk-attend",
    "end-in-round",
    "round-1",                 # e.g. will-the-fight-end-in-round-1
    "have-no-official-winner",
    "scorigami",
    "safety",                   # super-bowl-lx-safety
    "coin-toss-",
    "qbs-get-taken",
    "be-the-top-",
    "be-the-third-qb",
    "win-nba-coach",
    "vs-team-b-to-advance",
    "first-round-of-the",        # will-jaxson-dart-be-the-third-qb...
    "bearman-2025",
]

# FUTURES prefix-match for "will-<entity>-win-the-<YYYY>" that is *not* a GP
# (those are single-race events, treat as game_outcome since they resolve on
# one day). But "will-X-win-the-<year>-championship/french-open/wimbledon..."
# is a season-long future.
_FUTURES_YEAR_PATTERNS = [
    r"win-the-\d{4}-french-open",
    r"win-the-\d{4}-us-open",
    r"win-the-\d{4}-wimbledon",
    r"win-the-\d{4}-australian-open",
    r"win-the-\d{4}-atp-cincinnati",
    r"win-the-\d{4}-atp-",
    r"win-the-\d{4}-wta-",
    r"win-a-gold-medal",
    r"win-gold",
    r"win-the-\d{4}-indian-premier-league",
    r"win-the-\d{4}-f1-drivers",
    r"reach-the-quarterfinals",
    r"reach-the-semifinals",
    r"reach-the-finals",
    r"finish-(first|second|third|fourth)",
    r"will-\w+-win-the-\d{4}-\d{2}-nba",
    r"202[0-9]{1}-\d{2}-nba-champion",
    r"nfl-playoffs",
    r"stay-with-the-",
    r"get-traded-to",
    r"world-cup",
]

_FUTURES_YEAR_RE = re.compile("|".join(_FUTURES_YEAR_PATTERNS))


# GAME OUTCOME: team-team-date slug, or "will-team-a-beat-team-b", or GP winners
_GAME_OUTCOME_YEAR_PATTERNS = [
    r"^will-[\w-]+-win-the-\d{4}-(f1-)?(miami|austrian|italian|belgian|dutch|"
    r"singapore|spanish|british|japanese|united-states|monaco|hungarian|qatar|"
    r"abu-dhabi|saudi|bahrain|mexican|brazilian|las-vegas|australian|"
    r"emilia-romagna|canadian|azerbaijan)-grand-prix(-pole)?$",
    r"^will-[\w-]+-win-the-\d{4}-(miami|austrian|italian|belgian|dutch|"
    r"singapore|spanish|british|japanese|united-states|monaco|hungarian|qatar|"
    r"abu-dhabi|saudi|bahrain|mexican|brazilian|las-vegas|australian|"
    r"emilia-romagna|canadian|azerbaijan)-gp(-pole)?$",
    r"^will-[\w-]+-win-the-\d{4}-f1-.*-pole$",
    r"^will-[\w-]+-beat-[\w-]+",
    r"^[\w-]+-vs-[\w-]+$",
    r"^will-[\w-]+-win-the-coin-toss",   # -> props
]

# Note: we route the above "will-X-win-GP-pole" into PROPS separately since
# it's a pole (qualifying) prop, not the race outcome.


def classify(slug: str) -> str:
    s = slug.lower()

    # --- clear noise / irrelevant ---
    if s.startswith("global-heat-increase") or s.startswith("what-is-ther"):
        return "uncategorized"

    # 1. Spread first (very specific)
    if _RE_SPREAD.search(s):
        return "spreads"

    # 2. Totals (specific markers)
    if _RE_TOTAL.search(s):
        return "totals"

    # 2b. NFL draft pick order props
    if re.search(r"^will-[\w-]+-(be|win)-.*(first|second|third|2nd|3rd|1st)-pick", s):
        return "props"
    if "taken-with-the" in s and "pick" in s:
        return "props"
    if "make-the-first-pick" in s or "first-pick-of-the" in s:
        return "props"
    if "uefa-nations-league" in s:
        return "futures"
    if "nba-playoffs-first-round" in s and "-vs-" in s:
        return "game_outcome"
    if "comeback-player-of-the-year" in s or \
       "offensive-player-of-the-year" in s or \
       "defensive-player-of-the-year" in s:
        return "futures"
    if "finish-with-the-worst-record" in s or "finish-in-2nd-place" in s or \
       "finish-in-1st-place" in s or "finish-in-3rd-place" in s or \
       "finish-in-4th-place" in s or "finish-last" in s:
        return "futures"
    if "be-traded-to" in s or "stay-with-the" in s:
        return "futures"
    if "uefa-ban" in s or "uefa-suspend" in s:
        return "futures"
    if "academy-awards" in s or "bafta-awards" in s:
        return "futures"
    if "highest-constructor-score" in s:
        return "props"

    # 3. F1 pole / podium / fastest-lap / safety-car / constructor-1st = PROPS
    if any(k in s for k in [
        "pole-position", "-pole-", "fastest-lap", "pit-stop", "safety-car",
        "sprint-qualif", "sprint-winner", "driver-podium",
        "constructor-scores-1st", "constructor-pole-position",
        "constructor-fastest-lap", "driver-pole-position", "practice-1",
        "practice-2", "first-goal", "first-scorer", "first-touchdown",
        "first-set-winner", "coin-toss", "anthem", "halftime-show",
        "perform-all-the-stars", "perform-humble", "perform-squabble",
        "kendrick-lamar-perform", "-attend-ufc", "-attend-a-ufc",
        "attend-the-2025-mlb-world-series", "trump-attend",
        "end-in-round-1", "have-no-official-winner", "scorigami",
        "-safety", "qbs-get-taken", "be-the-third-qb",
        "be-the-top-fantasy", "be-the-top-goalscorer",
        "be-the-2025-2026-nfl-offensive", "be-the-2025-2026-nfl-defensive",
        "mannes-protector", "win-the-nfl-protector",
        "score-the-most-total-points", "top-goalscorer",
        "f1-rotten-tomatoes",
    ]):
        # but ensure it's not actually a full race future
        if "win-the-2025-f1-drivers-championship" in s:
            return "futures"
        return "props"

    # "will-X-win-the-YYYY-f1-<gp>-<gp>-pole" – pole is a prop
    if re.search(r"win-the-\d{4}-(f1-)?[\w-]+-grand-prix-pole$", s):
        return "props"
    if re.search(r"win-the-\d{4}-[\w-]+-gp-pole$", s):
        return "props"
    if re.search(r"win-the-\d{4}-miami-gp-pole$", s):
        return "props"
    if re.search(r"win-the-\d{4}-\w+-gp-pole$", s):
        return "props"

    # 3b. "will-X-win-wimbledon[-YYYY|-mens|-womens]" → futures (multi-round tournament)
    if re.search(r"win-wimbledon(-mens|-womens|-\d{4})?$", s):
        return "futures"
    if re.search(r"win-the-(us-open|french-open|australian-open)(-\d{4})?$", s):
        return "futures"
    if re.search(r"win-the-\d{4}-(womens|mens)?-?(australian|us|french)-open", s):
        return "futures"
    if re.search(r"win-the-\d{4}-golf-(us|pga|masters|british)-open", s):
        return "futures"

    # 4. Futures (season / championship / awards / standings)
    if _FUTURES_YEAR_RE.search(s):
        return "futures"
    if any(k in s for k in _FUTURES_KEYWORDS):
        return "futures"

    # 5. Game outcome: team-team-date, h2h, single-race winner
    # 5a. Team-team-date style
    if _RE_TEAM_DATE_HEAD.match(s):
        return "game_outcome"
    # 5b. Tennis / UFC dated h2h
    if _RE_TENNIS_MATCH.match(s):
        return "game_outcome"
    # 5b'. us-open-<player>-vs-<player>-DATE style
    if re.match(r"^us-open-[\w-]+-vs-[\w-]+-\d{4}-\d{2}-\d{2}$", s):
        return "game_outcome"
    if _RE_UFC_MATCH_DATED.match(s):
        return "game_outcome"
    # 5c. "a-vs-b" pattern with no date
    if re.match(r"^[a-z0-9]+-vs-[a-z0-9-]+$", s):
        return "game_outcome"
    # 5d. UFC fight-night-a-vs-b
    if s.startswith("ufc-fight-night-") or s.startswith("ufc-"):
        return "game_outcome"
    if re.match(r"^[a-z][a-z0-9]+-vs-[a-z][a-z0-9-]+$", s):
        return "game_outcome"
    # 5e. boxing-a-vs-b
    if s.startswith("boxing-"):
        return "game_outcome"
    # 5f. "will-<driver>-win-the-<GP>-grand-prix" with no year prefix (single-race)
    if re.match(r"^will-[\w-]+-win-the-[\w-]+-grand-prix$", s):
        return "game_outcome"
    # 5g. "will-X-win-his-boxing-match-against-Y" → game_outcome
    if "win-his-boxing-match" in s:
        return "game_outcome"
    # 5h. Hyphenated fighter pair with no prefix, e.g. "machado-garry-vs-prates",
    # "alexander-volkanovski-vs-diego-lopes", "nikita-krylov-vs-dominick-reyes".
    # Allow multi-segment names.
    if re.match(r"^[a-z]+(-[a-z]+)?-vs-[a-z]+(-[a-z]+)*$", s):
        return "game_outcome"
    # 5i. "a-vs-b-YYYY-MM-DD" generic fallback
    if re.match(r"^[a-z]+(-[a-z]+)*-vs-[a-z]+(-[a-z]+)*-\d{4}-\d{2}-\d{2}$", s):
        return "game_outcome"
    # 5j. Subway series / Eastern Conference Finals A vs B
    if s == "subway-series":
        return "game_outcome"
    if "-vs-" in s and (re.search(r"\d{4}-\d{2}-\d{2}$", s) or "series" in s):
        return "game_outcome"
    # 5k. Team-only 3-segment date slugs like "cru19wc-eng19-ind19-2026-02-06"
    if re.match(r"^[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-\d{4}-\d{2}-\d{2}(-[a-z0-9]+)?$", s):
        return "game_outcome"
    # 5f. "will-team-a-beat-team-b"
    if re.search(r"will-[\w-]+-beat-[\w-]+", s):
        # But "beat-the-X-4-Y" is a series (e.g. 4-2) — that's a series outcome
        # which is a championship/futures-like prop, but still a clear head-to-head
        # outcome resolved on a specific sequence. Keep as game_outcome.
        return "game_outcome"
    # 5g. "will-X-win-the-YYYY-<single-race-GP>"
    if re.search(r"will-[\w-]+-win-the-\d{4}-(f1-)?[\w-]+-grand-prix$", s):
        return "game_outcome"
    if re.search(r"will-[\w-]+-win-the-\d{4}-(miami|italian|austrian|belgian|"
                 r"dutch|singapore|spanish|british|japanese|monaco|hungarian|"
                 r"qatar|abu-dhabi|saudi|bahrain|mexican|brazilian|las-vegas|"
                 r"australian|emilia-romagna|canadian|azerbaijan)-gp$", s):
        return "game_outcome"

    # F1 typed slugs: "f1-<gp>-winner-<driver>-DATE" or "f1-<gp>-constructor-scores-Xth-..."
    if re.match(r"^f1-[\w-]+-winner-[\w-]+-\d{4}-\d{2}-\d{2}$", s):
        return "game_outcome"
    if re.match(r"^f1-[\w-]+-driver-[\w-]+-\d{4}-\d{2}-\d{2}$", s):
        # driver-pole / driver-podium already caught as props; else game_outcome
        return "props"    # any other driver-* slug is a per-driver prop
    if re.match(r"^f1-[\w-]+-constructor-[\w-]+-\d{4}-\d{2}-\d{2}$", s):
        return "props"

    return "uncategorized"


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #
def calibration_table(df: pd.DataFrame) -> pd.DataFrame:
    tbl = (df.groupby("bucket")
             .agg(n=("yes", "size"),
                  yes_rate=("yes", "mean"),
                  mid=("bucket_mid", "mean"))
             .reset_index()
             .sort_values("bucket"))
    tbl["deviation"] = tbl["yes_rate"] - tbl["mid"]
    return tbl


def main() -> int:
    df = pd.read_parquet(IN_PARQUET)
    print(f"loaded {len(df):,} sports T-7d snapshots")

    df["sub_category"] = df["slug"].apply(classify)
    df["bucket"] = df["price_tm7d"].apply(bucket_label)
    df["bucket_mid"] = df["price_tm7d"].apply(bucket_mid)
    df["yes"] = (df["resolution"] == "YES").astype(int)

    counts = df["sub_category"].value_counts()
    print("\nsub-category counts:")
    print(counts.to_string())

    # Dump uncategorized for review
    uncat = df[df["sub_category"] == "uncategorized"]["slug"].tolist()
    (DATA_DIR / "uncategorized_slugs.txt").write_text("\n".join(uncat))
    print(f"\nuncategorized: {len(uncat)} (see data/uncategorized_slugs.txt)")

    # Category counts (plus breakdown by sport category)
    cross = pd.crosstab(df["category"], df["sub_category"])
    print("\ncategory x sub-category:")
    print(cross.to_string())

    # Per sub-category calibration
    sub_tables: dict[str, list[dict]] = {}
    bucket_055 = "0.55-0.60"
    bucket_065 = "0.65-0.70"   # FYI
    overall_flb_by_subcat: dict[str, dict] = {}

    for sub in counts.index:
        sub_df = df[df["sub_category"] == sub]
        if len(sub_df) < 30:
            print(f"\nskipping {sub} calibration — n={len(sub_df)} < 30")
            sub_tables[sub] = []
            continue

        tbl = calibration_table(sub_df)
        sub_tables[sub] = tbl.to_dict(orient="records")
        print(f"\n=== {sub}  (n={len(sub_df)})===")
        print(f"  {'bucket':<12} {'n':>5}  {'mid':>5}  {'yes_rate':>9}  {'dev':>7}")
        for _, r in tbl.iterrows():
            if r["n"] >= 1:
                print(f"  {r['bucket']:<12} {int(r['n']):>5,}  {r['mid']:>5.3f}  "
                      f"{r['yes_rate']:>9.3f}  {r['deviation']:>+7.3f}")

        # FLB at 0.55-0.60
        row = tbl[tbl["bucket"] == bucket_055]
        if len(row):
            n = int(row["n"].iloc[0])
            dev = float(row["deviation"].iloc[0])
            rate = float(row["yes_rate"].iloc[0])
            overall_flb_by_subcat[sub] = {
                "n_0p55_0p60": n,
                "yes_rate": round(rate, 4),
                "deviation": round(dev, 4),
                "insufficient": n < 20,
            }
        else:
            overall_flb_by_subcat[sub] = {
                "n_0p55_0p60": 0,
                "yes_rate": None,
                "deviation": None,
                "insufficient": True,
            }

    # Mid-range (0.40 <= p < 0.70) FLB aggregate per sub-category — useful
    # because prop slugs concentrate in the tails and single buckets are noisy
    mid_flb = {}
    for sub in counts.index:
        sub_df = df[(df["sub_category"] == sub)
                    & (df["price_tm7d"] >= 0.40)
                    & (df["price_tm7d"] < 0.70)]
        if len(sub_df) == 0:
            mid_flb[sub] = {"n": 0, "mean_price": None,
                            "yes_rate": None, "deviation": None,
                            "insufficient": True}
            continue
        mp = float(sub_df["price_tm7d"].mean())
        yr = float(sub_df["yes"].mean())
        mid_flb[sub] = {
            "n": int(len(sub_df)),
            "mean_price": round(mp, 4),
            "yes_rate": round(yr, 4),
            "deviation": round(yr - mp, 4),
            "insufficient": len(sub_df) < 30,
        }
    print("\n=== Mid-range (0.40-0.70) FLB by sub-category ===")
    print(f"  {'sub':<14} {'n':>4}  {'mean_p':>7}  {'yes_rate':>9}  {'dev':>7}")
    for sub, rec in mid_flb.items():
        if rec["mean_price"] is not None:
            flag = "  (<30 n)" if rec["insufficient"] else ""
            print(f"  {sub:<14} {rec['n']:>4}  {rec['mean_price']:>7.3f}  "
                  f"{rec['yes_rate']:>9.3f}  {rec['deviation']:>+7.3f}{flag}")

    # Write JSON
    (DATA_DIR / "subcategory_calibration.json").write_text(json.dumps({
        "source_parquet": str(IN_PARQUET.relative_to(BASE.parents[1])),
        "n_markets": int(len(df)),
        "counts_per_subcategory": counts.to_dict(),
        "category_subcategory_cross": {
            str(c): dict(zip(cross.columns, map(int, cross.loc[c])))
            for c in cross.index
        },
        "calibration_by_subcategory": sub_tables,
        "flb_055_060_by_subcategory": overall_flb_by_subcat,
        "mid_range_flb_0p40_0p70_by_subcategory": mid_flb,
        "uncategorized_n": len(uncat),
    }, indent=2, default=str))
    print(f"\nwrote {DATA_DIR / 'subcategory_calibration.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
