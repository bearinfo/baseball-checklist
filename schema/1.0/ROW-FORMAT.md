# Row format 1.0 — the checklist CSV standard

Every checklist file (`base.csv`, `inserts/*.csv`) is a UTF-8 CSV with a header
row, comma-separated, `\n` line endings. **One row = one card.** A corrected name
must always be a one-line diff.

## Columns — frozen for 1.0

These six columns are the complete 1.0 row vocabulary. New needs are met by
extending `designations.json` (by PR, with evidence) or by a schema version
bump — never by ad-hoc columns.

| Column | Required | Meaning |
|---|---|---|
| `card_number` | **yes** | Always TEXT, exactly as printed: `1`, `US300`, `GN-1`. Unique **within the file** — see Numbering scope. |
| `name` | **yes** | Who or what is on the card, **as printed** — a player name, a team name (team cards), or a title. Never a resolved/corrected identity. |
| `team` | **yes** | Team name from the checked-in `data/baseball/teams.json` list, trademark glyphs stripped. |
| `designations` | no | Space-separated codes from `schema/1.0/designations.json`, e.g. `RC`, `FS`, `CC CL`. Empty = plain base card. |
| `is_short_print` | no | `true`/`false`; empty = `false`. SP/SSP detail goes in `variation_note`. |
| `variation_note` | no | Free text for variations: `"SSP image variation - batting stance"`. |

- Required columns must be present in the header of every file.
- An optional column may be omitted from a file entirely if it would be empty on
  every row (keeps diffs and review noise small).
- No other columns are allowed. Set-level facts (year, manufacturer, set name)
  are **never** repeated per row — they live in `set.json` and the directory path.

## Multi-subject cards (League Leaders, combos)

One row per **card**, never per person. Names and teams are joined with `" / "`
in the same order:

```csv
5,Tarik Skubal / Ronel Blanco / Framber Valdez,Detroit Tigers / Houston Astros / Houston Astros,LL
```

The i-th name pairs with the i-th team. If the source prints one line per person
under the same card number, the converter merges them into one row.

## Numbering scope

`card_number` is unique **within one CSV file**, never across a set. Manufacturers
deliberately reuse base numbers: 2026 Topps prints four short-print rookies at
#697–700 alongside four different base cards at the same numbers. They are
distinct physical cards, so they are distinct rows — in a separate file:

```
base.csv                                    697 Bryan Reynolds ...
variations/base-card-short-print-rookies.csv  697 Kevin McGonigle ... true
```

A file is the unit of unique numbering. `variations/` holds real cards that share
the base numbering (short-print rookies, photo variations) — unlike parallels,
which are re-printings of a card that already exists and are declared in
`set.json`, never as rows.

## Rules

1. **As printed, never resolved.** Misspellings by the manufacturer are kept and
   noted in `variation_note` if intentional; identity resolution belongs to
   consumers.
2. **Never guess.** A source line that cannot be parsed deterministically blocks
   the conversion with its line number. It is never skipped, never invented.
3. **Parallels are not rows.** A parallel is a printing of existing cards
   (declared at set level in a future schema revision), never duplicated rows.
4. **Team values are closed.** Every `/`-separated team component must appear in
   `data/baseball/teams.json`.
5. **Designations are closed.** Every code must appear in
   `schema/1.0/designations.json`; the vocabulary grows by PR, with evidence.
