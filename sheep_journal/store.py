"""Database reads and writes."""

from . import clock
from .constants import EVENT_TYPES, UNCOUNTED_TYPES
from .db import get_db
from .ids import animal_ref

ENTRY_FIELDS = (
    "direction",
    "event_type",
    "event_date",
    "species",
    "ppn",
    "individual_number",
    "count",
    "sex",
    "birth_year",
    "breeding",
    "counterparty",
    "driver_name",
    "vehicle_reg",
    "cause_of_death",
    "breed",
    "genotype",
    "electronic_tag",
    "previous_id",
    "notes",
    "mother_id",
    "males",
    "females",
    "source",
)

HOLDING_FIELDS = (
    "ppn", "keeper_name", "address", "species", "category", "main_breed", "journal_start",
    "postal_address", "county", "municipality", "property_designation", "area_ha", "housing",
    "max_capacity", "registered_from", "phone", "email",
)

COUNT_FIELDS = (
    "year", "species", "count_date", "total", "ewes", "rams", "lambs", "reported_on", "notes",
)

CONTACT_FIELDS = ("ppn", "name", "keeper", "kind", "address", "phone", "email", "notes")

ANIMAL_FIELDS = (
    "species", "ppn", "individual_number", "tag_year", "tag_type", "tag_model", "tag_colour",
    "electronic_tag", "name", "sex", "birth_date", "birth_year", "colour", "breed", "markings",
    "mother_id", "mother_name", "mother_elite_no", "father_id", "father_name", "father_elite_no",
    "elite_no", "elite_code", "notes",
)

TAG_FIELDS = ("species", "individual_number", "tag_type", "tag_model", "tag_colour", "order_ref")

HERD_EVENT_FIELDS = (
    "event_date", "kind", "species", "ppn", "individual_number", "subject", "description",
    "product", "dose", "withdrawal_until", "prescribed_by", "notes", "source",
)

_UNCOUNTED_SQL = ", ".join(f"'{t}'" for t in UNCOUNTED_TYPES) or "''"


def _insert_row(db, table, fields, data, extra=None):
    cols = list(fields) + list((extra or {}).keys())
    values = [data.get(c) for c in fields] + list((extra or {}).values())
    cur = db.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        values,
    )
    return cur.lastrowid


# --- holding -----------------------------------------------------------------


def get_holding():
    return get_db().execute("SELECT * FROM holding WHERE id = 1").fetchone()


def save_holding(data, commit=True):
    db = get_db()
    cols = ", ".join(HOLDING_FIELDS)
    marks = ", ".join("?" for _ in HOLDING_FIELDS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in HOLDING_FIELDS)
    db.execute(
        f"INSERT INTO holding (id, {cols}) VALUES (1, {marks}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}",
        [data.get(c) for c in HOLDING_FIELDS],
    )
    if commit:
        db.commit()


# --- contacts (PPN register) ---------------------------------------------------


def list_contacts():
    return get_db().execute("SELECT * FROM contact ORDER BY kind, name").fetchall()


def get_contact(contact_id):
    return get_db().execute("SELECT * FROM contact WHERE id = ?", (contact_id,)).fetchone()


def contact_by_ppn(ppn):
    return get_db().execute("SELECT * FROM contact WHERE ppn = ?", (ppn,)).fetchone()


def save_contact(data, contact_id=None, commit=True):
    db = get_db()
    if contact_id is None:
        contact_id = _insert_row(db, "contact", CONTACT_FIELDS, data)
    else:
        assignments = ", ".join(f"{c} = ?" for c in CONTACT_FIELDS)
        db.execute(
            f"UPDATE contact SET {assignments} WHERE id = ?",
            [data.get(c) for c in CONTACT_FIELDS] + [contact_id],
        )
    if commit:
        db.commit()
    return contact_id


# --- journal entries -----------------------------------------------------------


def _insert(db, entry, created_at=None):
    return _insert_row(
        db, "entry", ENTRY_FIELDS, entry,
        {"created_at": created_at or clock.now().isoformat()},
    )


def insert_entry(entry, created_at=None, commit=True):
    db = get_db()
    entry_id = _insert(db, entry, created_at)
    if commit:
        db.commit()
    return entry_id


def insert_entries(entries):
    """Insert several entries in one transaction."""
    db = get_db()
    ids = [_insert(db, e) for e in entries]
    db.commit()
    return ids


def update_entry(entry_id, entry):
    db = get_db()
    fields = [f for f in ENTRY_FIELDS if f != "source"]
    assignments = ", ".join(f"{c} = ?" for c in fields)
    db.execute(
        f"UPDATE entry SET {assignments}, updated_at = ? WHERE id = ?",
        [entry.get(c) for c in fields] + [clock.now().isoformat(), entry_id],
    )
    db.commit()


def void_entry(entry_id, reason):
    db = get_db()
    db.execute(
        "UPDATE entry SET voided_at = ?, void_reason = ? WHERE id = ? AND voided_at IS NULL",
        (clock.now().isoformat(), reason, entry_id),
    )
    db.commit()


def get_entry(entry_id):
    return get_db().execute("SELECT * FROM entry WHERE id = ?", (entry_id,)).fetchone()


def list_entries(
    direction=None,
    species=None,
    year=None,
    event_type=None,
    search=None,
    include_voided=True,
    newest_first=False,
    limit=None,
):
    clauses, params = [], []
    if direction in ("in", "out"):
        clauses.append("direction = ?")
        params.append(direction)
    if species:
        clauses.append("species = ?")
        params.append(species)
    if year and str(year).isdigit():
        clauses.append("substr(event_date, 1, 4) = ?")
        params.append(str(year))
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if search:
        clauses.append(
            "(ppn LIKE ? OR individual_number LIKE ? OR counterparty LIKE ? "
            "OR notes LIKE ? OR breed LIKE ?)"
        )
        params.extend([f"%{search}%"] * 5)
    if not include_voided:
        clauses.append("voided_at IS NULL")

    sql = "SELECT * FROM entry"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY event_date DESC, id DESC" if newest_first else " ORDER BY event_date, id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return get_db().execute(sql, params).fetchall()


def available_years():
    rows = get_db().execute(
        "SELECT DISTINCT substr(event_date, 1, 4) AS year FROM entry ORDER BY year DESC"
    ).fetchall()
    return [r["year"] for r in rows]


def balance(as_of=None, exclude_id=None, before=None):
    """Animals per species according to the journal.

    present: on the holding. away: temporarily away (tillfälligt ute).
    as_of includes events on that date; before excludes them.
    Tagging rows don't count: those animals were counted at birth.
    """
    sql = f"""
        SELECT species,
               SUM(CASE WHEN direction = 'in' THEN count ELSE -count END) AS present,
               SUM(CASE WHEN event_type = 'temp_out' THEN count
                        WHEN event_type = 'return_home' THEN -count
                        ELSE 0 END) AS away
          FROM entry
         WHERE voided_at IS NULL AND event_type NOT IN ({_UNCOUNTED_SQL})
    """
    params = []
    if as_of:
        sql += " AND event_date <= ?"
        params.append(as_of)
    if before:
        sql += " AND event_date < ?"
        params.append(before)
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    sql += " GROUP BY species"
    return {
        r["species"]: {"present": r["present"] or 0, "away": r["away"] or 0}
        for r in get_db().execute(sql, params).fetchall()
    }


# --- individual animals --------------------------------------------------------


def status_after(event_type):
    if EVENT_TYPES[event_type].direction == "in":
        return "present"
    if event_type == "temp_out":
        return "away"
    return "gone"


def _blank_animal(species, ppn, individual_number):
    return {
        "id": None,
        "species": species,
        "ppn": ppn,
        "individual_number": individual_number,
        "ref": animal_ref(ppn, individual_number),
        "first_date": None,
        "last_date": None,
        "last_event": None,
        "status": "unrecorded",
        "events": 0,
        **{f: None for f in ANIMAL_FIELDS if f not in ("species", "ppn", "individual_number")},
        "electronic_tag": False,
    }


def individual_animals(exclude_id=None):
    """One record per individually identified animal.

    Where the animal is comes from its journal rows; who it is comes from the
    animal register. Animals in the register without journal rows have status
    'unrecorded'.
    """
    db = get_db()
    sql = "SELECT * FROM entry WHERE voided_at IS NULL AND individual_number IS NOT NULL"
    params = []
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    sql += " ORDER BY event_date, id"

    animals = {}
    for row in db.execute(sql, params):
        key = (row["species"], row["ppn"], row["individual_number"])
        animal = animals.get(key)
        if animal is None:
            animal = animals[key] = _blank_animal(*key)
            animal["first_date"] = row["event_date"]
        animal["events"] += 1
        for field in ("sex", "birth_year", "breed", "genotype", "mother_id"):
            if row[field]:
                animal[field] = row[field]
        if row["electronic_tag"]:
            animal["electronic_tag"] = True
        animal["last_event"] = row["event_type"]
        animal["last_date"] = row["event_date"]
        animal["status"] = status_after(row["event_type"])

    for row in db.execute("SELECT * FROM animal"):
        key = (row["species"], row["ppn"], row["individual_number"])
        animal = animals.get(key)
        if animal is None:
            animal = animals[key] = _blank_animal(*key)
        animal["id"] = row["id"]
        for field in ANIMAL_FIELDS:
            if row[field] not in (None, ""):
                animal[field] = bool(row[field]) if field == "electronic_tag" else row[field]
    return animals


def animal_history(species, ppn, individual_number):
    return get_db().execute(
        "SELECT * FROM entry WHERE species = ? AND ppn = ? AND individual_number = ? "
        "ORDER BY event_date, id",
        (species, ppn, individual_number),
    ).fetchall()


def get_animal(animal_id):
    return get_db().execute("SELECT * FROM animal WHERE id = ?", (animal_id,)).fetchone()


def animal_by_key(species, ppn, individual_number):
    return get_db().execute(
        "SELECT * FROM animal WHERE species = ? AND ppn = ? AND individual_number = ?",
        (species, ppn, individual_number),
    ).fetchone()


def save_animal(data, commit=True):
    """Insert or update by (species, ppn, individual_number). Returns the id."""
    db = get_db()
    data = {**data, "electronic_tag": 1 if data.get("electronic_tag") else 0}
    cols = ", ".join(ANIMAL_FIELDS)
    marks = ", ".join("?" for _ in ANIMAL_FIELDS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in ANIMAL_FIELDS[3:])
    db.execute(
        f"INSERT INTO animal ({cols}) VALUES ({marks}) "
        f"ON CONFLICT (species, ppn, individual_number) DO UPDATE SET {updates}",
        [data.get(c) for c in ANIMAL_FIELDS],
    )
    if commit:
        db.commit()
    return animal_by_key(data["species"], data["ppn"], data["individual_number"])["id"]


def merge_animal(data, commit=True):
    """Like save_animal, but keeps existing details where data has no value."""
    existing = animal_by_key(data["species"], data["ppn"], data["individual_number"])
    if existing:
        merged = dict(existing)
        merged.update({k: v for k, v in data.items() if v not in (None, "")})
        data = merged
    return save_animal(data, commit=commit)


def births_and_tagged(species, ppn, birth_year):
    """How many were recorded born in a year, and how many of those have been tagged."""
    db = get_db()
    born = db.execute(
        "SELECT COALESCE(SUM(count), 0) FROM entry WHERE voided_at IS NULL "
        "AND event_type = 'birth' AND species = ? AND ppn = ? AND birth_year = ?",
        (species, ppn, birth_year),
    ).fetchone()[0]
    tagged = db.execute(
        "SELECT COUNT(*) FROM entry WHERE voided_at IS NULL "
        "AND event_type = 'tagging' AND species = ? AND ppn = ? AND birth_year = ?",
        (species, ppn, birth_year),
    ).fetchone()[0]
    return born, tagged


def commit():
    get_db().commit()


def offspring(ref):
    return [a for a in individual_animals().values() if a["mother_id"] == ref]


# --- animal photos -------------------------------------------------------------


def list_photos(species, ppn, individual_number):
    return get_db().execute(
        "SELECT * FROM animal_photo WHERE species = ? AND ppn = ? AND individual_number = ? "
        "ORDER BY id",
        (species, ppn, individual_number),
    ).fetchall()


def first_photos():
    """The first photo of every animal that has one, keyed like individual_animals()."""
    rows = get_db().execute(
        "SELECT * FROM animal_photo WHERE id IN "
        "(SELECT MIN(id) FROM animal_photo GROUP BY species, ppn, individual_number)"
    ).fetchall()
    return {(r["species"], r["ppn"], r["individual_number"]): r for r in rows}


def add_photo(species, ppn, individual_number, filename, original_name):
    db = get_db()
    db.execute(
        "INSERT INTO animal_photo (species, ppn, individual_number, filename, original_name, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (species, ppn, individual_number, filename, original_name, clock.now().isoformat()),
    )
    db.commit()


def get_photo(photo_id):
    return get_db().execute("SELECT * FROM animal_photo WHERE id = ?", (photo_id,)).fetchone()


def delete_photo(photo_id):
    db = get_db()
    db.execute("DELETE FROM animal_photo WHERE id = ?", (photo_id,))
    db.commit()


# --- ear tag stock -------------------------------------------------------------


def list_tags(species=None):
    """Own ear tags, each with used = True once an animal or entry carries the number."""
    holding = get_holding()
    own_ppn = holding["ppn"] if holding else ""
    sql = """
        SELECT t.*,
               EXISTS (SELECT 1 FROM animal a
                        WHERE a.species = t.species AND a.ppn = ? AND a.individual_number = t.individual_number)
            OR EXISTS (SELECT 1 FROM entry e
                        WHERE e.voided_at IS NULL AND e.species = t.species AND e.ppn = ?
                          AND e.individual_number = t.individual_number) AS used
          FROM ear_tag t
    """
    params = [own_ppn, own_ppn]
    if species:
        sql += " WHERE t.species = ?"
        params.append(species)
    sql += " ORDER BY t.species, t.individual_number"
    return get_db().execute(sql, params).fetchall()


def get_tag(species, individual_number):
    return get_db().execute(
        "SELECT * FROM ear_tag WHERE species = ? AND individual_number = ?",
        (species, individual_number),
    ).fetchone()


def add_tags(tags, commit=True):
    """Add tags; numbers already in stock are skipped. Returns how many were added."""
    db = get_db()
    added = 0
    for tag in tags:
        cur = db.execute(
            f"INSERT OR IGNORE INTO ear_tag ({', '.join(TAG_FIELDS)}) "
            f"VALUES ({', '.join('?' for _ in TAG_FIELDS)})",
            [tag.get(c) for c in TAG_FIELDS],
        )
        added += cur.rowcount
    if commit:
        db.commit()
    return added


def set_tag_lost(tag_id, lost):
    db = get_db()
    db.execute("UPDATE ear_tag SET lost = ? WHERE id = ?", (1 if lost else 0, tag_id))
    db.commit()


def available_tags(species="sheep", tag_type=None):
    return [
        t for t in list_tags(species)
        if not t["used"] and not t["lost"] and (tag_type is None or t["tag_type"] == tag_type)
    ]


# --- herd log ------------------------------------------------------------------


def insert_herd_events(events, commit=True):
    db = get_db()
    created = clock.now().isoformat()
    ids = [
        _insert_row(db, "herd_event", HERD_EVENT_FIELDS, e, {"created_at": created})
        for e in events
    ]
    if commit:
        db.commit()
    return ids


def list_herd_events(species=None, ppn=None, individual_number=None, kind=None, year=None):
    clauses, params = [], []
    if species:
        clauses.append("species = ?")
        params.append(species)
    if ppn and individual_number:
        clauses.append("ppn = ? AND individual_number = ?")
        params.extend([ppn, individual_number])
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if year and str(year).isdigit():
        clauses.append("substr(event_date, 1, 4) = ?")
        params.append(str(year))
    sql = "SELECT * FROM herd_event"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY event_date DESC, id DESC"
    return get_db().execute(sql, params).fetchall()


def delete_herd_event(event_id):
    db = get_db()
    db.execute("DELETE FROM herd_event WHERE id = ?", (event_id,))
    db.commit()


# --- December counts -----------------------------------------------------------


def list_counts():
    return get_db().execute(
        "SELECT * FROM annual_count ORDER BY year DESC, species"
    ).fetchall()


def get_count(year, species):
    return get_db().execute(
        "SELECT * FROM annual_count WHERE year = ? AND species = ?", (year, species)
    ).fetchone()


def save_count(data):
    db = get_db()
    cols = ", ".join(COUNT_FIELDS)
    marks = ", ".join("?" for _ in COUNT_FIELDS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in COUNT_FIELDS[2:])
    db.execute(
        f"INSERT INTO annual_count ({cols}) VALUES ({marks}) "
        f"ON CONFLICT (year, species) DO UPDATE SET {updates}",
        [data.get(c) for c in COUNT_FIELDS],
    )
    db.commit()


def is_empty():
    db = get_db()
    return (
        db.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 0
        and get_holding() is None
    )


def entry_count():
    return get_db().execute("SELECT COUNT(*) FROM entry").fetchone()[0]
