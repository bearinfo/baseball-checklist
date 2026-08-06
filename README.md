# baseball-checklist

Baseball card checklists as data: curated, version-controlled, schema-validated,
and free for any program to consume.

This repo is **inert data with a specification**. It contains no code that writes
into any application — consumers pull from it and convert on their own side.

```
schema/1.0/set.schema.json     the specification for set.json
schema/1.0/ROW-FORMAT.md       the row standard (frozen for 1.0)
schema/1.0/designations.json   controlled vocabulary: RC, FS, LL, TC, CC, CL, RCUP
schema/1.0/tags.json           controlled vocabulary for checklist categories
data/baseball/teams.json       closed list of valid team names
data/baseball/<year>/<manufacturer>/<set-slug>/
    set.json                   identity, provenance, series, packagings, parallels
    base.csv                   the base checklist
    variations/*.csv           cards sharing base numbering (short prints, photo variations)
    inserts/*.csv  autographs/*.csv  relics/*.csv
    parallels/*.csv            rows of partial parallels only, declared by parallels[]
scripts/validate.py            enforcement; CI runs it on every PR
tools/                         converters from published sources to this format
```

## What a checklist looks like

```csv
card_number,name,team,designations
1,Aaron Judge,New York Yankees,
11,Pete Alonso / Kyle Schwarber / Juan Soto,New York Mets / Philadelphia Phillies / New York Mets,LL
47,Arizona Diamondbacks,Arizona Diamondbacks,TC
60,Rhett Lowder,Cincinnati Reds,FS
```

Three columns are required — `card_number`, `name`, `team` — plus optional
`designations`, `is_short_print` and `variation_note`. Full rules in
[schema/1.0/ROW-FORMAT.md](schema/1.0/ROW-FORMAT.md).

CSV for rows and JSON for set metadata, deliberately: correcting one name in a
700-row checklist must produce a **one-line diff**. That review property is the
point of the repo.

## Principles

1. **Stable opaque IDs.** Every set carries a permanent UUID independent of its
   name and path, so renaming never orphans a record. Consumers key on the UUID.
2. **Names as printed, never resolved identities.** No person IDs, no Chadwick
   IDs, no third-party identifier space. Identity resolution belongs to the
   consumer; pinning it here would mean two sources of truth.
3. **Checklists only.** No prices, no ownership, no valuations.
4. **Never guess.** A source line that cannot be parsed deterministically stops
   the conversion with its line number. Nothing is silently skipped or invented.
5. **Provenance is required.** Every set records where its rows came from, as a
   list — agreement between independent sources is the strongest verification
   available, and `verified: true` without a source fails validation.
6. **Closed vocabularies.** Team names and designation codes come from
   checked-in lists and grow by PR with evidence of the printed form.
7. **No manufacturer PDFs in this repo.** Only the derived factual rows.

## Modelling

A set is **one brand-year**, not one product. *2026 Topps* is a single 700-card
set issued in two waves — Series 1 (#1-350) and Series 2 (#351-700) — recorded in
`series`.

A **packaging** is a way the set was sold as a whole — a factory set, a team set,
a box set. It lists checklists that already exist, so it is never a separate set
and never duplicates rows:

```json
"packagings": [{
  "id": "92793a4e-b1b5-46d9-9383-22afc2880a03",
  "name": "Factory Set",
  "type": "factory-set",
  "contains": [
    { "file": "base.csv" },
    { "file": "variations/short-print-rookies.csv", "exclusive": true }
  ],
  "card_count": 704
}]
```

Three things earn their place there. A packaging carries its own **permanent
UUID**, because a sealed factory set is a thing a collector owns and catalogues,
not just a label. **`exclusive`** answers the question that actually decides a
purchase — *which of these cards can I get no other way?* Here the 700 base
cards are the same ones pulled from Series 1 and 2 packs, and only the four
short-print rookies are unique to the box. And `contains` holds **objects rather
than filenames**, so a team set — a packaging holding part of a checklist — can
gain a card-number selector later without breaking anything already published.

**`base.csv` is the source of every card number in a set.** A variation is a
second version of a card that already exists — the same number, whatever is
printed on it. The subject may differ entirely: 2026 Topps prints Kevin
McGonigle on the short-print #697 where the base card is Bryan Reynolds. Both
are real cards, so both are rows, in separate files.

Every variation declares what it varies, and validation rejects any variation
number absent from that file:

```json
{ "file": "variations/short-print-rookies.csv", "kind": "variation",
  "varies": "base.csv", "card_count": 4 }
```

That is what keeps a variation from being counted as an extra card — the 2026
Topps set has 700 card numbers and 2,115 variation rows, and not one of those
rows adds a number.

A **parallel** uses the exact same photograph and design structure as a base
card, altering the colour scheme, borders, finish or foil. A **variation** —
image variation, short print, super short print — features a completely
different photo or design element while keeping the base card number.

The difference in how they are stored follows from one rule: **rows exist only
for what cannot be derived.** A variation prints a different subject on an
existing number, so it needs rows, and it declares what it `varies`. A parallel
re-prints cards that already exist, so it is never a checklist — every parallel
is declared in `parallels[]` with a permanent id and a `coverage`:

```json
"parallels": [
  { "id": "…", "name": "Gold", "coverage": "full", "applies_to": ["Base"] },
  { "id": "…", "name": "Mascots Autograph Parallel", "coverage": "partial",
    "file": "parallels/mascots-autograph-parallel.csv",
    "varies": "inserts/mascots.csv", "card_count": 15 }
]
```

A Gold covering all 700 base cards is fully derivable from `base.csv`, so it
carries no rows — 700 of them would say nothing new, and ownership is recorded
as (set, card_number, parallel id) against the base row. But only 15 of the 30
Mascots got the autograph treatment, and *which* 15 exists nowhere else, so
those rows are real information. A parallel whose extent nobody has verified is
declared `unknown` rather than guessed at.

A parallel printed in one wave only adds `series`, which narrows the target
before `coverage` is read:

```json
{ "name": "Spring Training", "coverage": "full",
  "series": "Series 1", "applies_to": ["Base"] }
```

Every Series 1 base card, none of Series 2 — 350 of the 700. The alternatives
were both wrong: `full` alone claims twice the cards, and rows would copy half
of `base.csv` to say what `series[].card_numbers` already says.

Both `varies` and `coverage` are asserted by a person, never inferred from
numbers: 2026 Topps has a 90-card insert numbered 1-90 whose numbers all exist
in the base set and whose players are entirely different.

## Validating

```sh
pip install -r requirements.txt
scripts/validate.py                                   # everything
scripts/validate.py data/baseball/2026/topps/2026-topps
```

Every failure names the file and, for rows, the line number. CI runs this on
every pull request.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: one set per PR, provenance
required, and `scripts/validate.py` must pass.
