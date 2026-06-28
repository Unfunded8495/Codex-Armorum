"""The single definition of how a catalogue record maps to datasheet links.

The "effective datasheet ids for a record" rule has two halves, and *both* had
drifted across the five-plus places that re-implemented it:

  - the exclude half: which resolution actions drop the record from the rendered
    catalogue. ``catalogue_faction_datasheet_index`` and the old gap-finder folded
    ``no_current_datasheet`` into their exclude set; ``catalogue_payload`` and
    ``_catalogue_models_by_datasheet`` did not.
  - the link half: which datasheet ids a kept record contributes. The existing
    ``reresolve_catalogue_faction._runtime_link_ids`` encoded this correctly but
    carried no exclude guard, so an excluded record passed to it fell through to
    its raw links.

Centralising only the link half would have left the exclude half duplicated, so
both live here. The contract is: a consumer calls :func:`is_render_excluded`
first and drops the record if true, then calls :func:`effective_link_ids` on the
records that survive. :func:`effective_link_ids` *assumes* the record is not
excluded.

This module has no app imports so scripts (the verifier, the reresolve pass) can
use it without the ``data_store`` / ``factions_theme`` render chain.
"""
from __future__ import annotations

# Resolution actions that drop a record from the rendered catalogue entirely.
RENDER_EXCLUDED_ACTIONS = frozenset({"exclude", "mark_accessory", "mark_box_product"})

# Actions where the resolution's pinned datasheet_ids replace the raw links.
_LINK_ACTIONS = frozenset({"link_datasheet", "link_multiple_datasheets"})


def is_render_excluded(resolution) -> bool:
    """True when the record should be dropped from the rendered catalogue.

    Call this BEFORE :func:`effective_link_ids`, which assumes the record is not
    excluded. ``no_current_datasheet`` is deliberately NOT here: such a record
    still renders, it just contributes no links (see :func:`effective_link_ids`).
    """
    return (resolution or {}).get("action", "") in RENDER_EXCLUDED_ACTIONS


def effective_link_ids(record, resolution) -> list:
    """Datasheet ids a non-excluded ``record`` effectively links to.

      - ``link_datasheet`` / ``link_multiple_datasheets``: the resolution's
        pinned ``datasheet_ids`` win (the user narrowed the model to those).
      - ``no_current_datasheet``: kept-but-empty -> ``[]``.
      - otherwise (including no resolution): the record's raw ``datasheet_links``.

    Assumes ``is_render_excluded(resolution)`` is ``False``.
    """
    action = (resolution or {}).get("action", "")
    if action in _LINK_ACTIONS:
        return [d for d in (resolution.get("datasheet_ids") or []) if d]
    if action == "no_current_datasheet":
        return []
    return [link["datasheet_id"]
            for link in (record or {}).get("datasheet_links", [])
            if link.get("datasheet_id")]
