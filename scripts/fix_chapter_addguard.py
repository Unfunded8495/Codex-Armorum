import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_store import get_store

s = get_store()
# Map name -> canonical datasheet id (the ["id"] field), NOT the dict key: the
# add-guard compares the normalized did (= ds_by_id[did]["id"]) against the
# {u["id"]} selectable set, so keying the test on ["id"] mirrors the guard and
# avoids a false negative if a sheet happens to have an alias key.
NAME = {v["name"]: v["id"] for v in s.ds_by_id.values()}
fail = 0

def check(label, cond):
    global fail
    print(f"{'ok ' if cond else 'XX '} {label}")
    fail += 0 if cond else 1

# Every chapter offers a non-empty selectable set (the generics it inherits).
chapters = [f for f in s.factions if s.is_chapter_faction(f["id"])]
check(f"found chapter factions ({len(chapters)})", len(chapters) >= 1)
for f in chapters:
    sel = {u["id"] for u in s.selectable_units_for_army(f["id"])}
    check(f"{f['name']}: selectable set non-empty ({len(sel)})", len(sel) > 0)

# Concrete Ultramarines case: gains parent generics, still excludes other chapters.
ult = next(f["id"] for f in s.factions if f["name"] == "Ultramarines")
sel = {u["id"] for u in s.selectable_units_for_army(ult)}
check("Ultramarines selectable includes Intercessor Squad (parent generic)",
      NAME["Intercessor Squad"] in sel)
check("Ultramarines selectable includes Tactical Squad (parent generic)",
      NAME["Tactical Squad"] in sel)
check("Ultramarines selectable EXCLUDES Death Company Marines (other chapter)",
      NAME["Death Company Marines"] not in sel)

print("ALL PASS" if not fail else f"{fail} FAILED")
sys.exit(1 if fail else 0)
