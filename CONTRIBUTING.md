# Contributing

Data changes are welcome. The rules exist so the data can be trusted without
re-checking it by hand.

## Before you open a PR

```sh
pip install -r requirements.txt
scripts/validate.py
```

It must pass. CI runs the same command.

## Adding a set

1. Create `data/baseball/<year>/<set-slug>/`, kebab-case
   throughout. The set slug is the brand-year, e.g. `2026-topps` — one set per
   brand-year, not one per series or product.
2. Generate a **new UUID** for `id` (`python -c "import uuid; print(uuid.uuid4())"`).
   Never reuse or edit an existing one: it is the permanent handle consumers key
   on, and it must survive every later rename.
3. Write the rows per [schema/1.0/ROW-FORMAT.md](schema/1.0/ROW-FORMAT.md).
4. Declare every CSV in `set.json` with its exact `card_count`.
5. Fill in `provenance` — at least one source, with `retrieved`. Leave
   `verified: false` until a human has compared the rows against the source.

## Adding a parallel

Parallels go in `set.json`'s `parallels[]`, never in `checklists[]`. Give each a
new UUID and state its `coverage` — the one judgement that decides everything
else:

```json
{ "id": "…", "name": "Gold", "coverage": "full", "applies_to": ["Base"] }
{ "id": "…", "name": "Mascots Autograph Parallel", "coverage": "partial",
  "file": "parallels/mascots-autograph-parallel.csv",
  "varies": "inserts/mascots.csv", "card_count": 15 }
```

- **`full`** — every card of the target exists in this parallel, so its
  checklist is derivable and rows would be duplication. No `file`.
- **`partial`** — the manufacturer printed an explicit list. The rows *are* the
  information, so `file`, `varies` and `card_count` are required. Validation
  rejects a partial whose rows happen to cover the whole target: that is a
  `full` parallel with redundant rows.
- **`unknown`** — the parallel exists but nobody has verified its extent. Use
  this rather than guessing; a source that names a parallel without counting it
  supports nothing stronger, and consumers are told not to assume any given card
  exists in it.

`applies_to` names checklists, or other parallels. A colour run of a parallel
points at its parent by name:

```json
{ "id": "…", "name": "Big Apple", "coverage": "partial",
  "file": "parallels/big-apple.csv", "varies": "base.csv", "card_count": 100 }
{ "id": "…", "name": "Big Apple Gold", "coverage": "full",
  "applies_to": ["Big Apple"] }
```

Gold prints the same 100 cards Big Apple does, so it is full coverage of that
parallel and needs no rows of its own. Validation rejects a name the set
declares in neither array, a parallel naming itself, and a cycle — and rejects
one name used for both a checklist and a parallel, which is what keeps
`applies_to` unambiguous.

A parallel printed in only one wave of a multi-series set adds `series`, naming
an entry in `series[]`. It narrows the target before `coverage` is read:

```json
{ "id": "…", "name": "Spring Training", "coverage": "full",
  "series": "Series 1", "applies_to": ["Base"] }
```

That is every Series 1 base card and none of Series 2 — 350 of 700. Without it
the choice would be `full`, claiming twice the cards, or 350 rows copied out of
`base.csv`. The numbers stay derivable from `series[].card_numbers`.

Coverage is asserted by a person, like `varies`. Say in the PR what shows it.

## Serial numbering

A card numbered `3/5` says so on its face, so `print_run` records what is
printed. Production estimates do not qualify: "limited to 600 copies" on a card
carrying no number is somebody's research, and stays out.

`print_run` alone carries this. Present means the parallel is serial numbered,
absent means it is not — there is no second flag to keep in step with it, and
none to contradict it.

That rule has a cost worth knowing. A parallel whose number nobody has found is
recorded exactly like one that carries no number. Where the difference matters,
say so in the set's `provenance` notes: "the relic ladders are unnumbered here
because no source gives figures, not because the cards are unnumbered" is one
line that covers a hundred records, and it does not tempt anyone into marking
records they have not checked.

**Failing to find a number is not evidence that no number exists.** That still
holds; it is just no longer something the data can be made to say per card.

## Correcting a name

Edit the one line. That is the whole procedure, and it is why rows are CSV. Say
in the PR what the source shows — a correction without a source is a guess.

## Extending a vocabulary

Team names (`data/baseball/teams.json`), designation codes
(`schema/1.0/designations.json`) and checklist tags (`schema/1.0/tags.json`) are
closed lists. To add one, include evidence of the printed form — which set and
card prints it that way.

Tags are the exception to "as printed", and the only curatorial field here.
Nothing prints the word *gimmick*; Topps prints `BASE CARDS DANCING DODGERS
VARIATION`. A tag exists so a question spanning sets can be answered in one
pass — every gimmick across every year — which `kind` cannot, since it says only
that these are variations. Two rules keep the list honest: a tag must never
restate data already held (`distribution` for how it was sold, the row's
`is_short_print` for short prints), and adding one still needs evidence that a
given checklist belongs in the category. Historical and
defunct franchises belong in the list once a card prints them; so do a
manufacturer's inconsistent forms, since rows record names **as printed**.

## What does not belong here

- Prices, valuations, ownership, or condition — this repo is checklists.
- Person IDs from any external database. Names are recorded as printed; identity
  resolution is the consumer's job.
- Manufacturer PDFs or scans. Store only the derived factual rows.
- Parallels as checklists. A parallel is a printing of cards that already exist,
  so it is declared in `set.json`'s `parallels[]`, never given a `kind`. It
  carries rows only when the manufacturer printed a partial list — see below.

## Converters

`tools/` holds converters from published sources to this format. They are not
part of the specification, and consumers never need them — they exist so that
generated data is reproducible and reviewable. A converter must fail loudly on
anything it cannot parse deterministically rather than guess.
