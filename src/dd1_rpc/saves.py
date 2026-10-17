# Locating and reading Darkest Dungeon's save files
from __future__ import annotations

import logging
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import dson

log = logging.getLogger(__name__)

APP_ID = "262060"
GAME_FILE = "persist.game.json"
RAID_FILE = "persist.raid.json"
CAMPAIGN_LOG_FILE = "persist.campaign_log.json"

# Errors raised when the game is midway through writing a file.
_PARTIAL_READ_ERRORS = (OSError, dson.DsonError, struct.error, KeyError, IndexError, UnicodeDecodeError)


@dataclass(frozen=True)
class Snapshot:
    """Decoded saves of the active profile. Optional parts are None when unavailable."""

    game: dict[str, Any]
    raid: dict[str, Any] | None = None
    campaign_log: dict[str, Any] | None = None


def steam_path() -> Path | None:
    """Steam's install directory, from the registry on Windows."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except (ImportError, OSError):
        pass
    fallback = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"
    return fallback if fallback.is_dir() else None


def find_save_dir() -> Path | None:
    """The Steam cloud save folder of the most recently played Steam account."""
    steam = steam_path()
    if steam is None:
        return None
    candidates = [p for p in (steam / "userdata").glob(f"*/{APP_ID}/remote") if p.is_dir()]
    return max(candidates, key=_newest_mtime, default=None)


def active_profile(save_dir: Path) -> Path | None:
    """The profile folder whose game save was written most recently."""
    profiles = [p for p in save_dir.glob("profile_*") if (p / GAME_FILE).is_file()]
    return max(profiles, key=lambda p: (p / GAME_FILE).stat().st_mtime_ns, default=None)


def raid_path(profile: Path, game: dict[str, Any]) -> Path | None:
    """Where the current raid is saved: the folder named by ``raid_save``, else the profile root."""
    candidates = []
    raid_save = game.get("raid_save")
    if isinstance(raid_save, str):
        # The game stores plot raid folders with a trailing slash, e.g. ``plot_crimson_court_2/``.
        raid_save = raid_save.strip().rstrip("/\\")
        if raid_save not in ("", ".", "..") and Path(raid_save).name == raid_save:
            candidates.append(profile / raid_save / RAID_FILE)
    candidates.append(profile / RAID_FILE)
    return next((p for p in candidates if p.is_file()), None)


class SaveReader:
    """Reads the active profile, reparsing a file only when it changed on disk."""

    def __init__(self, save_dir: Path):
        self.save_dir = save_dir
        self._cache: dict[Path, tuple[tuple[int, int], dict[str, Any]]] = {}

    def read(self) -> Snapshot | None:
        profile = active_profile(self.save_dir)
        if profile is None:
            return None
        game = self._load(profile / GAME_FILE)
        if game is None:
            return None

        in_raid = bool(game.get("inraid")) and game.get("raiddungeon", "none") != "none"
        if in_raid:
            raid_file = raid_path(profile, game)
            return Snapshot(game=game, raid=self._load(raid_file) if raid_file else None)
        return Snapshot(game=game, campaign_log=self._load(profile / CAMPAIGN_LOG_FILE))

    def _load(self, path: Path) -> dict[str, Any] | None:
        try:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            cached = self._cache.get(path)
            if cached and cached[0] == signature:
                return cached[1]
            data = dson.load(path)
        except _PARTIAL_READ_ERRORS as exc:
            # Fall back to the last good copy; the next poll will retry.
            log.debug("could not read %s: %r", path, exc)
            cached = self._cache.get(path)
            return cached[1] if cached else None
        self._cache[path] = (signature, data)
        return data


def _newest_mtime(path: Path) -> int:
    return max((p.stat().st_mtime_ns for p in path.rglob("*") if p.is_file()), default=0)
