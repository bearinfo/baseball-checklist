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

1. Create `data/baseball/<year>/<manufacturer>/<set-slug>/`, kebab-case
   throughout. The set slug is the brand-year, e.g. `2026-topps` — one set per
   brand-year, not one per series or product.
2. Generate a **new UUID** for `id` (`python -c "import uuid; print(uuid.uuid4())"`).
   Never reuse or edit an existing one: it is the permanent handle consumers key
   on, and it must survive every later rename.
3. Write the rows per [schema/1.0/ROW-FORMAT.md](schema/1.0/ROW-FORMAT.md).
4. Declare every CSV in `set.json` with its exact `card_count`.
5. Fill in `provenance` — at least one source, with `retrieved`. Leave
   `verified: false` until a human has compared the rows against the source.

## Correcting a name

Edit the one line. That is the whole procedure, and it is why rows are CSV. Say
in the PR what the source shows — a correction without a source is a guess.

## Extending a vocabulary

Team names (`data/baseball/teams.json`) and designation codes
(`schema/1.0/designations.json`) are closed lists. To add one, include evidence
of the printed form — which set and card prints it that way. Historical and
defunct franchises belong in the list once a card prints them; so do a
manufacturer's inconsistent forms, since rows record names **as printed**.

## What does not belong here

- Prices, valuations, ownership, or condition — this repo is checklists.
- Person IDs from any external database. Names are recorded as printed; identity
  resolution is the consumer's job.
- Manufacturer PDFs or scans. Store only the derived factual rows.
- Parallels as rows. A parallel is a printing of an existing card, declared in
  `set.json`.

## Converters

`tools/` holds converters from published sources to this format. They are not
part of the specification, and consumers never need them — they exist so that
generated data is reproducible and reviewable. A converter must fail loudly on
anything it cannot parse deterministically rather than guess.
