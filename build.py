"""Build ``dist\dd1-rpc.exe`` with the client ID from ``.env`` baked in.

Usage: ``python build.py`` (needs pystray, pillow and pyinstaller). A ``.env`` file or
``CLIENT_ID`` at runtime still overrides the baked-in value.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

from dd1_rpc.__main__ import default_client_id  # noqa: E402

BAKED = ROOT / "src" / "dd1_rpc" / "_baked.py"


def main() -> int:
    client_id = default_client_id(ROOT / ".env")
    if not client_id:
        print("CLIENT_ID not found in the environment or .env", file=sys.stderr)
        return 1
    work = Path(tempfile.gettempdir()) / "dd1build"
    BAKED.write_text(f"CLIENT_ID = {client_id!r}\n", encoding="utf-8")
    try:
        return subprocess.call(
            [
                sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole", "--name", "dd1-rpc",
                "--paths", str(ROOT / "src"), "--hidden-import", "dd1_rpc._baked",
                "--distpath", str(ROOT / "dist"), "--workpath", str(work), "--specpath", str(work),
                str(ROOT / "tray_launcher.py"),
            ],
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )
    finally:
        BAKED.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
