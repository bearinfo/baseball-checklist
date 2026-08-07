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
| `card_number` | **yes** | Always TEXT, exactly as printed: `1`, `US300`, `GN-1`. Unique **within the file** — see Numbering scope. Unique with `variation_note` where a manufacturer prints several cards on one number. |
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

### Several cards on one number

Topps stamps 697 on all six Jackson Holliday Fun Face cards of 2024 — an
homage to the 1989 Fleer Billy Ripken, down to the black box and the scribble.
The number identifies none of them, and it is still the number printed on every
one:

```csv
697,Jackson Holliday,Baltimore Orioles,RC,"Fun Face" on the bat knob
697,Jackson Holliday,Baltimore Orioles,RC,Black box over the bat knob
697,Jackson Holliday,Baltimore Orioles,RC,Black scribble over the bat knob
```

So the row key is `card_number` **plus `variation_note`**, and uniqueness is
enforced on the pair. Two rows sharing a number and a note are still a
duplicate and still fail.

Where numbers repeat, `variation_note` stops being decorative: it is the only
thing telling the cards apart, so it must be present and it must be stable.
Reword it and a consumer keyed on it loses the card. Nothing else changes —
`card_number` remains exactly what the manufacturer printed, which is worth
more than a tidier key.

Each variation checklist declares what it varies:

```json
{ "file": "variations/short-print-rookies.csv", "kind": "variation",
  "varies": "base.csv", "card_count": 4 }
```

## What each kind means

| kind | definition |
|---|---|
| `base` | The cards that define the set's numbering. For a set issued in waves, all of them: 2026 Topps base is Series 1 and Series 2 together, #1-700. |
| `variation` | Often called an image variation, short print (SP) or super short print (SSP). Features a completely different photo or design element from the standard base card, while retaining the same base set card number. |
| `insert` `autograph` `relic` | Cards issued alongside the set, with their own numbering — unless they declare `varies`, because an autograph or relic of a base card shares that card's number. |

A **parallel** is deliberately not a kind. It uses the exact same photograph and
design structure as an existing card, altering only the color scheme, borders,
finish or foil — it never introduces a card, so it is never a checklist. Every
parallel is declared in `set.json`'s `parallels[]` with a stable id and a
`coverage` a person asserts: `full` (every card of its targets — no rows, they
would all be derivable), `partial` (the manufacturer printed an explicit list —
its rows live in `parallels/*.csv`, referenced by the declaration's `file`, in
this same row format), or `unknown` (it exists, extent unverified). One printed
in a single wave adds `series`, narrowing the target to that wave's card numbers
before `coverage` is read, so covering all of Series 1 needs no rows either. A collection
records parallel ownership as (set, card_number, parallel id) — pointing at the
existing row, never duplicating it.

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
3. **Rows exist only for what cannot be derived.** A parallel covering every
   card of its target is declared at set level and gets no rows, because they
   would repeat a file that already exists. Rows appear only when they carry
   the one fact nothing else does — *which* cards the manufacturer printed.
4. **Team values are closed.** Every `/`-separated team component must appear in
   `data/baseball/teams.json`.
5. **Designations are closed.** Every code must appear in
   `schema/1.0/designations.json`; the vocabulary grows by PR, with evidence.
