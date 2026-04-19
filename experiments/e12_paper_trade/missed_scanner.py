"""Periodic worker — populates `missed_opportunities`.

For each sports market that resolved in the last 60 min, look at trades that
happened in the post-resolution window. Compute total capturable USD at our
max entry cap. Cross-reference against our `detections` and `position_context`.

Categorize each missed market into:
  - 'no_detection'       — we never saw it (slow-poll problem)
  - 'cap_too_tight'      — we saw it but ask was above all our caps
  - 'attempted_no_fill'  — we tried but got 0 shares
  - 'partial_fill'       — we got < requested

For v1 we use a simplified heuristic: match by market_slug.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from . import config, gamma_client, sidecar

logger = logging.getLogger(__name__)

WINDOW_MIN = 60                  # how far back to scan for resolutions
LOOKBACK_DETECTION_HOURS = 4     # how far back our detections might be relevant


async def run_once() -> dict:
    sidecar.init_db()
    print("[missed_scanner] running...")
    out = {"checked": 0, "logged": 0}
    resolved = await gamma_client.fetch_recently_resolved_sports_markets(limit=200)
    if not resolved:
        return out
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MIN)
    for m in resolved:
        ct_raw = getattr(m, "closed_time", None) or getattr(m, "closedTime", None)
        if not ct_raw:
            continue
        try:
            ct = datetime.fromisoformat(str(ct_raw).replace("Z", "+00:00"))
        except Exception:
            continue
        if ct < cutoff:
            continue
        out["checked"] += 1

        # Did we ever detect this slug?
        with sidecar.conn() as c:
            det_row = c.execute(
                """SELECT id, best_ask, ask_size, ts FROM detections
                   WHERE market_slug = ? ORDER BY ts ASC LIMIT 1""",
                (m.slug,),
            ).fetchone()
            pos_rows = c.execute(
                "SELECT pm_trade_id FROM position_context WHERE market_slug = ?",
                (m.slug,),
            ).fetchall()

        # Pull last_trade_price as best-price-observed proxy
        ltp = float(getattr(m, "last_trade_price", 0) or 0)
        # Capturable size unknown without book history; use a placeholder
        capturable = 0.0

        if not det_row:
            sidecar.log_missed_opportunity(
                market_slug=m.slug, event_id=str(getattr(m, "event_id", "") or "") or None,
                detected_via="post_facto_scan",
                arb_window_start_ts=ct.isoformat(),
                arb_window_end_ts=(ct + timedelta(minutes=30)).isoformat(),
                best_price_observed=ltp,
                total_capturable_usd=capturable,
                reason_we_missed="no_detection",
            )
            out["logged"] += 1
        elif not pos_rows:
            best_ask = float(det_row["best_ask"] or 0)
            reason = "cap_too_tight" if best_ask > max(config.ENTRY_TARGET_CAPS) else "attempted_no_fill"
            sidecar.log_missed_opportunity(
                market_slug=m.slug, event_id=str(getattr(m, "event_id", "") or "") or None,
                detected_via="post_facto_scan",
                arb_window_start_ts=ct.isoformat(),
                arb_window_end_ts=(ct + timedelta(minutes=30)).isoformat(),
                best_price_observed=best_ask,
                total_capturable_usd=capturable,
                reason_we_missed=reason,
                our_detection_id=det_row["id"],
            )
            out["logged"] += 1
        # If pos_rows exists, we filled — not a miss.
    return out


async def run_periodic(interval_s: int = 300):
    while True:
        try:
            res = await run_once()
            print(f"[missed_scanner] checked={res['checked']} logged={res['logged']}")
        except Exception as e:
            logger.warning(f"missed_scanner error: {e}")
        await asyncio.sleep(interval_s)


if __name__ == "__main__":
    asyncio.run(run_once())
