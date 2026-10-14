# Stalljournal – sheep and goats

[![Tests](https://github.com/valyo/sheep-journal/actions/workflows/test.yml/badge.svg)](https://github.com/valyo/sheep-journal/actions/workflows/test.yml)
[![Build and Push Docker Image](https://github.com/valyo/sheep-journal/actions/workflows/docker-build.yml/badge.svg)](https://github.com/valyo/sheep-journal/actions/workflows/docker-build.yml)

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

### Production image

CI builds the `production` stage of the Dockerfile (gunicorn, non-root user) and, on
pushes to `main`, publishes it to `ghcr.io/valyo/sheep-journal` tagged with the
version in `VERSION` and `latest`. Pull requests build and scan the image without
pushing. Bump `VERSION` for each release.

```bash
docker run -d -p 8000:8000 -e SECRET_KEY=<long random value> \
  -v sheep-journal-data:/app/instance ghcr.io/valyo/sheep-journal:latest
```

The app has no login yet: only run it where you control who can reach it.

### Importing the old Google Sheets journal

```bash
docker compose run --rm web flask --app sheep_journal import-xlsx stalljournal.xlsx --dry-run
docker compose run --rm web flask --app sheep_journal import-xlsx stalljournal.xlsx
```

The importer reads the `data`, `individuppgifter`, `ppn-regiser` and `Flik-B` sheets. It
interprets rows rather than copying them: running totals ("ingående balans", "lamm kvar")
become checks, returns recorded on the minus sheet become returns, a mother written in the
individual column becomes the litter's mother, and purchase rows are merged with the rows
that give the animals' identity. A report of everything it changed or couldn't resolve is
printed and saved next to the database. `--replace` deletes the current data first.

Spreadsheets are git-ignored: they contain personal data.

### Schema changes

`schema.sql` is the full current schema for new databases. Existing databases are upgraded
on start by the numbered scripts in `sheep_journal/migrations/` (tracked with
`PRAGMA user_version`). Add a new `NNNN_name.sql` there *and* update `schema.sql`; a test
checks that both give the same tables.

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
| Animals kept ≥ 12 months carry two ear tags | Tag type per animal and in the tag stock; warnings for breeding animals with a single tag |
| Medicine use recorded and kept 5 years | Herd log with product, dose and withdrawal period; medicine records can't be deleted |

Beyond the journal itself:

- **Animal register**: name, exact birth date, sex, colour, breed, markings, mother and
  father, elitlamm numbers, tag type and colour, and up to two photos. Photos are turned
  upright, resized and re-encoded as JPEG (which drops EXIF data such as GPS position),
  and stored in `instance/uploads/` next to the database.
- **Ear-tag lambs**: births can be recorded as a litter (with mother and males/females) and
  the lambs ear-tagged later. Tagging rows appear on the plus sheet but don't change the
  balance.
- **Ear tag stock**: add a tag order as a number range; the next unused numbers are
  suggested when tagging.
- **Contacts**: other holdings and slaughterhouses by PPN, shown by name in the journal.
- **Herd log**: shearing, treatments, vaccinations, deworming and other work.

Print views reproduce the paper plusblad, minusblad and *tillfälligt ute* sheets, and
`/export.csv` exports the full journal (semicolon-separated for Swedish Excel).

Reporting movements to Jordbruksverket within 7 days is still done in their e-service;
this app only keeps the journal.

## Layout

```
sheep_journal/
  __init__.py      app factory
  schema.sql       tables: holding, contact, entry, animal, ear_tag, herd_event, annual_count
  migrations/      upgrades for existing databases
  constants.py     event types and labels
  ids.py           ear tag number parsing
  photos.py        animal photo processing
  importer.py      Google Sheets / xlsx import
  rules.py         form parsing and the record-keeping rules
  store.py         database queries
  views/           dashboard, journal, animals, registers (contacts, tags, herd log)
  templates/, static/
tests/
```

Not included yet: user accounts and a production server setup.
