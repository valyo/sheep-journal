# Stalljournal – sheep and goats

A small Flask + SQLite app for keeping the herd register (*stalljournal*, "fårjournal")
that Jordbruksverket requires for sheep and goats.

## Run the dev environment

```bash
docker compose up --build
```

Open http://localhost:8000. The source is bind-mounted and Flask runs in debug mode, so
code changes reload automatically. The database is `instance/sheep_journal.sqlite` on
the host.

```bash
docker compose run --rm web flask --app sheep_journal seed-demo   # demo herd (empty DB only)
docker compose run --rm web pytest                                # tests
```

## What it covers

| Rule (Jordbruksverket) | In the app |
|---|---|
| Record arrivals, departures, births and deaths in date order | Plus (in) and minus (out) entries with the official event types |
| Within 48 hours; births once all lambs are tagged (max 6 months after the first birth) | Late entries are warned about and flagged; births are exempt |
| Animals living ≥ 12 months recorded individually with PPN + individual number | "Livdjur" entries require an individual number; *Keep a lamb for breeding* moves one lamb out of a group row into an individual row |
| Slaughter lambs may be recorded as groups | Rows without an individual number carry a count |
| Supplier / recipient and transporter (driver, vehicle reg.) for movements | Required / warned per event type |
| Deaths with date and documented cause | Cause of death required |
| Keep records for 5 years | Entries are voided (crossed out, with a reason), never deleted |
| Count all animals 1–31 December and report | December count page, compared with the journal balance |
| Other breed / known genotype / re-tagging noted | Breed, genotype, previous ID, electronic tag fields |

Print views reproduce the paper plusblad, minusblad and *tillfälligt ute* sheets, and
`/export.csv` exports the full journal (semicolon-separated for Swedish Excel).

Reporting movements to Jordbruksverket within 7 days is still done in their e-service;
this app only keeps the journal.

## Layout

```
sheep_journal/
  __init__.py      app factory
  schema.sql       tables: holding, entry, annual_count
  constants.py     event types and labels
  rules.py         form parsing and the record-keeping rules
  store.py         database queries
  views/           dashboard, journal, animals
  templates/, static/
tests/
```

Not included yet: user accounts, schema migrations, and a production server setup.
