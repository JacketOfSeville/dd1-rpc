"""System tray front end: ``python -m dd1_rpc.tray`` or the packaged ``dd1-rpc.exe``."""

from __future__ import annotations

import ctypes
import importlib
import logging
import os
import sys
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from pypresence.exceptions import InvalidID
from pypresence.presence import Presence

from .__main__ import default_client_id
from .app import PresenceApp
from .saves import SaveReader, find_save_dir

TITLE = "Darkest Dungeon Rich Presence"
POLL_INTERVAL = 5.0


def baked_client_id() -> str | None:
    """The client ID compiled in by ``build.py`` (a generated, git-ignored ``_baked`` module)."""
    try:
        module = importlib.import_module("dd1_rpc._baked")
    except ImportError:
        return None
    value = getattr(module, "CLIENT_ID", None)
    return value if isinstance(value, str) and value else None


def app_dir() -> Path:
    """The folder holding the ``.exe`` when packaged, else the current folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _message(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, text, TITLE, 0x10)


def make_icon() -> Image.Image:
    """A small torch flame on a dark disc."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, size - 2, size - 2), fill=(28, 22, 20, 255), outline=(120, 30, 30, 255), width=3)
    draw.polygon([(32, 10), (46, 32), (42, 46), (32, 52), (22, 46), (18, 32)], fill=(214, 120, 24, 255))
    draw.polygon([(32, 26), (39, 38), (36, 47), (32, 49), (28, 47), (25, 38)], fill=(250, 214, 96, 255))
    return image


def main() -> int:
    folder = app_dir()
    logging.basicConfig(
        filename=folder / "dd1-rpc.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("dd1_rpc")

    client_id = default_client_id(folder / ".env") or baked_client_id()
    if not client_id:
        _message(f"No Discord client ID found.\n\nPut CLIENT_ID=<your id> in a .env file in:\n{folder}")
        return 1
    save_dir = find_save_dir()
    if save_dir is None or not save_dir.is_dir():
        _message("Could not find the Darkest Dungeon save folder.")
        return 1

    app = PresenceApp(SaveReader(save_dir), lambda: Presence(client_id))
    stop = threading.Event()

    def quit_app(icon: pystray.Icon, _item: object = None) -> None:
        stop.set()
        icon.stop()

    def open_saves(_icon: pystray.Icon, _item: object) -> None:
        os.startfile(save_dir)

    icon = pystray.Icon(
        "dd1-rpc",
        make_icon(),
        TITLE,
        menu=pystray.Menu(
            pystray.MenuItem(lambda _item: app.status[:80], None, enabled=False),
            pystray.MenuItem("Open save folder", open_saves),
            pystray.MenuItem("Quit", quit_app),
        ),
    )

    def worker() -> None:
        try:
            app.run(POLL_INTERVAL, stop)
        except InvalidID:
            log.error("Discord rejected the client ID")
            _message("Discord rejected the client ID. Check CLIENT_ID in your .env file.")
            icon.stop()
        except Exception:
            log.exception("presence loop crashed")
            _message(f"The presence loop crashed. See {folder / 'dd1-rpc.log'}")
            icon.stop()

    def refresh() -> None:
        while not stop.wait(2.0):
            icon.title = f"{TITLE}\n{app.status}"[:127]
            icon.update_menu()

    def setup(icon: pystray.Icon) -> None:
        icon.visible = True
        threading.Thread(target=worker, daemon=True).start()
        threading.Thread(target=refresh, daemon=True).start()

    log.info("watching %s", save_dir)
    icon.run(setup)
    stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
