"""Generic utility functions shared across modules."""
import re


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _as_int(value, default=0, minimum=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    if minimum is not None:
        n = max(minimum, n)
    return n


def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _icon_key(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())
