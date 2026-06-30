"""Shared helpers for the army-builder test suite.

Conventions (match the rest of the repo): standalone runnable scripts, no
pytest, no new runtime deps. Each test file defines ``run()`` returning the
number of failures and ends with ``sys.exit(run())`` so ``run_all.py`` can drive
them as subprocesses. Engine checks read the live store and pure functions and
need no server. API/golden/fuzz checks use an in-process Flask test client
against an isolated copy of ``collection.db``.

Feature detection: this suite is written to the full Phase 1-6 contract but runs
cleanly against a tree where later phases are absent. Anything Phase 5/6 (allies,
duplicate_cap, core stratagems, army rules, missions, export/import) is probed
first and SKIPPED with a reason if not present, rather than failing.
"""
import os
import sys
import shutil
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


class Reporter:
    """Collects ok / fail / skip lines and prints a summary."""

    def __init__(self, title):
        self.title = title
        self.fail = 0
        self.passed = 0
        self.skipped = 0
        print(f"\n=== {title} ===")

    def check(self, label, cond, detail=""):
        if cond:
            self.passed += 1
            print(f"ok   {label}")
        else:
            self.fail += 1
            print(f"XX   {label}" + (f"  --  {detail}" if detail else ""))
        return cond

    def skip(self, label, reason):
        self.skipped += 1
        print(f"--   {label}  (skipped: {reason})")

    def summary(self):
        tail = f"  [{self.skipped} skipped]" if self.skipped else ""
        if self.fail:
            print(f"\n{self.fail} FAILED, {self.passed} passed{tail}  -- {self.title}")
        else:
            print(f"\nALL PASS ({self.passed} checks){tail}  -- {self.title}")
        return self.fail


_STORE = None


def store():
    global _STORE
    if _STORE is None:
        import data_store
        _STORE = data_store.get_store()
    return _STORE


def has(obj, name):
    """True if a symbol exists (and, for store methods, is non-empty-ish)."""
    return getattr(obj, name, None) is not None


def name_index():
    """{datasheet name -> id} for resolving units by name in tests."""
    return {v["name"]: k for k, v in store().ds_by_id.items()}


def faction_index():
    """{faction name -> id}."""
    return {v["name"]: k for k, v in store().faction_by_id.items()}


def did(name):
    i = name_index()
    if name not in i:
        raise KeyError(f"no datasheet named {name!r}")
    return i[name]


def fid(name):
    i = faction_index()
    if name not in i:
        raise KeyError(f"no faction named {name!r}")
    return i[name]


# ----- in-process client against an isolated DB --------------------------------
# Must be called BEFORE importing app/db: db.py reads COLLECTION_DB_PATH at import.

_TMP_DB = None


def use_isolated_db():
    """Point COLLECTION_DB_PATH at a throwaway copy of collection.db. Returns the
    temp path. Call before importing app. Idempotent within a process."""
    global _TMP_DB
    if _TMP_DB:
        return _TMP_DB
    src = os.path.join(REPO, "collection.db")
    fd, tmp = tempfile.mkstemp(prefix="test_collection_", suffix=".db")
    os.close(fd)
    if os.path.exists(src):
        shutil.copy2(src, tmp)
    os.environ["COLLECTION_DB_PATH"] = tmp
    _TMP_DB = tmp
    return tmp


def drop_isolated_db():
    global _TMP_DB
    if _TMP_DB and os.path.exists(_TMP_DB):
        try:
            os.remove(_TMP_DB)
        except OSError:
            pass
    _TMP_DB = None


def client():
    """Flask test client (in-process). The Flask object is app.app here."""
    use_isolated_db()
    import app
    return app.app.test_client()


def json_of(resp):
    try:
        return resp.get_json()
    except Exception:
        return None


def army_id_from(payload):
    """Pull an army id out of a create/import response of unknown exact shape."""
    if not isinstance(payload, dict):
        return None
    for k in ("id", "army_id", "army_list_id"):
        if k in payload and payload[k]:
            return payload[k]
    inner = payload.get("army") or payload.get("army_list")
    if isinstance(inner, dict):
        for k in ("id", "army_id", "army_list_id"):
            if k in inner and inner[k]:
                return inner[k]
    return None
