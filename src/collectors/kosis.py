"""KOSIS collector boundary."""
from __future__ import annotations

import os


def configured() -> bool:
    return bool(os.getenv("KOSIS_API_KEY"))
