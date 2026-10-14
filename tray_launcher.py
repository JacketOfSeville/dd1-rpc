"""PyInstaller entry point (the package's own modules use relative imports)."""

import sys

from dd1_rpc.tray import main

sys.exit(main())
