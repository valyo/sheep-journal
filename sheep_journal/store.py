"""Database reads and writes."""

from . import clock
from .constants import EVENT_TYPES
from .db import get_db

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
)

HOLDING_FIELDS = ("ppn", "keeper_name", "address", "species", "category", "main_breed", "journal_start")

COUNT_FIELDS = (
    "year", "species", "count_date", "total", "ewes", "rams", "lambs", "reported_on", "notes",
)


# --- holding -----------------------------------------------------------------


def get_holding():
    return get_db().execute("SELECT * FROM holding WHERE id = 1").fetchone()


def save_holding(data):
    db = get_db()
    cols = ", ".join(HOLDING_FIELDS)
    marks = ", ".join("?" for _ in HOLDING_FIELDS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in HOLDING_FIELDS)
    db.execute(
        f"INSERT INTO holding (id, {cols}) VALUES (1, {marks}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}",
        [data.get(c) for c in HOLDING_FIELDS],
    )
    db.commit()


# --- journal entries -----------------------------------------------------------


def _insert(db, entry, created_at=None):
    cols = ENTRY_FIELDS + ("created_at",)
    values = [entry.get(c) for c in ENTRY_FIELDS]
    values.append(created_at or clock.now().isoformat())
    cur = db.execute(
        f"INSERT INTO entry ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        values,
    )
    return cur.lastrowid


def insert_entry(entry, created_at=None):
    db = get_db()
    entry_id = _insert(db, entry, created_at)
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
    assignments = ", ".join(f"{c} = ?" for c in ENTRY_FIELDS)
    db.execute(
        f"UPDATE entry SET {assignments}, updated_at = ? WHERE id = ?",
        [entry.get(c) for c in ENTRY_FIELDS] + [clock.now().isoformat(), entry_id],
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


def balance(as_of=None, exclude_id=None):
    """Animals per species according to the journal.

    present: on the holding right now. away: temporarily away (tillfälligt ute).
    """
    sql = """
        SELECT species,
               SUM(CASE WHEN direction = 'in' THEN count ELSE -count END) AS present,
               SUM(CASE WHEN event_type = 'temp_out' THEN count
                        WHEN event_type = 'return_home' THEN -count
                        ELSE 0 END) AS away
          FROM entry
         WHERE voided_at IS NULL
    """
    params = []
    if as_of:
        sql += " AND event_date <= ?"
        params.append(as_of)
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


def individual_animals(exclude_id=None):
    """Fold all individually recorded rows into one record per animal."""
    sql = "SELECT * FROM entry WHERE voided_at IS NULL AND individual_number IS NOT NULL"
    params = []
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    sql += " ORDER BY event_date, id"

    animals = {}
    for row in get_db().execute(sql, params):
        key = (row["species"], row["ppn"], row["individual_number"])
        animal = animals.setdefault(
            key,
            {
                "species": row["species"],
                "ppn": row["ppn"],
                "individual_number": row["individual_number"],
                "first_date": row["event_date"],
                "sex": None,
                "birth_year": None,
                "breed": None,
                "genotype": None,
                "electronic_tag": False,
                "events": 0,
            },
        )
        animal["events"] += 1
        for field in ("sex", "birth_year", "breed", "genotype"):
            if row[field]:
                animal[field] = row[field]
        if row["electronic_tag"]:
            animal["electronic_tag"] = True
        animal["last_event"] = row["event_type"]
        animal["last_date"] = row["event_date"]
        animal["status"] = status_after(row["event_type"])
    return animals


def animal_history(species, ppn, individual_number):
    return get_db().execute(
        "SELECT * FROM entry WHERE species = ? AND ppn = ? AND individual_number = ? "
        "ORDER BY event_date, id",
        (species, ppn, individual_number),
    ).fetchall()


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
