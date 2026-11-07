"""Paths shared by source and packaged Sortrr."""
import os
import sys
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent
FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else RESOURCES


def data_directory():
    override = os.environ.get("SORTRR_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if FROZEN and os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(local) / "Sortrr"
    return APP_DIR / "data"
