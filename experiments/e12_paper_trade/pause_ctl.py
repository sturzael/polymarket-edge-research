"""Manual pause/resume control for the daemon.

Usage:
    uv run python -m experiments.e12_paper_trade.pause_ctl status
    uv run python -m experiments.e12_paper_trade.pause_ctl pause
    uv run python -m experiments.e12_paper_trade.pause_ctl resume
    uv run python -m experiments.e12_paper_trade.pause_ctl set-protocol v1|v2

The daemon checks `daemon_state.paused` every loop tick. Pausing here takes
effect within POLL_INTERVAL_S (~2s).
"""
from __future__ import annotations

import argparse
import sys

from . import sidecar


def cmd_status() -> int:
    sidecar.init_db()
    paused = sidecar.is_paused()
    proto = sidecar.current_protocol_version()
    print(f"paused: {paused}")
    print(f"protocol_version: {proto}")
    return 0


def cmd_pause() -> int:
    sidecar.init_db()
    sidecar.set_state("paused", "1")
    print("paused=1")
    return 0


def cmd_resume() -> int:
    sidecar.init_db()
    sidecar.set_state("paused", "0")
    print("paused=0")
    return 0


def cmd_set_protocol(version: str) -> int:
    if version not in ("v1", "v2"):
        print(f"invalid version: {version}")
        return 2
    sidecar.init_db()
    sidecar.set_state("protocol_version", version)
    print(f"protocol_version={version}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("pause")
    sub.add_parser("resume")
    sp = sub.add_parser("set-protocol")
    sp.add_argument("version", choices=("v1", "v2"))
    args = p.parse_args()
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "pause":
        return cmd_pause()
    if args.cmd == "resume":
        return cmd_resume()
    if args.cmd == "set-protocol":
        return cmd_set_protocol(args.version)
    return 2


if __name__ == "__main__":
    sys.exit(main())
