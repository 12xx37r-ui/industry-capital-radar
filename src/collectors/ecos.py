"""한국은행 ECOS collector boundary."""
from __future__ import annotations

import os


def configured() -> bool:
    return bool(os.getenv("ECOS_API_KEY"))
