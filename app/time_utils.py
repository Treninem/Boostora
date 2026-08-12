from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return naive UTC for compatibility with existing SQLite timestamp strings.

    ``datetime.utcnow()`` is deprecated in modern Python.  Boostora historically
    stores UTC timestamps without an offset, so this helper deliberately keeps
    that representation while obtaining the clock from an aware UTC datetime.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
