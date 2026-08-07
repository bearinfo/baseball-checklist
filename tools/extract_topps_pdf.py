#!/usr/bin/env python3
"""Convert a Topps checklist PDF into ROW-FORMAT 1.0 CSV files.

A converter, not part of the standard: it produces candidate rows for human
review. The vocabularies it needs — team names and designation codes — come
from the checked-in files, never from this script.

It handles the layouts Topps actually ships, which differ per product:

    "1 Shohei Ohtani Los Angeles Dodgers®"   Series 1/2: number, space, name
    "1Aaron Judge New York Yankees®"         Complete Set: number glued to name
    BASE SET                                 sometimes a header, sometimes not
    BASE CARD SHORT PRINT ROOKIES            a section reusing base numbers

Rules enforced here (see schema/1.0/ROW-FORMAT.md):
- one row per CARD: lines repeating a card number (League Leaders print one
  line per player) merge into a single row, names/teams joined with " / "
- trademark glyphs stripped from team names
- printed designation tails map to controlled codes from designations.json
- a line that cannot be parsed deterministically ABORTS the run (never guess);
  the only permitted repair is exact rightmost-subsequence removal of a known
  team name, which fixes pdfplumber frame-interleaving without inventing text

Usage:
    tools/extract_topps_pdf.py <checklist.pdf> <set-directory>
"""
import argparse
import os
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Printed designation tails -> ordered codes. A tail not listed here aborts the
# run rather than being dropped: an unknown designation is new information.
PRINTED_TAILS = {
    "": [],
    "Rookie": ["RC"],
    "Future Stars": ["FS"],
    "All-Star Rookie": ["RCUP"],
    "League Leaders": ["LL"],
    "Team Card": ["TC"],
    "Combo Card": ["CC"],
    "Combo Cards": ["CC"],
    "Combo Card/Checklist": ["CC", "CL"],
    "Future Star": ["FS"],
    "Checklist": ["CL"],
}

# Headers that announce a kind rather than naming a section of their own.
KIND_MARKERS = {"BASE", "BASE SET", "BASE CARD SET", "BASE COMPLETE SET"}

# A card line starts with its card number, which is TEXT and not always
# numeric: "1", "US300", "GN-1", "MLMA-AB" and "YTA-VW" are all card numbers.
# Two printed shapes, tried in this order:
#   "1Aaron Judge ..."      Complete Set: digits glued to the name
#   "MLMA-AB Alex Bregman"  everything else: number, space, name
# A number token must contain a digit or a hyphen, which is what separates it
# from the first word of a name.
GLUED_NUMBER = re.compile(r"^(\d+)([^\W\d_].*)$")
SPACED_NUMBER = re.compile(r"^#?\s*([A-Za-z0-9][A-Za-z0-9.\-_]*)\s+(.+)$")


def number_style(lines):
    """Whether this document glues the card number to the name.

    Decided per document rather than per line, because the two shapes are not
    distinguishable on their own: "698JJ Wetherholt" is card 698, while
    "91A-ABB Jim Abbott" is card 91A-ABB. Numbers carrying a hyphen are
    unambiguous and sit out the vote.
    """
    glued = spaced = 0
    for line in lines:
        token = line.split(" ", 1)[0]
        if "-" in token or "_" in token:
            continue
        if re.match(r"^\d+\s", line):
            spaced += 1
        elif re.match(r"^\d+[A-Za-z]", line):
            glued += 1
    return ("glued" if glued > spaced else "spaced"), glued, spaced


def split_number(line, style):
    """(card_number, remainder) or None."""
    match = SPACED_NUMBER.match(line)
    # A hyphen or underscore marks the whole token as the card number —
    # "MLMA-AB", "91A-ABB", "C-9" — whatever the document's style.
    if match and re.search(r"[-_]", match.group(1)):
        return match.group(1), match.group(2)
    if style == "glued":
        glued = GLUED_NUMBER.match(line)
        if glued:
            return glued.group(1), glued.group(2)
    if match and re.search(r"\d", match.group(1)):
        return match.group(1), match.group(2)
    return None

# Editorial furniture: the cover title (which reads as a card number), the
# standing disclaimer, and page numbers.
# The cover title reads as a card number: "2026 Topps Series 2 Baseball" is
# card #2026 by shape. Only honoured on page 1, so a real card that starts with
# a year — "1991 Topps Baseball" is an insert — is never mistaken for it.
TITLE_LINE = re.compile(r"^(19|20)\d{2}\s+Topps\b.*\b(baseball|checklist)\b",
                        re.IGNORECASE)
FURNITURE = re.compile(
    r"^(checklists provided\b.*|\*?\s*subject to change\s*\*?|page \d+|\d+)$",
    re.IGNORECASE)

# How the cards were distributed. Printed between sections, and true of the
# section that follows rather than of any card.
# A distribution note is recognised by how it ENDS, never by how it starts.
# Matching a leading keyword swallowed real content: every "MEGA-1 Mike Trout"
# row parsed as a distribution line, because \b sits between MEGA and the
# hyphen, and the section header "TOKYO NIGHTS" did too, so its 35 cards fell
# into the section above it. Every distribution Topps prints ends in one of
# these words; a card row does not.
DISTRIBUTION = re.compile(
    r".*\b(only|exclusive|exclusives|boxtopper|boxloader)\s*$",
    re.IGNORECASE)


def strip_trademarks(text):
    """Drop trademark marks, which Topps prints as glyphs or as letters."""
    text = text.replace("®", "").replace("™", "")
    return re.sub(r"\s*\((?:TM|R)\)", "", text, flags=re.IGNORECASE).strip()


def load_vocab():
    teams = json.loads((REPO / "data/baseball/teams.json").read_text())["teams"]
    codes = json.loads((REPO / "schema/1.0/designations.json").read_text())["codes"]
    for tail, mapped in PRINTED_TAILS.items():
        for code in mapped:
            if code not in codes:
                sys.exit(f"designation map uses {code!r}, not in designations.json")
    return sorted(teams, key=len, reverse=True)


def remove_subsequence_rightmost(text, sub):
    """Remove `sub` from `text` as a RIGHTMOST character subsequence, or None.

    Repairs pdfplumber frame-interleaving. The team text overlaps the end of
    the line, so each character must bind as far right as possible; only an
    exact full-subsequence match is accepted, so the repair is deterministic.
    """
    keep = list(text)
    j = len(sub) - 1
    for i in range(len(text) - 1, -1, -1):
        if j >= 0 and text[i] == sub[j]:
            keep[i] = None
            j -= 1
    if j >= 0:
        return None
    result = "".join(ch for ch in keep if ch is not None)
    # Removing characters out of the middle of a real word leaves a gap:
    # "Wade Boggs Tampa Bay Devil Rays" minus "Tampa Bay Rays" reads
    # "Wade Boggs  Devil". That is a mangling, not a repair — the team is
    # simply missing from teams.json — so refuse it.
    if "  " in result:
        return None
    return result


def split_name_team(rest, teams):
    """(name, team, codes) from the part of a card line after its number."""
    unknown_tail = None
    for team in teams:  # normal case: the team name is a plain substring
        idx = rest.rfind(team)
        if idx >= 0:
            tail = rest[idx + len(team):].strip()
            name = rest[:idx].strip()
            # Team cards print the team as the subject too:
            # "34Kansas City Royals Kansas City Royals Team Card"
            if not name and tail == "Team Card":
                name = team
            if name and tail in PRINTED_TAILS:
                return name, team, PRINTED_TAILS[tail]
            if name and tail and unknown_tail is None:
                unknown_tail = tail
    # A team was found and the words after it are not a designation this
    # converter knows. That is new information, not a corrupt line, and the
    # repair below would happily invent a name out of it: removing "New York
    # Mets" as a subsequence from "Pete Alonso New York Mets Combo Cards"
    # takes letters out of the tail and yields "Pete Alonso s Combo Card".
    if unknown_tail is not None:
        sys.exit(f"unknown printed tail {unknown_tail!r} (aborting, never "
                 f"guess): add it to PRINTED_TAILS if it is a designation — "
                 f"{rest!r}")
    for team in teams:  # repair case: the team text is interleaved into the line
        repaired = remove_subsequence_rightmost(rest, team)
        if repaired is None:
            continue
        repaired = repaired.strip()
        # A repair has to drop the designation off the end too, or the tail
        # ends up inside the player's name.
        for tail, codes in PRINTED_TAILS.items():
            if tail and repaired.endswith(tail):
                name = repaired[:-len(tail)].strip()
                if name and " " in name:
                    print(f"  repaired interleaved line: name={name!r} "
                          f"team={team!r} tail={tail!r}", file=sys.stderr)
                    return name, team, codes
        if " " in repaired:
            print(f"  repaired interleaved line: name={repaired!r} "
                  f"team={team!r}", file=sys.stderr)
            return repaired, team, []
    return None


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def canonical(name):
    """One name for a program Topps prints inconsistently across series.

    Series 1 prints "Clear Variation", Series 2 "Base Cards Clear Variation";
    "True Photo Variation" becomes "True Photo Variations"; 2024 Series 1
    misspells its own header as "Topps Reverence Autogaph Patch Cards" where
    Series 2 spells it correctly. Only these mechanical drifts are normalised —
    a genuinely different printed name (Series 1 "Vintage Stock" vs Series 2
    "Vintage Stock Retro") stays its own section, because merging those would
    be a guess.
    """
    name = re.sub(r"^Base Cards?\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\bAutogaph\b", "Autograph", name, flags=re.IGNORECASE)
    return re.sub(r"Variations$", "Variation", name, flags=re.IGNORECASE).strip()


class Section:
    def __init__(self, name, kind, short_print=False, distribution="", page=0):
        self.name = name
        self.kind = kind
        self.short_print = short_print
        self.distribution = distribution
        self.page = page
        self.cards = []

    FOLDERS = {"insert": "inserts", "variation": "variations",
               "parallel": "parallels", "autograph": "autographs",
               "relic": "relics"}

    @property
    def file(self):
        if self.kind == "base":
            return "base.csv"
        return f"{self.FOLDERS[self.kind]}/{slugify(self.name)}.csv"

    def add(self, number, name, team, codes):
        if self.cards and self.cards[-1]["card_number"] == number:
            self.cards[-1]["names"].append(name)   # another subject, same card
            self.cards[-1]["teams"].append(team)
            return
        self.cards.append({"card_number": number, "names": [name],
                           "teams": [team], "codes": codes})


KIND_KEYWORDS = [("AUTOGRAPH RELIC", "relic"), ("AUTOGRAPH", "autograph"),
                 ("RELIC", "relic"), ("INSERT", "insert")]

# Sections a checklist PDF prints that are not cards of this set: sweepstakes
# prizes, gift cards, and vintage cards re-inserted from other sets. Skipped
# wholesale and reported — never parsed into rows.
NON_CARD_SECTION = re.compile(r"\b(GIFTS?|REDEMPTION|BUYBACK|PRIZE|"
                              r"SWEEPSTAKES|EXPERIENCE)\b")


def classify(header, kind_context):
    """What kind of section a printed header announces.

    `kind_context` is the last standalone kind marker seen ("INSERT",
    "AUTOGRAPH"...), which Topps prints once above a run of sections.
    """
    upper = header.upper()
    if upper in KIND_MARKERS:
        return "Base", "base", False
    if "SHORT PRINT" in upper:
        return titlecase(header), "variation", True
    if "VARIATION" in upper:
        return titlecase(header), "variation", False
    if "PARALLEL" in upper:
        return titlecase(header), "parallel", False
    return titlecase(header), kind_context, False


KEEP_UPPER = {"MLB", "AL", "NL", "RC", "SP", "SSP", "HR", "RBI", "ERA", "OPS", "US",
              "II", "III", "IV"}


def titlecase(name):
    out = []
    for word in name.split():
        if word.upper() in KEEP_UPPER:
            out.append(word.upper())
        elif word.isupper() and len(word) > 1:
            out.append(word.capitalize())
        else:
            out.append(word)
    return " ".join(out)


def read_sections(pdf_path, teams):
    import pdfplumber

    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for raw in (page.extract_text() or "").splitlines():
                text = re.sub(r"\s+", " ", raw).strip()
                if text:
                    lines.append((page_no, text))

    style, glued, spaced = number_style([text for _, text in lines])
    print(f"{os.path.basename(str(pdf_path))}: card numbers are {style} "
          f"({glued} glued / {spaced} spaced lines)", file=sys.stderr)

    sections, current = [], None
    kind_context, distribution, skipping = "insert", "", None
    skipped, teamless = [], 0
    for page_no, line in lines:
        if FURNITURE.match(line) or (page_no == 1 and TITLE_LINE.match(line)):
            continue

        # A header is set in full caps. Checked before card shape because a
        # header may start with digits — "1990 TOPPS BASEBALL AUTOGRAPH CARDS".
        if line.isupper():
            standalone = [k for text, k in KIND_KEYWORDS if line == text]
            if standalone:
                kind_context = standalone[0]   # applies to the sections below
                continue
            if DISTRIBUTION.match(line):
                distribution = line            # applies to the section below
                continue
            if NON_CARD_SECTION.search(line):
                skipping, current = line, None
                skipped.append((page_no, line))
                continue
            skipping = None
            name, kind, short_print = classify(line, kind_context)
            current = Section(name, kind, short_print, distribution, page_no)
            sections.append(current)
            distribution = ""
            continue
        if skipping:
            continue                           # body of a non-card section
        if DISTRIBUTION.match(line):
            distribution = line
            continue

        split = split_number(line, style)
        if not split:
            continue                           # not a card and not a header
        number, rest = split
        rest = strip_trademarks(rest)
        parsed = split_name_team(rest, teams)
        if current is None:
            # Cards before any header: the checklist starts straight in.
            current = Section("Base", "base", page=page_no)
            sections.append(current)
        if parsed is None:
            # No known team. Base and variation cards always carry one, so
            # there the line is corrupt and the run stops. Inserts and
            # autographs genuinely include teamless subjects — mascots,
            # celebrities, box toppers — which are emitted with team empty.
            if current.kind in ("base", "variation") or not rest:
                sys.exit(f"page {page_no}: UNPARSEABLE (aborting, never guess): {line!r}")
            teamless += 1
            parsed = (rest, "", [])
        current.add(number, *parsed)

    if skipped:
        print(f"skipped {len(skipped)} non-card section(s):", file=sys.stderr)
        for page_no, name in skipped:
            print(f"    p{page_no}: {name}", file=sys.stderr)
    if teamless:
        print(f"note: {teamless} row(s) printed without a team (emitted with "
              f"team empty; not allowed in base/variation)", file=sys.stderr)
    empty = [s for s in sections if not s.cards]
    if empty:
        print(f"note: {len(empty)} header(s) carried no rows:", file=sys.stderr)
        for s in empty:
            print(f"    p{s.page}: {s.name}", file=sys.stderr)
    return [s for s in sections if s.cards]


def write_section(section, set_dir):
    path = set_dir / section.file
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["card_number", "name", "team", "designations"]
    if section.short_print:
        columns.append("is_short_print")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        for card in section.cards:
            row = [card["card_number"], " / ".join(card["names"]),
                   " / ".join(card["teams"]), " ".join(card["codes"])]
            if section.short_print:
                row.append("true")
            writer.writerow(row)
    return path


def merge(per_pdf):
    """Combine sections from several PDFs of one set into one section each.

    A set issued in waves — Series 1 and Series 2 of the same year — is one
    set: base #1-350 and #351-700 are one 700-card checklist. Sections combine
    by canonical name. A card number in more than one source is either the
    same card listed twice (kept once — never a duplicate row) or two
    different cards sharing a code; those sections cannot be one file, so they
    stay per series, the way TCDB also keeps them ("... (Series One)").
    """
    def series_tag(label, index):
        found = re.search(r"[Ss]eries[_ ]?(\d)", label) or \
                re.search(r"[-_][sS](\d)\b", label)
        return f"Series {found.group(1) if found else index}"

    groups = {}
    for label, sections in per_pdf:
        for section in sections:
            key = (section.kind, canonical(section.name))
            groups.setdefault(key, []).append((label, section))

    result = []
    for (kind, name), group in groups.items():
        first = group[0][1]
        first.name = name
        first.sources = [group[0][0]]
        if len(group) == 1:
            result.append(first)
            continue
        cards = {c["card_number"]: c for c in first.cards}
        clean, duplicates = True, 0
        for label, section in group[1:]:
            for card in section.cards:
                previous = cards.get(card["card_number"])
                if previous is None:
                    cards[card["card_number"]] = card
                elif (previous["names"] == card["names"]
                        and previous["teams"] == card["teams"]
                        and previous["codes"] == card["codes"]):
                    duplicates += 1
                else:
                    clean = False
            first.short_print = first.short_print or section.short_print
        if clean:
            first.cards = list(cards.values())
            first.sources = [label for label, _ in group]
            if duplicates:
                print(f'  "{name}": {duplicates} row(s) listed identically in '
                      f'more than one source, kept once', file=sys.stderr)
            result.append(first)
        else:
            print(f'  "{name}" ({kind}): same code, different cards across '
                  f'sources — kept per series', file=sys.stderr)
            for index, (label, section) in enumerate(group, start=1):
                section.name = f"{name} {series_tag(label, index)}"
                section.sources = [label]
                result.append(section)
    return result


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdfs", nargs="+", help="one or more checklist PDFs of the same set")
    parser.add_argument("-o", "--out", help="output set directory; omit to only list")
    parser.add_argument("--kinds", default="",
                        help="comma-separated kinds to write, e.g. base,variation")
    args = parser.parse_args(argv)

    teams = load_vocab()
    wanted = [k.strip() for k in args.kinds.split(",") if k.strip()]
    per_pdf = []
    for path in args.pdfs:
        sections = read_sections(path, teams)
        # Filter before merging: a conflict in a section nobody asked for must
        # not block the ones in scope.
        per_pdf.append((Path(path).name,
                        [s for s in sections if not wanted or s.kind in wanted]))
    sections = merge(per_pdf) if len(per_pdf) > 1 else per_pdf[0][1]
    for section in sections:
        if not hasattr(section, "sources"):
            section.sources = [per_pdf[0][0]]

    print(f"\n{len(sections)} section(s) with rows:")
    total = 0
    for section in sorted(sections, key=lambda s: (s.kind != "base", s.file)):
        if args.out:
            write_section(section, Path(args.out))
        total += len(section.cards)
        print(f'  {section.kind:<10}{len(section.cards):>5} cards  '
              f'{section.file:<50}{len(section.sources)} source(s)  '
              f'{section.distribution}')
    print(f"\n{total} rows in scope{'' if wanted else ' (all kinds)'}."
          f"{'' if args.out else ' Nothing written (no -o).'}")
    if args.out:
        print("Declare each written file in set.json; card_count must match.")
        print("parallels/*.csv go in parallels[] as coverage: partial, not in "
              "checklists[] — and only if the list really is partial.")


if __name__ == "__main__":
    main(sys.argv[1:])
