"""Command line entry point: ``python -m dd1_rpc``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from pypresence.presence import Presence
from pypresence.exceptions import InvalidID

from .app import PresenceApp
from .saves import SaveReader, find_save_dir


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse simple ``KEY=value`` lines; missing or unreadable files give an empty dict."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        values[key] = value.strip().strip("\"'")
    return values


def default_client_id(env_file: Path = Path(".env")) -> str | None:
    """``CLIENT_ID`` from the environment, then from ``.env``; ``DD1_RPC_CLIENT_ID`` still works."""
    file_values = _read_env_file(env_file)
    for name in ("CLIENT_ID", "DD1_RPC_CLIENT_ID"):
        value = os.environ.get(name) or file_values.get(name)
        if value:
            return value
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd1-rpc", description="Discord Rich Presence for Darkest Dungeon (Steam)."
    )
    parser.add_argument(
        "--client-id",
        default=default_client_id(),
        help="Discord application client ID (or set CLIENT_ID in the environment or a .env file)",
    )
    parser.add_argument(
        "--save-dir",
        type=Path,
        help=r"Steam cloud save folder, e.g. ...\Steam\userdata\<id>\262060\remote (auto-detected by default)",
    )
    parser.add_argument("--interval", type=float, default=5.0, help="poll interval in seconds")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.client_id:
        parser.error("a Discord client ID is required (--client-id, or CLIENT_ID in the environment or .env)")
    save_dir = args.save_dir or find_save_dir()
    if save_dir is None or not save_dir.is_dir():
        parser.error("could not find the save folder; pass --save-dir")

    log = logging.getLogger("dd1_rpc")
    log.info("watching %s", save_dir)
    try:
        PresenceApp(SaveReader(save_dir), lambda: Presence(args.client_id)).run(args.interval)
    except InvalidID:
        log.error("Discord rejected the client ID %r", args.client_id)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
