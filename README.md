# baseball-checklist

Baseball card checklists as data: curated, version-controlled, schema-validated,
and free for any program to consume.

This repo is **inert data with a specification**. It contains no code that writes
into any application — consumers pull from it and convert on their own side.

```
schema/1.0/set.schema.json     the specification for set.json
schema/1.0/ROW-FORMAT.md       the row standard (frozen for 1.0)
schema/1.0/designations.json   controlled vocabulary: RC, FS, LL, TC, CC, CL, RCUP
data/baseball/teams.json       closed list of valid team names
data/baseball/<year>/<manufacturer>/<set-slug>/
    set.json                   identity, provenance, series, packagings
    base.csv                   the base checklist
    variations/*.csv           cards sharing base numbering (short prints, photo variations)
    inserts/*.csv  autographs/*.csv  relics/*.csv
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

A **packaging** is a way the set was sold as a whole. The 2026 Topps Factory Set
is a sealed box holding the 700-card base set plus four short-print rookies not
available in packs — so it is a `packaging` listing checklists that already
exist, never a separate set and never duplicated rows. The distinction matters:
the base cards in that box are the same cards pulled from Series 1 and 2 packs,
and only the four short prints are exclusive to it.

Card numbers are unique **within a file**, not across a set: manufacturers
deliberately reuse them, so 2026 Topps prints four short-print rookies at
#697-700 alongside four different base cards at those numbers. Different cards,
different files.

Parallels are *printings* of cards that already exist. They are declared in
`set.json` and never emitted as rows.

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
