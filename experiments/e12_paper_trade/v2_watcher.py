"""V2 cutover watcher — orchestrates the snapshot → pause → verify → resume
sequence around 2026-04-22.

Run in its own tmux pane alongside the daemon:
    uv run python -m experiments.e12_paper_trade.v2_watcher

Sequence (UTC):
  09:25 2026-04-22 → run v2_migration.py snapshot (5 min before auto-pause)
  09:30 2026-04-22 → daemon auto-pauses (handled inside daemon.py)
  10:00 2026-04-23 → run v2_migration.py verify
                     - if CLEAN: set daemon_state.paused = 0; daemon resumes
                     - if BREAKING: keep paused; print remediation steps; re-try every 6h
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from . import config, sidecar, v2_migration

logger = logging.getLogger("e12.v2_watcher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

SNAPSHOT_AT = config.V2_CUTOVER_PAUSE_AT - timedelta(minutes=5)   # 09:25 UTC
VERIFY_AT = config.V2_CUTOVER_RESUME_NO_EARLIER_THAN              # 10:00 UTC +1d
RETRY_VERIFY_EVERY_HOURS = 6


async def sleep_until(target: datetime) -> None:
    while True:
        now = datetime.now(timezone.utc)
        delta = (target - now).total_seconds()
        if delta <= 0:
            return
        chunk = min(delta, 600)  # wake every 10 min so we can log liveness
        logger.info(f"sleeping {chunk:.0f}s; target={target.isoformat()}, now={now.isoformat()}")
        await asyncio.sleep(chunk)


async def main() -> int:
    sidecar.init_db()
    now = datetime.now(timezone.utc)
    logger.info(f"v2_watcher up. snapshot_at={SNAPSHOT_AT}, verify_at={VERIFY_AT}, now={now}")

    # Stage 1: snapshot
    if now < SNAPSHOT_AT:
        await sleep_until(SNAPSHOT_AT)
    if not (config.HERE / "data" / "v2_pre_snapshot.json").exists():
        logger.info("running v2_migration snapshot")
        await v2_migration.snapshot()
    else:
        logger.info("snapshot file already exists; skipping")

    # Stage 2: wait for verify window
    if datetime.now(timezone.utc) < VERIFY_AT:
        await sleep_until(VERIFY_AT)

    # Stage 3: verify (retry on breaking until clean or operator intervenes)
    while True:
        logger.info("running v2_migration verify")
        rc = await v2_migration.verify()
        if rc == 0:
            sidecar.set_state("paused", "0")
            sidecar.set_state("protocol_version", "v2")
            logger.info("V2 verify CLEAN — daemon will resume on next loop iteration")
            return 0
        logger.warning(
            f"V2 verify reports BREAKING — daemon stays paused. "
            f"Inspect data/v2_post_verify.json. Per plan §V2 cutover plan §4, "
            f"if shift is real and persistent, treat V1-only sample as canonical."
        )
        logger.info(f"retrying in {RETRY_VERIFY_EVERY_HOURS}h")
        await asyncio.sleep(RETRY_VERIFY_EVERY_HOURS * 3600)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
