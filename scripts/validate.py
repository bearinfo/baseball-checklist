#!/usr/bin/env python3
"""Validate every set in data/ against the standard. This is the point of the repo.

Run with no arguments to check everything, or pass set directories to check
only those. Exits non-zero on the first failing set so CI fails the PR.

    scripts/validate.py
    scripts/validate.py data/baseball/2026/topps/2026-topps

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

        names, teams = name.split(MULTI), team.split(MULTI)
        if team and len(names) != len(teams):
            failures.add(where, f"{len(names)} name(s) but {len(teams)} team(s) "
                                f"— multi-subject rows pair them in order")
        for value in (teams if team else []):
            if value not in vocab["teams"]:
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

    declared = {c["file"] for c in document["checklists"]}
    present = {str(p.relative_to(set_dir)) for p in set_dir.rglob("*.csv")}
    for missing in sorted(declared - present):
        failures.add(rel, f"declares {missing}, which does not exist")
    for stray in sorted(present - declared):
        failures.add(rel, f"{stray} exists but is not declared in checklists")

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
        path = set_dir / checklist["file"]
        if path.exists():
            check_rows(path, checklist, vocab, failures)


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
                             for p in document.get("packagings", [])]):
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
