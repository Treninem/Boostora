from __future__ import annotations

from app import bot as core_runtime
from app.webapp_v4 import start_webapp_server_v4


def run() -> None:
    """Run the proven bot core with the v4 Mini App gateway enabled.

    The indirection keeps the existing Telegram polling/background subsystem intact
    while the new gateway can be rolled back independently if deployment requires it.
    """
    core_runtime.start_webapp_server = start_webapp_server_v4
    core_runtime.run()
