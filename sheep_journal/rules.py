"""Form parsing and the record-keeping rules from Jordbruksverket.

Summary of the rules enforced here (stalljournal for sheep and goats):

* Every arrival, departure, birth and death is recorded, in date order, within
  48 hours. Births may be recorded once all lambs are born and tagged, but no
  later than 6 months after the first lamb was born.
* Animals intended to live 12 months or longer (livdjur) are recorded one per
  row with their individual number. Slaughter lambs may be recorded as groups.
* Movements record the other holding (supplier / recipient) and, when animals
  are transported, the driver's name and the vehicle's registration number.
* Deaths are recorded with the date and a documented cause of death.
* Records are kept for at least 5 years (entries are voided, never deleted).
* Between 1 and 31 December all animals are counted and the number reported.
"""

import re
from datetime import date

from flask import url_for

from . import store
from .constants import (
    EVENT_TYPES,
    EXEMPT_FROM_48H,
    HOLDING_SPECIES,
    SEXES,
    SPECIES,
    holding_species,
)


def _text(form, name, upper=False):
    value = (form.get(name) or "").strip()
    if upper:
        value = value.upper()
    return value or None


def _checkbox(form, name):
    return 1 if form.get(name) in ("1", "on", "true", 1, True) else 0


def _int(form, name, errors, label):
    raw = (form.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        errors[name] = f"{label} must be a whole number."
        return None


def _date(form, name, errors, label, required=True):
    raw = (form.get(name) or "").strip()
    if not raw:
        if required:
            errors[name] = f"Enter the {label}."
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        errors[name] = f"The {label} must be a date (YYYY-MM-DD)."
        return None


def normalize_ppn(value):
    """'SE 12 345' -> '12345'. Foreign animals keep their country code."""
    if not value:
        return None
    value = re.sub(r"[\s-]", "", value.upper())
    if re.fullmatch(r"SE\d+", value):
        value = value[2:]
    return value or None


def is_late(entry):
    """True when the entry was certainly made more than 48 hours after the event."""
    if entry["event_type"] in EXEMPT_FROM_48H:
        return False
    created = date.fromisoformat(entry["created_at"][:10])
    return (created - date.fromisoformat(entry["event_date"])).days >= 3


def entry_flags(entry):
    if entry["voided_at"]:
        return []
    event = EVENT_TYPES.get(entry["event_type"])
    flags = []
    if is_late(entry):
        flags.append("late")
    if event and event.transport and not (entry["driver_name"] and entry["vehicle_reg"]):
        flags.append("no_transport")
    if entry["event_type"] == "death" and not entry["cause_of_death"]:
        flags.append("no_cause")
    return flags


# --- journal entries -----------------------------------------------------------


def parse_entry_form(form):
    """Turn submitted form data into an entry dict. Returns (entry, errors)."""
    errors = {}
    event = EVENT_TYPES.get(form.get("event_type") or "")
    if event is None:
        errors["event_type"] = "Choose what happened."

    entry = {
        "event_type": event.key if event else None,
        "direction": event.direction if event else None,
        "event_date": _date(form, "event_date", errors, "date"),
        "species": form.get("species") or "sheep",
        "ppn": normalize_ppn(form.get("ppn")),
        "individual_number": _text(form, "individual_number"),
        "count": _int(form, "count", errors, "Number of animals"),
        "sex": form.get("sex") or None,
        "birth_year": _int(form, "birth_year", errors, "Birth year"),
        "breeding": _checkbox(form, "breeding"),
        "counterparty": _text(form, "counterparty"),
        "driver_name": _text(form, "driver_name"),
        "vehicle_reg": _text(form, "vehicle_reg", upper=True),
        "cause_of_death": _text(form, "cause_of_death"),
        "breed": _text(form, "breed"),
        "genotype": _text(form, "genotype"),
        "electronic_tag": _checkbox(form, "electronic_tag"),
        "previous_id": _text(form, "previous_id"),
        "notes": _text(form, "notes"),
    }

    if entry["individual_number"]:
        if entry["count"] not in (None, 1):
            errors["count"] = "An individually numbered animal is recorded on its own row (count 1)."
        entry["count"] = 1
    elif entry["count"] is None and "count" not in errors:
        entry["count"] = 1
    elif entry["count"] is not None and entry["count"] < 1:
        errors["count"] = "Number of animals must be at least 1."

    return entry, errors


def validate_entry(entry, holding, today, entry_id=None):
    """Check an entry against the rules. Returns (errors, warnings).

    Errors block saving. Warnings are shown and must be acknowledged.
    """
    errors, warnings = {}, []
    event = EVENT_TYPES[entry["event_type"]]
    event_date = date.fromisoformat(entry["event_date"])

    if event_date > today:
        errors["event_date"] = "The date can't be in the future."
    if entry["species"] not in SPECIES:
        errors["species"] = "Choose sheep or goat."
    elif holding and entry["species"] not in holding_species(holding):
        warnings.append(
            f"Your holding is registered for {HOLDING_SPECIES[holding['species']].lower()}, "
            f"but this entry is for {SPECIES[entry['species']].lower()}."
        )
    if not entry["ppn"]:
        errors["ppn"] = (
            "Enter the production site number (PPN) from the ear tag, "
            "or the country code for animals from another EU country."
        )
    if entry["sex"] and entry["sex"] not in SEXES:
        errors["sex"] = "Choose female or male."

    individual = entry["individual_number"]
    if entry["breeding"] and not individual:
        message = (
            "Animals intended to live 12 months or longer must be recorded individually, "
            "with their individual number."
        )
        if event.key in ("temp_out", "return_home", "opening_balance"):
            warnings.append(
                message + " Group recording is only allowed for moves between holdings "
                "where you are the registered keeper."
            )
        else:
            errors["individual_number"] = message

    if event.key == "birth":
        if not entry["birth_year"]:
            errors["birth_year"] = "Births must be recorded with the birth year."
        elif not event_date.year - 1 <= entry["birth_year"] <= event_date.year:
            errors["birth_year"] = (
                "The birth year must match the identification date: lambs and kids are "
                "tagged at most 6 months after birth."
            )
    elif entry["birth_year"] and entry["birth_year"] > event_date.year:
        errors["birth_year"] = "The birth year can't be after the date of the event."

    if event.movement and not entry["counterparty"]:
        who = "supplier" if event.direction == "in" else "recipient"
        errors["counterparty"] = (
            f"Enter the {who}: the other holding's PPN, or name and address."
        )
    if event.transport and not (entry["driver_name"] and entry["vehicle_reg"]):
        warnings.append(
            "When animals are transported, record the driver's name and the registration "
            "number of the vehicle part that carries the animals. Leave these empty only if "
            "the animals were not transported (e.g. walked to nearby grazing)."
        )
    if event.key == "death" and not entry["cause_of_death"]:
        errors["cause_of_death"] = (
            "Record the cause of death. Dead animals must be documented with the cause."
        )

    if errors:
        return errors, warnings

    # Consistency with what the journal already says.
    stock = store.balance(exclude_id=entry_id).get(entry["species"], {"present": 0, "away": 0})
    species_name = SPECIES[entry["species"]].split(" ")[0].lower()
    if event.direction == "out" and entry["count"] > stock["present"]:
        warnings.append(
            f"The journal shows {stock['present']} {species_name} on the holding, so this "
            "entry makes the balance negative. Check that all arrivals and births are recorded."
        )
    if event.key == "return_home" and entry["count"] > stock["away"]:
        warnings.append(
            f"The journal shows {stock['away']} {species_name} temporarily away, "
            "fewer than are returning."
        )

    if individual:
        key = (entry["species"], entry["ppn"], individual)
        status = store.individual_animals(exclude_id=entry_id).get(key, {}).get("status")
        label = f"{entry['ppn']}-{individual}"
        if event.direction == "out" and status != "present":
            warnings.append(f"Animal {label} is not recorded as present on the holding.")
        elif event.key == "return_home" and status != "away":
            warnings.append(f"Animal {label} is not recorded as temporarily away.")
        elif event.direction == "in" and event.key != "return_home" and status in ("present", "away"):
            warnings.append(f"Animal {label} is already recorded as being on the holding.")

    if entry_id is None and event.key not in EXEMPT_FROM_48H and (today - event_date).days >= 3:
        warnings.append(
            "This event is more than 48 hours old. Entries must be made within 48 hours; "
            "the entry will be marked as late."
        )

    return errors, warnings


# --- holding and December count ------------------------------------------------


def parse_holding_form(form):
    errors = {}
    data = {
        "ppn": normalize_ppn(form.get("ppn")),
        "keeper_name": _text(form, "keeper_name"),
        "address": _text(form, "address"),
        "species": form.get("species") or "sheep",
        "category": _text(form, "category"),
        "main_breed": _text(form, "main_breed"),
        "journal_start": _date(form, "journal_start", errors, "journal start date", required=False),
    }
    if not data["ppn"]:
        errors["ppn"] = "Enter your production site number (PPN)."
    if not data["keeper_name"]:
        errors["keeper_name"] = "Enter the name of the registered animal keeper."
    if data["species"] not in HOLDING_SPECIES:
        errors["species"] = "Choose which animals you keep."
    return data, errors


def parse_count_form(form):
    errors = {}
    data = {
        "year": _int(form, "year", errors, "Year"),
        "species": form.get("species") or "sheep",
        "count_date": _date(form, "count_date", errors, "count date"),
        "total": _int(form, "total", errors, "Total"),
        "ewes": _int(form, "ewes", errors, "Females"),
        "rams": _int(form, "rams", errors, "Males"),
        "lambs": _int(form, "lambs", errors, "Young"),
        "reported_on": _date(form, "reported_on", errors, "reporting date", required=False),
        "notes": _text(form, "notes"),
    }
    if data["year"] is None and "year" not in errors:
        errors["year"] = "Enter the year."
    if data["species"] not in SPECIES:
        errors["species"] = "Choose sheep or goat."
    if data["total"] is None and "total" not in errors:
        errors["total"] = "Enter the total number of animals counted."
    for name in ("total", "ewes", "rams", "lambs"):
        if data[name] is not None and data[name] < 0:
            errors[name] = "Numbers can't be negative."
    if data["count_date"] and data["year"]:
        counted = date.fromisoformat(data["count_date"])
        if counted.year != data["year"] or counted.month != 12:
            errors["count_date"] = f"Count on a day between 1 and 31 December {data['year']}."
    parts = [data["ewes"], data["rams"], data["lambs"]]
    if all(p is not None for p in parts) and data["total"] is not None and sum(parts) != data["total"]:
        errors["total"] = f"Females + males + young = {sum(parts)}, which doesn't match the total."
    if data["reported_on"] and data["count_date"] and data["reported_on"] < data["count_date"]:
        errors["reported_on"] = "You can't report before you have counted."
    return data, errors


# --- dashboard -----------------------------------------------------------------


def compliance_warnings(holding, today):
    """Things the keeper should act on. List of (level, message, link)."""
    items = []
    if holding is None:
        items.append((
            "error",
            "Set up your holding (PPN and animal keeper) before you start recording.",
            url_for("main.holding"),
        ))
        return items

    for species, stock in store.balance().items():
        if stock["present"] < 0:
            items.append((
                "error",
                f"The journal balance for {SPECIES[species].lower()} is negative "
                f"({stock['present']}). Some arrivals or births are missing.",
                url_for("journal.index", species=species),
            ))

    entries = store.list_entries(include_voided=False)
    flag_counts = {"late": 0, "no_transport": 0, "no_cause": 0}
    for entry in entries:
        for flag in entry_flags(entry):
            flag_counts[flag] += 1
    if flag_counts["no_cause"]:
        items.append((
            "error",
            f"{flag_counts['no_cause']} death(s) recorded without a cause of death.",
            url_for("journal.index", flag="no_cause"),
        ))
    if flag_counts["no_transport"]:
        items.append((
            "warning",
            f"{flag_counts['no_transport']} departure(s) without transporter details. "
            "Fine if the animals weren't transported; otherwise add driver and vehicle.",
            url_for("journal.index", flag="no_transport"),
        ))
    if flag_counts["late"]:
        items.append((
            "warning",
            f"{flag_counts['late']} entr{'y was' if flag_counts['late'] == 1 else 'ies were'} "
            "recorded more than 48 hours after the event.",
            url_for("journal.index", flag="late"),
        ))

    first_entry = entries[0]["event_date"] if entries else None
    last_year = today.year - 1
    for species in holding_species(holding):
        name = SPECIES[species].lower()
        if today.month == 12 and store.get_count(today.year, species) is None:
            items.append((
                "info",
                f"December: count all {name} on the holding on any day this month "
                "and report the number to Jordbruksverket.",
                url_for("main.counts"),
            ))
        previous = store.get_count(last_year, species)
        if previous is None and first_entry and first_entry <= f"{last_year}-12-31":
            items.append((
                "warning",
                f"No December count recorded for {name} in {last_year}.",
                url_for("main.counts"),
            ))
        elif previous is not None and not previous["reported_on"]:
            items.append((
                "info",
                f"The December {last_year} count for {name} is not marked as reported "
                "to Jordbruksverket.",
                url_for("main.counts", year=last_year, species=species),
            ))
    return items
