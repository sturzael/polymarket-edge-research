# e10 REPORT

## Control-vs-candidate flag rate (headline)

- candidate markets: 18 markets, 121.4 market-hours observed, 11 flags
- control markets:   11 markets, 74.2 market-hours observed, 6 flags
- candidate flag rate: 90.64 per 1k market-hours
- control   flag rate: 80.90 per 1k market-hours
- **ratio: 1.12×**

### Verdict

**null result — no signal distinguishable from control noise**

Reference — decision gate thresholds (pre-committed):
- ratio < 1.0× → null result — control flags at or above candidate rate
- ratio < 1.5× → null result — no signal distinguishable from control noise
- ratio < 3.0× → weak signal; individual events may or may not survive the manual review rubric
- ratio < ∞× → candidate signal above control baseline; apply decision gate from README and the disqualifier checklist from MANUAL_REVIEW_RUBRIC.md to top events

Phrasing rule enforced by this report: no event is described as "suspicious", "consistent with informed trading", "insider-like", or "leak". Strongest allowed phrasing is `unexplained by our monitored feed set`. This is pre-committed.

## Coverage

- generated: 2026-04-19T02:48:57.296252+00:00
- markets tracked: 29  (geo=18, control=11)
- snapshots: 10,179
- snapshot span: 6.74 hours  (2026-04-18 20:04 UTC → 2026-04-19 02:48 UTC)
- snapshots per market: min=351 median=351 max=351
- news items: 404
- news by source:
    - kyiv-post: 100 items, latest=2026-04-18 15:11 UTC
    - nyt-world: 61 items, latest=2026-04-18 23:51 UTC
    - scmp: 61 items, latest=2026-04-19 02:00 UTC
    - guardian-world: 52 items, latest=2026-04-18 23:01 UTC
    - abc-international: 42 items, latest=2026-04-19 01:30 UTC
    - bbc-world: 34 items, latest=2026-04-18 21:19 UTC
    - al-jazeera: 33 items, latest=2026-04-19 00:28 UTC
    - times-of-israel: 21 items, latest=2026-04-19 00:43 UTC
- news→market matches: 373

## Flagged events

- total flags: 17 (candidate=11, control=6)
- ⚠️ low-confidence (theme-relevant feed silent >60m in event window): 17

### Top 20 by news-lead

Conf = ⚠️ if any theme-relevant feed silent >60m in window.

| # | conf | slug | theme | c/ctrl | z | Δprice | volΔ$ | lead_min | first_news | nearby |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ⚠️ | us-x-iran-permanent-peace-deal-by-april-30 | iran-ceasefire | cand | 6.28 | +0.020 | 10,794 | +51.7 | 2026-04-18 19:48 UTC | 2 |
| 2 | ⚠️ | us-x-iran-permanent-peace-deal-by-april-22 | iran-ceasefire | cand | 3.54 | +0.010 | 13,056 | +51.7 | 2026-04-18 19:48 UTC | 2 |
| 3 | ⚠️ | us-x-iran-permanent-peace-deal-by-april-22 | iran-ceasefire | cand | 3.54 | +0.010 | 9,561 | +0.2 | 2026-04-18 21:19 UTC | 2 |
| 4 | ⚠️ | strait-of-hormuz-traffic-returns-to-normal | iran-military | cand | 3.35 | -0.020 | 4,161 | +0.0 | 2026-04-19 00:00 UTC | 0 |
| 5 | ⚠️ | will-the-iranian-regime-fall-by-june-30 | iran-regime | cand | 6.32 | +0.010 | 14,303 | — | n/a | 0 |
| 6 | ⚠️ | will-spain-win-the-2026-fifa-world-cup-963 | control-worldcup | ctrl | 6.15 | -0.003 | 37,914 | — | n/a | 0 |
| 7 | ⚠️ | will-the-us-confirm-that-aliens-exist-befo | control-aliens | ctrl | 4.42 | -0.010 | 102,205 | — | n/a | 0 |
| 8 | ⚠️ | will-the-us-confirm-that-aliens-exist-befo | control-aliens | ctrl | 4.42 | +0.010 | 1,021 | — | n/a | 0 |
| 9 | ⚠️ | us-obtains-iranian-enriched-uranium-by-may | iran-nuclear | cand | 3.95 | -0.010 | 4,582 | — | n/a | 0 |
| 10 | ⚠️ | us-obtains-iranian-enriched-uranium-by-apr | iran-nuclear | cand | 3.69 | -0.006 | 2,467 | — | n/a | 1 |
| 11 | ⚠️ | us-x-iran-permanent-peace-deal-by-april-22 | iran-ceasefire | cand | 3.54 | +0.010 | 9,258 | — | n/a | 1 |
| 12 | ⚠️ | trump-announces-end-of-military-operations | iran-ceasefire | cand | 3.52 | +0.010 | 1,090 | — | n/a | 1 |
| 13 | ⚠️ | us-x-iran-permanent-peace-deal-by-april-30 | iran-ceasefire | cand | 3.14 | +0.010 | 4,688 | — | n/a | 1 |
| 14 | ⚠️ | will-lorenzo-musetti-win-the-2026-mens-fre | control-tennis | ctrl | 3.12 | +0.001 | 947 | — | n/a | 0 |
| 15 | ⚠️ | will-lorenzo-musetti-win-the-2026-mens-fre | control-tennis | ctrl | 3.12 | -0.001 | 4,976 | — | n/a | 0 |
| 16 | ⚠️ | will-lorenzo-musetti-win-the-2026-mens-fre | control-tennis | ctrl | 3.12 | -0.001 | 3,153 | — | n/a | 1 |
| 17 | ⚠️ | iran-agrees-to-surrender-enriched-uranium- | iran-nuclear | cand | 3.10 | -0.013 | 5,455 | — | n/a | 1 |

### Per-event feed activity (top 10)

For each event: silent_minutes per theme-relevant feed during [t_start − 60min, t_end].

**#1 us-x-iran-permanent-peace-deal-by-april-30-2026** (2026-04-18 20:40 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international ⚠️ | 70.0 | 0 | n/a |
| al-jazeera | 52.0 | 1 | 2026-04-18 19:58 UTC |
| bbc-world ⚠️ | 70.0 | 0 | n/a |
| guardian-world | 19.3 | 5 | 2026-04-18 20:30 UTC |
| nyt-world | 49.1 | 3 | 2026-04-18 20:00 UTC |
| times-of-israel | 25.6 | 1 | 2026-04-18 20:24 UTC |

**#2 us-x-iran-permanent-peace-deal-by-april-22-2026** (2026-04-18 20:40 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international ⚠️ | 70.0 | 0 | n/a |
| al-jazeera | 52.0 | 1 | 2026-04-18 19:58 UTC |
| bbc-world ⚠️ | 70.0 | 0 | n/a |
| guardian-world | 19.3 | 5 | 2026-04-18 20:30 UTC |
| nyt-world | 49.1 | 3 | 2026-04-18 20:00 UTC |
| times-of-israel | 25.6 | 1 | 2026-04-18 20:24 UTC |

**#3 us-x-iran-permanent-peace-deal-by-april-22-2026** (2026-04-18 21:20 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international ⚠️ | 70.0 | 0 | n/a |
| al-jazeera | 20.7 | 4 | 2026-04-18 21:09 UTC |
| bbc-world | 10.2 | 1 | 2026-04-18 21:19 UTC |
| guardian-world | 59.3 | 1 | 2026-04-18 20:30 UTC |
| nyt-world ⚠️ | 70.0 | 0 | n/a |
| times-of-israel | 1.5 | 2 | 2026-04-18 21:28 UTC |

**#4 strait-of-hormuz-traffic-returns-to-normal-by-apri** (2026-04-19 00:00 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international ⚠️ | 70.0 | 0 | n/a |
| al-jazeera | 10.0 | 2 | 2026-04-19 00:00 UTC |
| bbc-world ⚠️ | 70.0 | 0 | n/a |
| guardian-world ⚠️ | 68.6 | 1 | 2026-04-18 23:01 UTC |
| nyt-world | 18.9 | 1 | 2026-04-18 23:51 UTC |
| times-of-israel ⚠️ | 70.0 | 0 | n/a |

**#5 will-the-iranian-regime-fall-by-june-30** (2026-04-18 22:30 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international | 42.4 | 1 | 2026-04-18 21:57 UTC |
| al-jazeera ⚠️ | 70.0 | 0 | n/a |
| bbc-world ⚠️ | 70.0 | 0 | n/a |
| guardian-world ⚠️ | 70.0 | 0 | n/a |
| nyt-world ⚠️ | 70.0 | 0 | n/a |
| times-of-israel | 51.8 | 1 | 2026-04-18 21:48 UTC |

**#6 will-spain-win-the-2026-fifa-world-cup-963** (2026-04-19 00:10 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international ⚠️ | 70.0 | 0 | n/a |
| al-jazeera | 20.0 | 2 | 2026-04-19 00:00 UTC |
| bbc-world ⚠️ | 70.0 | 0 | n/a |
| guardian-world ⚠️ | 70.0 | 0 | n/a |
| nyt-world | 28.9 | 1 | 2026-04-18 23:51 UTC |

**#7 will-the-us-confirm-that-aliens-exist-before-2027-** (2026-04-18 22:10 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international | 22.4 | 1 | 2026-04-18 21:57 UTC |
| al-jazeera ⚠️ | 70.0 | 0 | n/a |
| bbc-world ⚠️ | 60.2 | 1 | 2026-04-18 21:19 UTC |
| guardian-world ⚠️ | 70.0 | 0 | n/a |
| nyt-world ⚠️ | 70.0 | 0 | n/a |

**#8 will-the-us-confirm-that-aliens-exist-before-2027-** (2026-04-19 00:00 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international ⚠️ | 70.0 | 0 | n/a |
| al-jazeera | 10.0 | 2 | 2026-04-19 00:00 UTC |
| bbc-world ⚠️ | 70.0 | 0 | n/a |
| guardian-world ⚠️ | 68.6 | 1 | 2026-04-18 23:01 UTC |
| nyt-world | 18.9 | 1 | 2026-04-18 23:51 UTC |

**#9 us-obtains-iranian-enriched-uranium-by-may-31-396** (2026-04-18 22:50 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international ⚠️ | 62.4 | 1 | 2026-04-18 21:57 UTC |
| al-jazeera ⚠️ | 70.0 | 0 | n/a |
| bbc-world ⚠️ | 70.0 | 0 | n/a |
| guardian-world | 10.3 | 1 | 2026-04-18 22:49 UTC |
| nyt-world ⚠️ | 70.0 | 0 | n/a |
| times-of-israel | 13.3 | 1 | 2026-04-18 22:46 UTC |

**#10 us-obtains-iranian-enriched-uranium-by-april-30** (2026-04-18 23:20 UTC)

| feed | silent_min | items_in_window | last_pub |
|---|---|---|---|
| abc-international ⚠️ | 70.0 | 0 | n/a |
| al-jazeera ⚠️ | 70.0 | 0 | n/a |
| bbc-world ⚠️ | 70.0 | 0 | n/a |
| guardian-world | 28.6 | 2 | 2026-04-18 23:01 UTC |
| nyt-world ⚠️ | 70.0 | 0 | n/a |
| times-of-israel | 43.3 | 1 | 2026-04-18 22:46 UTC |

## Manual review

See `MANUAL_REVIEW_RUBRIC.md` for the six disqualifier checks that must be applied before any flag can be labeled `unexplained-by-monitored-feeds`. Fill `manual_verdict` in the `flagged_events` table per row. No verdict other than the ones specified in the rubric is admissible for the decision gate.

SQL for verdict entry:
```
UPDATE flagged_events SET manual_verdict = '<label>' WHERE id = <n>;
```