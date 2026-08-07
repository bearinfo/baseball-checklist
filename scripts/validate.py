#!/usr/bin/env python3
"""Validate every set in data/ against the standard. This is the point of the repo.

Run with no arguments to check everything, or pass set directories to check
only those. Exits non-zero on the first failing set so CI fails the PR.

    scripts/validate.py
    scripts/validate.py data/baseball/2026/2026-topps

Every failure names the file and, for row problems, the line number.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO / "schema"
DATA_DIR = REPO / "data"

REQUIRED_COLUMNS = ["card_number", "name", "team"]
OPTIONAL_COLUMNS = ["designations", "is_short_print", "variation_note"]
BOOLEAN = {"true", "false", ""}
MULTI = " / "


class Failures(list):
    def add(self, where, message):
        self.append(f"{where}: {message}")


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def check_rows(path, checklist, vocab, failures):
    """Row rules from schema/1.0/ROW-FORMAT.md."""
    rel = path.relative_to(REPO)
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = list(reader)

    unknown = [c for c in columns if c not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS]
    if unknown:
        failures.add(rel, f"column(s) not in the 1.0 row format: {unknown}")
    for column in REQUIRED_COLUMNS:
        if column not in columns:
            failures.add(rel, f"required column {column!r} is missing")
    if unknown or not all(c in columns for c in REQUIRED_COLUMNS):
        return

    if len(rows) != checklist["card_count"]:
        failures.add(rel, f"{len(rows)} rows but set.json declares "
                          f"card_count {checklist['card_count']}")

    seen = {}
    teamless_ok = checklist["kind"] not in ("base", "variation")
    for number, row in enumerate(rows, start=2):   # line 1 is the header
        where = f"{rel}:{number}"
        card_number = (row.get("card_number") or "").strip()
        name = (row.get("name") or "").strip()
        team = (row.get("team") or "").strip()

        if not card_number:
            failures.add(where, "card_number is empty")
        elif card_number in seen:
            failures.add(where, f"card_number {card_number!r} already used on "
                                f"line {seen[card_number]} of this file")
        else:
            seen[card_number] = number
        if not name:
            failures.add(where, "name is empty")
        if not team and not teamless_ok:
            failures.add(where, f"team is empty, which a {checklist['kind']} "
                                f"row may not be")

        # Split from the raw cell, not the stripped one: a teamless subject in
        # a multi-subject row is an empty component ("Moby Musician / Bryce
        # Harper" pairs with " / Philadelphia Phillies"), and stripping first
        # would collapse it and break the pairing.
        names = name.split(MULTI)
        teams = [t.strip() for t in (row.get("team") or "").split(MULTI)]
        if team and len(names) != len(teams):
            failures.add(where, f"{len(names)} name(s) but {len(teams)} team(s) "
                                f"— multi-subject rows pair them in order")
        for value in (teams if team else []):
            if not value:
                if not teamless_ok:
                    failures.add(where, f"empty team component, which a "
                                        f"{checklist['kind']} row may not have")
            elif value not in vocab["teams"]:
                failures.add(where, f"team {value!r} is not in data/baseball/teams.json")
        for code in (row.get("designations") or "").split():
            if code not in vocab["codes"]:
                failures.add(where, f"designation {code!r} is not in "
                                    f"schema/1.0/designations.json")
        flag = (row.get("is_short_print") or "").strip().lower()
        if flag not in BOOLEAN:
            failures.add(where, f"is_short_print {flag!r} is not true/false")


def check_set(set_dir, schemas, vocab, failures):
    """One set: metadata against the schema, then its rows."""
    import jsonschema

    set_path = set_dir / "set.json"
    rel = set_path.relative_to(REPO)
    if not set_path.exists():
        failures.add(set_dir.relative_to(REPO), "no set.json")
        return
    document = load_json(set_path)

    version = document.get("schema_version")
    if version not in schemas:
        failures.add(rel, f"schema_version {version!r} has no schema/ directory")
        return
    try:
        jsonschema.validate(document, schemas[version],
                            format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as error:
        location = "/".join(str(p) for p in error.absolute_path) or "(root)"
        failures.add(rel, f"{location}: {error.message}")
        return

    if document["slug"] != set_dir.name:
        failures.add(rel, f"slug {document['slug']!r} does not match the "
                          f"directory name {set_dir.name!r}")
    if document["verified"] and not document["provenance"]:
        failures.add(rel, "verified: true requires at least one source")

    parallels = document.get("parallels", [])
    declared = ({c["file"] for c in document["checklists"]} |
                {p["file"] for p in parallels if "file" in p})
    present = {str(p.relative_to(set_dir)) for p in set_dir.rglob("*.csv")}
    for missing in sorted(declared - present):
        failures.add(rel, f"declares {missing}, which does not exist")
    for stray in sorted(present - declared):
        failures.add(rel, f"{stray} exists but is not declared in checklists "
                          f"or parallels")

    counts = {c["file"]: c["card_count"] for c in document["checklists"]}
    for packaging in document.get("packagings", []):
        files = [entry["file"] for entry in packaging["contains"]]
        unknown = [f for f in files if f not in counts]
        repeated = sorted({f for f in files if files.count(f) > 1})
        if unknown:
            failures.add(rel, f"packaging {packaging['name']!r} contains "
                              f"{unknown}, not declared in checklists")
        if repeated:
            failures.add(rel, f"packaging {packaging['name']!r} lists "
                              f"{repeated} more than once")
        if not unknown and not repeated and "card_count" in packaging:
            total = sum(counts[f] for f in files)
            if total != packaging["card_count"]:
                failures.add(rel, f"packaging {packaging['name']!r} declares "
                                  f"{packaging['card_count']} cards but its "
                                  f"checklists hold {total}")

    for checklist in document["checklists"]:
        for tag in checklist.get("tags", []):
            if tag not in vocab["tags"]:
                failures.add(rel, f"{checklist['file']} is tagged {tag!r}, "
                                  f"which is not in schema/1.0/tags.json")

    numbers = {}
    for checklist in document["checklists"]:
        path = set_dir / checklist["file"]
        if path.exists():
            check_rows(path, checklist, vocab, failures)
            with open(path, newline="", encoding="utf-8") as handle:
                numbers[checklist["file"]] = [r.get("card_number", "")
                                              for r in csv.DictReader(handle)]

    names = {c["name"] for c in document["checklists"]}
    waves = {s["name"] for s in document.get("series", [])}

    # A parallel may print another parallel — Big Apple Gold prints the 100
    # cards of Big Apple — so applies_to names either array. That only reads
    # unambiguously while the two do not share a name.
    parallel_names = {p["name"] for p in parallels}
    for shared in sorted(names & parallel_names):
        failures.add(rel, f"{shared!r} names both a checklist and a parallel, "
                          f"so applies_to cannot say which is meant")

    # A colour is named once per parent — a dozen parallels are called Gold —
    # so a name only identifies a parallel while it is unique.
    repeated = {n for n in parallel_names
                if sum(1 for p in parallels if p["name"] == n) > 1}
    parents = {p["name"]: [t for t in p.get("applies_to", [])
                           if t in parallel_names] for p in parallels}
    for parallel in parallels:
        for target in parallel.get("applies_to", []):
            if target not in names and target not in parallel_names:
                failures.add(rel, f"parallel {parallel['name']!r} applies to "
                                  f"{target!r}, which this set declares as "
                                  f"neither a checklist nor a parallel")
            elif target in repeated and target not in names:
                failures.add(rel, f"parallel {parallel['name']!r} applies to "
                                  f"{target!r}, which names more than one "
                                  f"parallel of this set")
        # Walk up the parallel-of-a-parallel chain; a loop would otherwise
        # leave a card whose numbering is defined only in terms of itself.
        seen, walk = {parallel["name"]}, list(parents.get(parallel["name"], []))
        while walk:
            step = walk.pop()
            if step in seen:
                failures.add(rel, f"parallel {parallel['name']!r} applies to "
                                  f"itself through {step!r}")
                break
            seen.add(step)
            walk.extend(parents.get(step, []))
        # "not serial numbered" and "numbered to N" cannot both be true. The
        # rest of that claim rests on a person, like varies and coverage.
        if parallel.get("serial_numbered") is False and "print_run" in parallel:
            failures.add(rel, f"parallel {parallel['name']!r} is serial_numbered "
                              f"false but carries print_run "
                              f"{parallel['print_run']}")
        wave = parallel.get("series")
        if wave and wave not in waves:
            failures.add(rel, f"parallel {parallel['name']!r} is printed in "
                              f"{wave!r}, not a series this set declares")
        path = set_dir / parallel["file"] if "file" in parallel else None
        if path is None or not path.exists():
            continue
        check_rows(path, {"kind": "parallel",
                          "card_count": parallel["card_count"]},
                   vocab, failures)
        source = parallel["varies"]
        if source not in counts:
            failures.add(rel, f"parallel {parallel['name']!r} varies "
                              f"{source!r}, which this set does not declare")
            continue
        with open(path, newline="", encoding="utf-8") as handle:
            rows = [r.get("card_number", "") for r in csv.DictReader(handle)]
        known = set(numbers.get(source, []))
        for line, number in enumerate(rows, start=2):
            if number and number not in known:
                failures.add(f"{path.relative_to(REPO)}:{line}",
                             f"card_number {number!r} is not in {source} — a "
                             f"parallel cannot introduce a new card")
        # Rows exist to record WHICH cards got the treatment. When that is all
        # of them, the rows say nothing the source file does not already say.
        if known and set(rows) == known:
            failures.add(rel, f"parallel {parallel['name']!r} covers every "
                              f"card of {source} — declare it coverage: full "
                              f"and delete {parallel['file']}")

    # A variation is a second version of a card that already exists, so it
    # introduces no card numbers of its own. Enforcing that is what stops a
    # variation being counted as an extra card.
    for checklist in document["checklists"]:
        source = checklist.get("varies")
        if not source:
            continue
        if source not in counts:
            failures.add(rel, f"{checklist['file']} varies {source!r}, which "
                              f"this set does not declare")
            continue
        if source == checklist["file"]:
            failures.add(rel, f"{checklist['file']} varies itself")
            continue
        known = set(numbers.get(source, []))
        for line, number in enumerate(numbers.get(checklist["file"], []), start=2):
            if number and number not in known:
                failures.add(f"{(set_dir / checklist['file']).relative_to(REPO)}:{line}",
                             f"card_number {number!r} is not in {source} — a "
                             f"variation cannot introduce a new card")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sets", nargs="*", type=Path,
                        help="set directories to check; default is all of data/")
    args = parser.parse_args(argv)

    schemas = {p.name: load_json(p / "set.schema.json")
               for p in sorted(SCHEMA_DIR.iterdir()) if p.is_dir()}
    vocab = {
        "teams": set(load_json(DATA_DIR / "baseball/teams.json")["teams"]),
        "codes": set(load_json(SCHEMA_DIR / "1.0/designations.json")["codes"]),
        "tags": set(load_json(SCHEMA_DIR / "1.0/tags.json")["tags"]),
    }
    set_dirs = ([p.resolve() for p in args.sets] or
                sorted(p.parent for p in DATA_DIR.rglob("set.json")))
    outside = [p for p in set_dirs if REPO not in p.parents and p != REPO]
    if outside:
        print(f"not inside this repo: {outside[0]}")
        return 1
    if not set_dirs:
        print("no sets found under data/")
        return 1

    failures, rows, ids = Failures(), 0, {}
    for set_dir in set_dirs:
        before = len(failures)
        check_set(set_dir, schemas, vocab, failures)
        document = load_json(set_dir / "set.json") if (set_dir / "set.json").exists() else {}
        count = sum(c["card_count"] for c in document.get("checklists", []))
        rows += count

        # Every id is a permanent handle consumers key on, so no two records
        # anywhere in the repo may share one.
        rel = (set_dir / "set.json").relative_to(REPO)
        for kind, value in ([("set", document.get("id"))] +
                            [("packaging", p.get("id"))
                             for p in document.get("packagings", [])] +
                            [("parallel", p.get("id"))
                             for p in document.get("parallels", [])]):
            if not value:
                continue
            if value in ids:
                failures.add(rel, f"{kind} id {value} is already used by {ids[value]}")
            else:
                ids[value] = rel
        mark = "FAIL" if len(failures) > before else "ok  "
        print(f"{mark} {set_dir.relative_to(REPO)}  "
              f"({len(document.get('checklists', []))} checklists, {count} cards"
              f"{', verified' if document.get('verified') else ''})")

    print()
    if failures:
        for failure in failures:
            print(f"  {failure}")
        print(f"\n{len(failures)} problem(s) in {len(set_dirs)} set(s).")
        return 1
    print(f"{len(set_dirs)} set(s), {rows} cards: all valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
