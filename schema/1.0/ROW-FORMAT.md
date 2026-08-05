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

**`base.csv` is the source of every card number in a set.** Variations share that
numbering and never add to it; a variation file whose number is absent from the
file it `varies` fails validation. That single rule is what stops a variation
being counted as an extra card.

`card_number` is therefore unique **within one CSV file**, not across a set. A
variation is a second version of a card that already exists — same number,
whatever is printed on it. The subject may differ entirely: 2026 Topps prints
Kevin McGonigle on the short-print #697 where the base card is Bryan Reynolds.
Both are real cards, so both are rows, in separate files:

```
base.csv                            697  Bryan Reynolds
variations/short-print-rookies.csv  697  Kevin McGonigle   is_short_print=true
```

Each variation checklist declares what it varies:

```json
{ "file": "variations/short-print-rookies.csv", "kind": "variation",
  "varies": "base.csv", "card_count": 4 }
```

## What each kind means

| kind | definition |
|---|---|
| `base` | The cards that define the set's numbering. For a set issued in waves, all of them: 2026 Topps base is Series 1 and Series 2 together, #1-700. |
| `parallel` | Uses the exact same photograph and design structure as a base card, but alters the colour scheme, borders, card finish, or foil pattern. |
| `variation` | Often called an image variation, short print (SP) or super short print (SSP). Features a completely different photo or design element from the standard base card, while retaining the same base set card number. |
| `insert` `autograph` `relic` | Cards issued alongside the set, with their own numbering — unless they declare `varies`, because an autograph or relic of a base card shares that card's number. |

A checklist row carries only a number, a name and a team. It can never prove
whether the photograph changed, so `kind` follows what the manufacturer prints
and is corrected by a person holding evidence of the card itself.

### `varies` is asserted, never inferred

Numbers alone prove nothing. 2026 Topps has a 90-card insert numbered 1-90 whose
numbers all exist in the base set and whose players are entirely different — the
numbering merely collides. By contrast its Real One Relics match base cards on
both number *and* player, and are genuinely relics of those cards.

So `varies` is always a human assertion. Once made, validation enforces it: every
card number in the file must exist in the file it varies.

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
