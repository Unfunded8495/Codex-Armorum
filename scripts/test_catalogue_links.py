"""Contract test for catalogue_links: locks the two-halves rule so a dropped
is_render_excluded guard or a fallen-through no_current_datasheet fails loudly.

The fixture deliberately includes the cases that drifted across the old copies:
an exclude record, a mark_accessory record, and a no_current_datasheet record
that still carries raw datasheet_links (the live data has 9 of these).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import catalogue_links as cl


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


RAW = {"datasheet_links": [{"datasheet_id": "uuid-A"}, {"datasheet_id": "uuid-B"}]}


def test_exclude_half():
    for action in ("exclude", "mark_accessory", "mark_box_product"):
        check(cl.is_render_excluded({"action": action}), f"{action} must be excluded")
    for action in ("no_current_datasheet", "link_datasheet", "defer", "add_alias", ""):
        check(not cl.is_render_excluded({"action": action}),
              f"{action} must NOT be excluded")
    check(not cl.is_render_excluded({}), "missing resolution must NOT be excluded")
    check(not cl.is_render_excluded(None), "None resolution must NOT be excluded")


def test_link_half():
    # no_current_datasheet is kept-but-empty even when raw links are present.
    check(cl.effective_link_ids(RAW, {"action": "no_current_datasheet"}) == [],
          "no_current_datasheet must yield [] despite raw links")
    # resolution pins win, raw links ignored.
    for action in ("link_datasheet", "link_multiple_datasheets"):
        res = {"action": action, "datasheet_ids": ["uuid-X", "uuid-Y", ""]}
        check(cl.effective_link_ids(RAW, res) == ["uuid-X", "uuid-Y"],
              f"{action} must use resolution ids and drop empties")
    # no resolution / passthrough actions fall back to raw links.
    check(cl.effective_link_ids(RAW, {}) == ["uuid-A", "uuid-B"], "no resolution -> raw")
    check(cl.effective_link_ids(RAW, {"action": "defer"}) == ["uuid-A", "uuid-B"],
          "defer -> raw")
    check(cl.effective_link_ids(RAW, None) == ["uuid-A", "uuid-B"], "None -> raw")
    check(cl.effective_link_ids({}, {}) == [], "no links -> []")


if __name__ == "__main__":
    test_exclude_half()
    test_link_half()
    print("OK: catalogue_links contract (exclude half + link half) holds.")
