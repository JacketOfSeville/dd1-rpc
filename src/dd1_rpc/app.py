"""Polling loop tying the game process, the saves and Discord together."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import psutil
from pypresence.exceptions import InvalidID

from .saves import SaveReader
from .state import Activity, Kind, build_activity, generic_activity

log = logging.getLogger(__name__)

GAME_PROCESS_NAMES = frozenset({"darkest.exe"})
# Discord rate-limits presence updates to one per 15 seconds.
MIN_UPDATE_INTERVAL = 15.0
RECONNECT_DELAY = 15.0


def _discard(rpc: Any) -> None:
    """Close a pypresence client, releasing its event loop even if it never connected."""
    try:
        rpc.close()
    except Exception:
        loop = getattr(rpc, "loop", None)
        if loop is not None and not loop.is_closed():
            loop.close()


def find_game_process() -> psutil.Process | None:
    for proc in psutil.process_iter(["name"]):
        name = proc.info["name"]
        if name and name.lower() in GAME_PROCESS_NAMES:
            return proc
    return None


def presence_payload(activity: Activity, start: int) -> dict[str, Any]:
    """Keyword arguments for ``Presence.update``; empty fields are omitted."""
    payload: dict[str, Any] = {
        "details": activity.details,
        "large_image": activity.large_image,
        "start": start,
    }
    if activity.state:
        payload["state"] = activity.state
    if activity.large_text:
        payload["large_text"] = activity.large_text
    if activity.small_image:
        payload["small_image"] = activity.small_image
        if activity.small_text:
            payload["small_text"] = activity.small_text
    return payload


class PresenceApp:
    def __init__(
        self,
        reader: SaveReader,
        rpc_factory: Callable[[], Any],
        find_process: Callable[[], psutil.Process | None] = find_game_process,
        clock: Callable[[], float] = time.time,
    ):
        self.reader = reader
        self.rpc_factory = rpc_factory
        self.find_process = find_process
        self.clock = clock
        self._rpc: Any = None
        self._next_connect_at = 0.0
        self.status = "Waiting for Darkest Dungeon"
        self._reset_session()

    def _reset_session(self) -> None:
        self._key: str | None = None
        self._started = 0
        self._sent: dict[str, Any] | None = None
        self._last_sent_at = float("-inf")
        self._game_pid: int | None = None

    def tick(self) -> None:
        """One poll: clear the presence if the game is gone, else sync it with the saves."""
        proc = self.find_process()
        if proc is None:
            self._on_game_closed()
            return

        if proc.pid != self._game_pid:
            self._reset_session()
            self._game_pid = proc.pid

        snapshot = self.reader.read()
        activity = (
            generic_activity()
            if snapshot is None
            else build_activity(snapshot.game, snapshot.raid, snapshot.campaign_log)
        )
        now = self.clock()
        if activity.key != self._key:
            first = self._key is None
            self._key = activity.key
            # Count the first Hamlet visit from game launch; later phases from the change.
            self._started = int(proc.create_time() if first and activity.kind != Kind.RAID else now)

        payload = presence_payload(activity, self._started)
        if payload != self._sent and now - self._last_sent_at >= MIN_UPDATE_INTERVAL:
            self._send(payload, now)
        self._update_status(activity)

    def _update_status(self, activity: Activity) -> None:
        if self._rpc is None:
            self.status = "Game running, waiting for Discord"
        else:
            self.status = f"Showing: {activity.details}"

    def _send(self, payload: dict[str, Any], now: float) -> None:
        rpc = self._ensure_connected(now)
        if rpc is None:
            return
        try:
            rpc.update(**payload)
        except Exception as exc:
            log.warning("Discord update failed (%r); will reconnect", exc)
            self._drop_connection(now)
            return
        log.info("presence: %s | %s", payload["details"], payload.get("state", ""))
        self._sent = payload
        self._last_sent_at = now

    def _ensure_connected(self, now: float) -> Any:
        if self._rpc is not None:
            return self._rpc
        if now < self._next_connect_at:
            return None
        rpc = self.rpc_factory()
        try:
            rpc.connect()
        except InvalidID:
            _discard(rpc)
            raise
        except Exception as exc:
            log.warning("Could not connect to Discord (%r); retrying later", exc)
            _discard(rpc)
            self._next_connect_at = now + RECONNECT_DELAY
            return None
        self._rpc = rpc
        log.info("connected to Discord")
        return rpc

    def _drop_connection(self, now: float) -> None:
        rpc, self._rpc = self._rpc, None
        self._sent = None
        self._next_connect_at = now + RECONNECT_DELAY
        if rpc is not None:
            _discard(rpc)

    def _on_game_closed(self) -> None:
        if self._game_pid is not None:
            log.info("game closed")
        self._reset_session()
        self.shutdown()
        self.status = "Waiting for Darkest Dungeon"

    def shutdown(self) -> None:
        """Clear the presence and disconnect."""
        rpc, self._rpc = self._rpc, None
        if rpc is None:
            return
        try:
            rpc.clear()
        except Exception as exc:
            log.debug("error while clearing presence: %r", exc)
        _discard(rpc)

    def run(self, interval: float = 5.0, stop: threading.Event | None = None) -> None:
        """Poll until interrupted, or until ``stop`` is set (used by the tray app)."""
        stop = stop or threading.Event()
        try:
            while not stop.is_set():
                self.tick()
                stop.wait(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()
