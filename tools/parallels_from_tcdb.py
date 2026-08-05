#!/usr/bin/env python3
"""Derive parallels[] declarations from a TCDB sub-collection listing.

TCDB publishes one sub-collection per parallel. The listing is a flat,
alphabetical list of names with no hierarchy and no card counts, so a
parallel's parent can only be read off its name, and its COVERAGE cannot be
read at all. This tool therefore emits `coverage: "unknown"` for everything it
derives: the source proves a parallel exists, and nothing more. Upgrading one
to `full` or `partial` needs a count, which a person supplies.

    tools/parallels_from_tcdb.py sample/2026-topps.txt \\
        data/baseball/2026/topps/2026-topps [--write]

Resolution is by longest-prefix match against the set's checklist names plus
the ALIAS table below, because TCDB and Topps name the same product
differently. Every name must land in exactly one bucket — a checklist of this
set, a parallel of one, a parallel of the base set, or an explicit skip. A name
that matches nothing aborts the run rather than being guessed at or dropped.

Re-running is safe: existing ids are matched by (name, applies_to) and kept, so
a permanent handle is never reissued.
"""
import argparse
import json
import re
import sys
import uuid
from pathlib import Path

ENTRY = re.compile(r'<a href="/ViewCollection\.cfm/sid/(\d+)[^"]*"[^>]*>\s*(.*?)\s*</a>',
                   re.S)
SERIES_SUFFIX = re.compile(r"\s*\((?:Series (?:One|Two))\)\s*$")

# TCDB's name for a product, mapped to this set's checklist name. Authored by
# hand: fuzzy matching pairs "Black Border" (a base parallel) with "Bulk Order"
# (an insert), so it is not trustworthy here. A key that maps a TCDB name onto
# a checklist exactly means "this entry IS that checklist", not a parallel of
# it; longer keys win, so listing both a product and its sub-product works.
ALIAS = {
    # TCDB brands the 1991 insert programme "35th Anniversary"; Topps does not.
    "1991 Topps Baseball 35th Anniversary": "1991 Topps Baseball",
    "1991 Topps Baseball 35th Anniversary All-Stars": "1991 Topps All Star Baseball",
    "1991 Topps Baseball 35th Anniversary Chrome": "1991 Topps Baseball Chrome Base Cards",
    "1991 Topps Baseball 35th Anniversary Chrome All-Stars":
        "1991 Topps Baseball All Star Chrome Base Cards",
    "1991 Topps Baseball 35th Anniversary Autographs":
        "1991 Topps Baseball Autograph Cards",
    "1991 Topps Baseball 35th Anniversary All-Stars Autographs":
        "1991 Topps Baseball All Star Autograph Cards",
    "1991 Topps Baseball 35th Anniversary Chrome Autographs":
        "1991 Topps Baseball Chrome Autograph Parallel",
    "1991 Topps Baseball 35th Anniversary Relics": "1991 Topps Baseball Relics",
    "1991 Topps Baseball 35th Anniversary All-Stars Relics":
        "1991 Topps Baseball All Star Relics",
    "Oversized 1991 Topps Baseball": "Oversized 1991 Topps Baseball",

    # Two TCDB spellings of one Topps checklist; both fold onto it.
    "75 Years of Topps Autographs Die Cut": "75 Years Of Topps Die Cut Autographs",
    "75 Years Of Topps Die-Cut Autographs": "75 Years Of Topps Die Cut Autographs",

    "Topps - Base Set": "Base",
    "Cover Athletes": "Cover Athletes Cards",
    "Cover Athletes Autographs": "Cover Athletes Autograph Cards",
    "City Connect Swatch Collection Relics": "City Connect Swatch Collection",
    "City Connect Swatch Collection Autographs Relics":
        "City Connect Swatch Collection Autograph Relic",
    "Flagship Collection": "The Flagship Collection Base Cards",
    "Flagship Collection Chrome": "The Flagship Collection Chrome Base Cards",
    "Flagship Real One Autographs": "Flagship Real One Autograph Cards",
    "Major League Materials Relics": "Major League Material Cards",
    "Major League Materials Autographs": "Major League Material Autograph Cards",
    "Major League Materials Dual Autographs Relics":
        "Major League Material Dual Autograph Cards",
    "Mascots Relics": "Mascot Relics",
    "Mascots Dynasty Autographs Patches": "Mascots Dynasty Autograph Patch",
    "Mascots Dynasty Autograph Patches": "Mascots Dynasty Autograph Patch",
    "Mascots Dynasty Dual Autographs Patches": "Mascots Dynasty Dual Autograph Patch",
    "Mascots Dynasty MLB Logo Autographs Patches":
        "Mascots Dynasty MLB Logo Autograph Patch",
    "Postseason Performance Autographs": "Postseason Performance Autograph Cards",
    "Profiles": "Topps Profiles",
    "Rounding the Bases Relics": "Rounding The Bases Relic",
    "Topps Flagship Autograph Patch": "Topps Flagship Autograph Patch Cards",
    "World Champion Autographs": "World Champion Autograph Cards",

    # Variations. TCDB prints "Variations" on some and omits it on others, so
    # the word cannot be used to detect them — Clear, Holiday, Team Color
    # Border, Vintage Stock and Big Apple Foil are variations named without it.
    "1952 Base Card Variations": "1952 Variation",
    "1952 Base Card Variations Autographs": "1952 Autograph Variation",
    "Golden Mirror Variations": "Golden Mirror Base Image Variation",
    "Golden Mirror Legend Variations": "Golden Mirror Legend Variation",
    "True Photo Variations": "True Photo Variation",
    "Big Apple Foil": "Big Apple Foil Variation",
    "Clear": "Clear Variation",
    "Holiday": "Holiday Variation",
    "Team Color Border": "Team Color Border Variation",
    "Vintage Stock": "Vintage Stock Variation",

    # "Swinging for the Stars" (TCDB) vs "Swinging With The Stars" (Topps PDF).
    # Same 25-card insert under a misremembered preposition.
    "Swinging for the Stars": "Swinging With The Stars",

    # "Home Field Advantage" (Series 1, 20) and "Home Field" (Series 2, 20) are
    # one 40-card insert; this repo already holds it as a single checklist.
    "Home Field Advantage": "Home Field",

    # Topps prints In The Name per series with the same codes on different
    # players, so this repo keeps two checklists where TCDB keeps one. A
    # parallel of it parallels both.
    "In The Name Relics": ["In The Name Relics Series 1",
                           "In The Name Relics Series 2"],
}

# Parallels of the base set. TCDB gives these no product prefix, which is the
# only thing marking them as base — so they are listed explicitly rather than
# inferred from "nothing else matched". A new name appearing here in a future
# dump must be classified by a person, not absorbed by a fallback.
BASE_PARALLELS = {
    "All-Star Game", "All-Star Game Black", "All-Star Game Gold",
    "All-Star Game Green", "All-Star Game Orange", "All-Star Game Platinum",
    "All-Star Game Red",
    "Aqua Holo Foil", "Aqua Rainbow Foil",
    "Black Border", "Black Diamante Foil", "Black Holo Foil",
    "Black Rainbow Foil", "Black Sandglitter",
    "Blue Holo Foil", "Blue Rainbow Foil",
    "Canadian Independence Day", "Canvas", "Cherry Blossoms",
    "Confetti", "Confetti Lime", "Confetti Pink",
    "Diamante Foil", "First Card", "FoilFractors",
    "Gold", "Gold Diamante Foil", "Gold Holo Foil", "Gold Rainbow Foil",
    "Gold Sandglitter",
    "Green Diamante Foil", "Green Holo Foil", "Green Rainbow Foil",
    "Holo Foil", "Independence Day", "Memorial Day Camo", "Opening Day Foil",
    "Orange Diamante Foil", "Orange Holo Foil", "Orange Rainbow Foil",
    "Orange Sandglitter", "Oversized 5x7",
    "Pink Diamante Foil", "Pink Holo Foil",
    "Printing Plates Black", "Printing Plates Cyan", "Printing Plates Magenta",
    "Printing Plates Yellow",
    "Purple Holo Foil", "Purple Rainbow Foil", "Rainbow Foil",
    "Red Diamante Foil", "Red Holo Foil", "Red Rainbow Foil", "Red Sandglitter",
    "Rose Gold Holo Foil", "Sandglitter", "Silver Crackle Foil",
    "Spring Training", "Spring Training Black", "Spring Training Gold",
    "Spring Training Green", "Spring Training Orange", "Spring Training Red",
    "Spring Training Rose Gold",
    "Tinsel Foil", "Topps Foil Pattern", "Wood",
    # Baseball Card Pedia lists this as a base parallel numbered to /75 in both
    # series, not a checklist this set is missing.
    "75 Years of Topps",
}

# TCDB entries that set.json already declares under a different name — Topps
# prints "<product> Autograph Parallel" where TCDB prints "<product>
# Autographs". Listed so the derived record folds onto the existing one instead
# of becoming a second declaration of the same parallel, which would give one
# card two permanent ids. Their colour runs are ordinary derived parallels of
# the parent checklist and are not listed here.
DECLARED = {
    "First Pitch Autographs": "First Pitch Autograph Parallel",
    "Mascots Autographs": "Mascots Autograph Parallel",
    "Rounding the Bases Relic Autographs":
        "Rounding The Bases Relic Autograph Parallel",
    "Flagship Collection Chrome Autographs":
        "The Flagship Collection Chrome Base Cards Autograph Parallel",
}

# Base parallels Baseball Card Pedia's insertion-ratio tables list in BOTH
# series at 350 cards each: 350 + 350 is the whole 700-card base set, so these
# are coverage: full, with the print run that source states. A parallel it
# lists in only ONE series covers just that wave's 350 and is deliberately
# absent here — half the base set is not full coverage, and this schema has no
# way yet to say "every card of Series 2", so those stay unknown rather than
# being rounded up. Canada Day is the sharpest case: 13 cards, not 350.
BASE_FACTS = {
    "Rainbow Foil": None, "Holo Foil": None, "Diamante Foil": None,
    "Sandglitter": None, "Aqua Rainbow Foil": None, "Aqua Holo Foil": None,
    "Pink Diamante Foil": None, "Topps Foil Pattern": None,
    "Silver Crackle Foil": None,
    "Gold": 2026, "Pink Holo Foil": 800,
    "Purple Rainbow Foil": 250, "Purple Holo Foil": 250,
    "Blue Rainbow Foil": 150, "Blue Holo Foil": 150,
    "Green Rainbow Foil": 99, "Green Holo Foil": 99, "Green Diamante Foil": 99,
    "Cherry Blossoms": 99, "Independence Day": 76, "Black Border": 75,
    "Gold Rainbow Foil": 50, "Gold Sandglitter": 50, "Gold Holo Foil": 50,
    "Gold Diamante Foil": 50, "Canvas": 50,
    "Orange Rainbow Foil": 25, "Orange Sandglitter": 25, "Orange Holo Foil": 25,
    "Orange Diamante Foil": 25, "Wood": 25, "Memorial Day Camo": 25,
    "Black Rainbow Foil": 10, "Black Sandglitter": 10, "Black Holo Foil": 10,
    "Black Diamante Foil": 10,
    "Red Rainbow Foil": 5, "Red Sandglitter": 5, "Red Holo Foil": 5,
    "Red Diamante Foil": 5,
    "FoilFractors": 1, "Rose Gold Holo Foil": 1,
    "Printing Plates Black": 1, "Printing Plates Cyan": 1,
    "Printing Plates Magenta": 1, "Printing Plates Yellow": 1,
}

# TCDB entries this set cannot place. Skipped deliberately and reported, never
# silently dropped: each is a product with no checklist here, or a name too
# ambiguous to assign without a count. A key also covers its parallels, so
# skipping a product skips its colour runs with it.
SKIP = {
    "Topps Collector Kit": "retail kit; no checklist in this set",
    "Super Box Companion Cards": "Super Box product; no checklist in this set",
    "Super Box Funko Bitty Pops!": "Super Box product; no checklist in this set",
    "Fanatics Authentic Memorabilia Redemptions": "redemption, not a card",
    "75 Years of Topps Gift Redemptions": "redemption, not a card",
    "Oversized Costco Flagship Collection": "Costco exclusive; no checklist here",
    "Flagship Collection Big Time Players": "no checklist in this set",
    "Flagship Collection Bulk Order": "distinct from the Bulk Order insert; unresolved",
    "Flagship Collection Chrome Highlight Reels": "no checklist in this set",
    "Funko": "ambiguous between Funko Base Cards and Funko Pop",
    "Funko Autographs": "ambiguous between Funko Pop Autograph Parallel and Funko",
    "": "TCDB publishes this sub-collection with an empty name (sid 595144)",
}


def parse_listing(path):
    entries = []
    for sid, name in ENTRY.findall(Path(path).read_text(encoding="utf-8")):
        entries.append((sid, name.replace("&amp;", "&").strip()))
    if not entries:
        sys.exit(f"{path}: no sub-collection links found")
    return entries


def strip_series(name):
    """2026 Topps is one brand-year set, so a per-series split collapses."""
    return SERIES_SUFFIX.sub("", name).strip()


def longest_prefix(name, keys):
    """The longest key that is `name` itself or a whole-word prefix of it."""
    lowered = name.lower()
    best = None
    for key in keys:
        low = key.lower()
        if lowered == low:
            return key
        if lowered.startswith(low + " ") and (best is None or len(key) > len(best)):
            best = key
    return best


def build(entries, document):
    names = {c["name"] for c in document["checklists"]}
    for source, alias in ALIAS.items():
        for target in (alias if isinstance(alias, list) else [alias]):
            if target not in names:
                sys.exit(f"ALIAS maps {source!r} to {target!r}, "
                         f"which this set does not declare")
    targets = {name: name for name in names}
    targets.update(ALIAS)

    already = {p["name"] for p in document.get("parallels", [])}
    for source, target in DECLARED.items():
        if target not in already:
            sys.exit(f"DECLARED maps {source!r} to {target!r}, "
                     f"which set.json does not declare")

    # One namespace, longest match wins, so a skipped product cannot swallow a
    # longer alias that names a real checklist ("75 Years of Topps" vs "75
    # Years of Topps Autographs Die Cut").
    routes = {key: ("skip", why) for key, why in SKIP.items()}
    routes.update({key: ("checklist", value) for key, value in targets.items()})

    derived, skipped, is_checklist, declared, unresolved = {}, [], [], [], []
    for sid, raw in entries:
        name = strip_series(raw)
        if name in DECLARED:
            declared.append((sid, raw, DECLARED[name]))
            continue
        if name in BASE_PARALLELS:
            target, parallel = ["Base"], name
        else:
            key = longest_prefix(name, routes) if name else ""
            if key is None:
                unresolved.append((sid, raw))
                continue
            route, value = routes[key]
            if route == "skip":
                skipped.append((sid, raw, value))
                continue
            target = value if isinstance(value, list) else [value]
            parallel = "" if len(name) == len(key) else name[len(key) + 1:].strip()
            if not parallel:
                is_checklist.append((sid, raw, target))
                continue
        key = (parallel.lower(), tuple(target))
        derived.setdefault(key, {"name": parallel, "targets": target, "sids": []})
        derived[key]["sids"].append(sid)
    return derived, skipped, is_checklist, declared, unresolved


def apply_base_facts(record):
    """Coverage and print run for a base parallel, where a source states them."""
    if record.get("applies_to") != ["Base"] or record["name"] not in BASE_FACTS:
        return False
    run = BASE_FACTS[record["name"]]
    before = (record.get("coverage"), record.get("print_run"),
              record.get("one_of_one"))
    record["coverage"] = "full"
    if run == 1:
        record["one_of_one"] = True
        record.pop("print_run", None)
    elif run:
        record["print_run"] = run
        record["serial_numbered"] = True
    return before != (record.get("coverage"), record.get("print_run"),
                      record.get("one_of_one"))


def declarations(derived, document):
    """Merge onto what set.json already declares, keeping every existing id."""
    existing = {}
    for parallel in document.get("parallels", []):
        for target in parallel.get("applies_to", [None]):
            existing[(parallel["name"].lower(), target)] = parallel

    out = list(document.get("parallels", []))
    added, retargeted, upgraded = 0, [], []
    for key in sorted(derived, key=lambda k: (k[1], k[0])):
        item = derived[key]
        matches = [existing[(key[0], t)] for t in item["targets"]
                   if (key[0], t) in existing]
        if matches:
            # A correction to ALIAS can widen or narrow what a parallel covers.
            # Carry it onto the record already declared rather than leaving a
            # stale applies_to behind, and never mint a second id for it.
            parallel = matches[0]
            if apply_base_facts(parallel):
                upgraded.append(parallel["name"])
            if parallel.get("applies_to") != item["targets"]:
                retargeted.append((parallel["name"],
                                   parallel.get("applies_to"), item["targets"]))
                parallel["applies_to"] = item["targets"]
            continue
        record = {
            "id": str(uuid.uuid4()),
            "name": item["name"],
            "coverage": "unknown",
            "applies_to": item["targets"],
        }
        apply_base_facts(record)
        out.append(record)
        added += 1
    return out, added, retargeted, upgraded


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("listing", help="TCDB sub-collection listing (HTML fragment)")
    parser.add_argument("set_dir", type=Path, help="set directory holding set.json")
    parser.add_argument("--write", action="store_true",
                        help="update set.json; omit to report only")
    args = parser.parse_args(argv)

    set_path = args.set_dir / "set.json"
    document = json.loads(set_path.read_text(encoding="utf-8"))
    entries = parse_listing(args.listing)
    derived, skipped, is_checklist, declared, unresolved = build(entries, document)

    print(f"{len(entries)} sub-collection(s) in the listing")
    print(f"  {len(is_checklist):>4} are checklists of this set")
    print(f"  {len(declared):>4} are parallels set.json already declares")
    print(f"  {len(derived):>4} parallels after collapsing series splits")
    print(f"  {len(skipped):>4} skipped deliberately")
    for sid, raw, why in skipped:
        print(f"         {raw or '(empty name)'} — {why}  [sid {sid}]")

    if unresolved:
        print(f"\n{len(unresolved)} name(s) match nothing. Add each to ALIAS, "
              f"BASE_PARALLELS or SKIP — never guess:")
        for sid, raw in unresolved:
            print(f"  {raw}  https://www.tcdb.com/ViewCollection.cfm/sid/{sid}")
        return 1

    parallels, added, retargeted, upgraded = declarations(derived, document)
    print(f"\n{added} new declaration(s); "
          f"{len(parallels) - added} already declared")
    if upgraded:
        print(f"  {len(upgraded)} base parallel(s) upgraded to coverage: full")
    for name, was, now in retargeted:
        print(f"  retargeted {name!r}: {was} -> {now}")
    if not args.write:
        print("Nothing written (no --write).")
        return 0

    document["parallels"] = parallels
    set_path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"wrote {set_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
