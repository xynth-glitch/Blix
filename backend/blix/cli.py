"""Blix command-line entrypoint for operational tasks.

Usage:
    blix init-db                     Create PostGIS extension + tables
    blix import-static [--dir PATH]  Download (or use PATH) + import static GTFS
    blix poll-once                   Fetch real-time vehicle positions once
    blix poll-rt                     Run the real-time poller loop
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import structlog

from blix.db import init_db, session_scope
from blix.ingestion.rt_poller import poll_once, run_forever
from blix.ingestion.static_importer import import_gtfs_dir
from blix.providers import get_provider

log = structlog.get_logger(__name__)


def _cmd_init_db(_: argparse.Namespace) -> int:
    init_db()
    log.info("db.init.done")
    return 0


def _cmd_import_static(args: argparse.Namespace) -> int:
    init_db()
    if args.dir:
        gtfs_dir = Path(args.dir)
    else:
        provider = get_provider(args.provider)
        gtfs_dir = provider.fetch_static_gtfs(Path(tempfile.mkdtemp(prefix="blix-gtfs-")))
    with session_scope() as session:
        counts = import_gtfs_dir(session, gtfs_dir)
    log.info("import.static.done", counts=counts)
    return 0


def _cmd_poll_once(args: argparse.Namespace) -> int:
    count = poll_once(get_provider(args.provider))
    log.info("poll.once.done", count=count)
    return 0


def _cmd_poll_rt(_: argparse.Namespace) -> int:
    run_forever()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blix", description="Blix operational CLI")
    parser.add_argument("--provider", default="delhi-otd", help="Provider id")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=_cmd_init_db)

    p_import = sub.add_parser("import-static", help="Import static GTFS")
    p_import.add_argument("--dir", help="Path to an extracted GTFS dir (skips download)")
    p_import.set_defaults(func=_cmd_import_static)

    sub.add_parser("poll-once").set_defaults(func=_cmd_poll_once)
    sub.add_parser("poll-rt").set_defaults(func=_cmd_poll_rt)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
