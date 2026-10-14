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
* Animals kept beyond 12 months carry two ear tags; slaughter lambs may carry one.
* Medicine use is recorded (product, dose, withdrawal period) and kept 5 years.
"""

import re
from datetime import date

from flask import url_for

from . import store
from .constants import (
    CONTACT_KINDS,
    EVENT_TYPES,
    EXEMPT_FROM_48H,
    HERD_EVENT_KINDS,
    HOLDING_SPECIES,
    MEDICINE_KINDS,
    SEXES,
    SPECIES,
    SPECIES_PLURAL,
    TAG_TYPES,
    holding_species,
)
from .ids import animal_ref, normalize_ref


def _text(form, name, upper=False):
    value = (form.get(name) or "").strip()
    if upper:
        value = value.upper()
    return value or None


def _checkbox(form, name):
    return 1 if form.get(name) in ("1", "on", "true", 1, True) else 0


def _int(form, name, errors, label):
    raw = str(form.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        errors[name] = f"{label} måste vara ett heltal."
        return None


def _float(form, name, errors, label):
    raw = str(form.get(name) or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        errors[name] = f"{label} måste vara ett tal."
        return None


def _date(form, name, errors, label, required=True):
    raw = (form.get(name) or "").strip()
    if not raw:
        if required:
            errors[name] = f"Ange {label}."
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        errors[name] = f"{label.capitalize()} måste vara ett datum (ÅÅÅÅ-MM-DD)."
        return None


def normalize_ppn(value):
    """'SE 12 345' -> '12345'. Foreign animals keep their country code."""
    if not value:
        return None
    value = re.sub(r"[\s-]", "", value.upper())
    if re.fullmatch(r"SE\d+", value):
        value = value[2:]
    return value or None


def real_vehicle_reg(value):
    """False for empty values and placeholders like 'XXX 000'."""
    if not value:
        return False
    compact = re.sub(r"[\s-]", "", value.upper())
    if re.fullmatch(r"X+0*", compact) or re.fullmatch(r"[X0]+", compact):
        return False
    return bool(re.search(r"[A-Z]", compact) and re.search(r"\d", compact))


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
    if event and event.transport and not (entry["driver_name"] and real_vehicle_reg(entry["vehicle_reg"])):
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
        errors["event_type"] = "Välj vad som hände."

    entry = {
        "event_type": event.key if event else None,
        "direction": event.direction if event else None,
        "event_date": _date(form, "event_date", errors, "datum"),
        "species": form.get("species") or "sheep",
        "ppn": normalize_ppn(form.get("ppn")),
        "individual_number": _text(form, "individual_number"),
        "count": _int(form, "count", errors, "Antal djur"),
        "sex": form.get("sex") or None,
        "birth_year": _int(form, "birth_year", errors, "Födelseår"),
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
        "mother_id": normalize_ref(form.get("mother_id")),
        "males": _int(form, "males", errors, "Antal hanar"),
        "females": _int(form, "females", errors, "Antal honor"),
    }
    if event and event.key != "birth":
        entry["males"] = entry["females"] = None
    if event and event.key not in ("birth", "tagging", "recruitment_in"):
        entry["mother_id"] = None

    if entry["individual_number"]:
        if entry["count"] not in (None, 1):
            errors["count"] = "Ett djur med individnummer förs in på en egen rad (antal 1)."
        entry["count"] = 1
    elif entry["count"] is None and "count" not in errors:
        entry["count"] = 1
    elif entry["count"] is not None and entry["count"] < 1:
        errors["count"] = "Antal djur måste vara minst 1."

    return entry, errors


def validate_entry(entry, holding, today, entry_id=None):
    """Check an entry against the rules. Returns (errors, warnings).

    Errors block saving. Warnings are shown and must be acknowledged.
    """
    errors, warnings = {}, []
    event = EVENT_TYPES[entry["event_type"]]
    event_date = date.fromisoformat(entry["event_date"])

    if event_date > today:
        errors["event_date"] = "Datumet kan inte ligga i framtiden."
    if entry["species"] not in SPECIES:
        errors["species"] = "Välj får eller get."
    elif holding and entry["species"] not in holding_species(holding):
        warnings.append(
            f"Anläggningen är registrerad för {HOLDING_SPECIES[holding['species']].lower()}, "
            f"men raden gäller {SPECIES_PLURAL[entry['species']]}."
        )
    if not entry["ppn"]:
        errors["ppn"] = (
            "Ange produktionsplatsnumret (PPN) från öronmärket, "
            "eller landskoden för djur från ett annat EU-land."
        )
    if entry["sex"] and entry["sex"] not in SEXES:
        errors["sex"] = "Välj hona eller hane."

    individual = entry["individual_number"]
    if entry["breeding"] and not individual:
        message = (
            "Djur som ska leva 12 månader eller längre (livdjur) ska journalföras "
            "individuellt, med individnummer."
        )
        if event.key in ("temp_out", "return_home", "opening_balance"):
            warnings.append(
                message + " Gruppvis journalföring är bara tillåten vid flytt mellan "
                "produktionsplatser där du själv är registrerad djurhållare."
            )
        else:
            errors["individual_number"] = message

    if event.key == "birth":
        if not entry["birth_year"]:
            errors["birth_year"] = "Födslar ska journalföras med födelseår."
        elif not event_date.year - 1 <= entry["birth_year"] <= event_date.year:
            errors["birth_year"] = (
                "Födelseåret måste stämma med identifieringsdatumet: lamm och killingar "
                "märks senast 6 månader efter födseln."
            )
    elif entry["birth_year"] and entry["birth_year"] > event_date.year:
        errors["birth_year"] = "Födelseåret kan inte vara senare än händelsedatumet."

    if event.key == "birth":
        split = (entry["males"] or 0) + (entry["females"] or 0)
        if split > entry["count"]:
            errors["males"] = f"Hanar + honor ({split}) är fler än antalet födda."
    if event.key == "tagging":
        if not individual:
            errors["individual_number"] = "Vid öronmärkning anges djurets individnummer."
        if not entry["birth_year"]:
            errors["birth_year"] = "Ange födelseår för det märkta djuret."
        if holding and entry["ppn"] and entry["ppn"] != holding["ppn"]:
            warnings.append(
                f"Djur som föds här märks med ditt eget PPN ({holding['ppn']}), "
                f"inte {entry['ppn']}."
            )

    if event.movement and not entry["counterparty"]:
        who = "leverantör" if event.direction == "in" else "mottagare"
        errors["counterparty"] = (
            f"Ange {who}: den andra produktionsplatsens PPN, eller namn och adress."
        )
    if event.transport and entry["vehicle_reg"] and not real_vehicle_reg(entry["vehicle_reg"]):
        warnings.append(
            f"'{entry['vehicle_reg']}' ser inte ut som ett registreringsnummer. "
            "Ange det riktiga numret på fordonet eller släpet som djuren transporterades i."
        )
    elif event.transport and not (entry["driver_name"] and entry["vehicle_reg"]):
        warnings.append(
            "När djur transporteras ska chaufförens namn och registreringsnumret för den del "
            "av fordonet som djuren finns i antecknas. Lämna tomt bara om djuren inte "
            "transporterades (t.ex. gick till närliggande bete)."
        )
    if event.key == "death" and not entry["cause_of_death"]:
        errors["cause_of_death"] = (
            "Ange dödsorsak. Döda djur ska dokumenteras med orsaken till att de dött."
        )

    if errors:
        return errors, warnings

    # Consistency with what the journal already says.
    stock = store.balance(exclude_id=entry_id).get(entry["species"], {"present": 0, "away": 0})
    species_name = SPECIES_PLURAL[entry["species"]]
    if event.direction == "out" and entry["count"] > stock["present"]:
        warnings.append(
            f"Enligt journalen finns {stock['present']} {species_name} på anläggningen, så "
            "raden gör saldot negativt. Kontrollera att alla inkomna och födda djur är införda."
        )
    if event.key == "return_home" and entry["count"] > stock["away"]:
        warnings.append(
            f"Enligt journalen är {stock['away']} {species_name} tillfälligt ute, "
            "färre än de som kommer tillbaka."
        )

    animals = store.individual_animals(exclude_id=entry_id)
    if individual:
        key = (entry["species"], entry["ppn"], individual)
        animal = animals.get(key, {})
        status = animal.get("status")
        label = animal_ref(entry["ppn"], individual)
        if event.direction == "out" and status != "present":
            warnings.append(f"Djur {label} är inte registrerat som närvarande på anläggningen.")
        elif event.key == "return_home" and status != "away":
            warnings.append(f"Djur {label} är inte registrerat som tillfälligt ute.")
        elif event.direction == "in" and event.key != "return_home" and status in ("present", "away"):
            warnings.append(f"Djur {label} är redan registrerat som närvarande på anläggningen.")
        if entry["breeding"] and animal.get("tag_type") == "single":
            warnings.append(double_tag_warning(label))

    if entry["mother_id"]:
        known = {a["ref"]: a for a in animals.values()}
        mother = known.get(entry["mother_id"])
        if mother is None:
            warnings.append(f"Modern {entry['mother_id']} finns inte i djurregistret.")
        elif mother["sex"] == "M":
            warnings.append(f"{entry['mother_id']} är registrerad som hane.")

    if entry_id is None and event.key not in EXEMPT_FROM_48H and (today - event_date).days >= 3:
        warnings.append(
            "Händelsen är mer än 48 timmar gammal. Uppgifter ska föras in inom 48 timmar; "
            "raden markeras som sent införd."
        )

    return errors, warnings


def older_than_12_months(animal, today):
    """Conservative: with only a birth year, assume the animal was born on 31 December."""
    birth_date = animal.get("birth_date")
    if birth_date and len(birth_date) == 10:
        born = date.fromisoformat(birth_date)
    elif birth_date and len(birth_date) == 7:
        born = date(int(birth_date[:4]), int(birth_date[5:7]), 28)
    elif animal.get("birth_year"):
        born = date(animal["birth_year"], 12, 31)
    else:
        return False
    return (today - born).days > 365


def double_tag_warning(label):
    return (
        f"Djur {label} har bara ett öronmärke. Djur som hålls längre än 12 månader ska "
        "ha två öronmärken: beställ ett ersättningspar eller ett andra märke."
    )


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
        "journal_start": _date(form, "journal_start", errors, "startdatum för journalen", required=False),
        "postal_address": _text(form, "postal_address"),
        "county": _text(form, "county"),
        "municipality": _text(form, "municipality"),
        "property_designation": _text(form, "property_designation"),
        "area_ha": _float(form, "area_ha", errors, "Areal"),
        "housing": _text(form, "housing"),
        "max_capacity": _int(form, "max_capacity", errors, "Max kapacitet"),
        "registered_from": _date(form, "registered_from", errors, "registreringsdatum", required=False),
        "phone": _text(form, "phone"),
        "email": _text(form, "email"),
    }
    if not data["ppn"]:
        errors["ppn"] = "Ange ditt produktionsplatsnummer (PPN)."
    if not data["keeper_name"]:
        errors["keeper_name"] = "Ange namnet på den registrerade djurhållaren."
    if data["species"] not in HOLDING_SPECIES:
        errors["species"] = "Välj vilka djur du håller."
    return data, errors


def parse_count_form(form):
    errors = {}
    data = {
        "year": _int(form, "year", errors, "År"),
        "species": form.get("species") or "sheep",
        "count_date": _date(form, "count_date", errors, "datum för räkningen"),
        "total": _int(form, "total", errors, "Totalt antal"),
        "ewes": _int(form, "ewes", errors, "Honor"),
        "rams": _int(form, "rams", errors, "Hanar"),
        "lambs": _int(form, "lambs", errors, "Ungdjur"),
        "reported_on": _date(form, "reported_on", errors, "rapporteringsdatum", required=False),
        "notes": _text(form, "notes"),
    }
    if data["year"] is None and "year" not in errors:
        errors["year"] = "Ange år."
    if data["species"] not in SPECIES:
        errors["species"] = "Välj får eller get."
    if data["total"] is None and "total" not in errors:
        errors["total"] = "Ange totalt antal räknade djur."
    for name in ("total", "ewes", "rams", "lambs"):
        if data[name] is not None and data[name] < 0:
            errors[name] = "Antal kan inte vara negativa."
    if data["count_date"] and data["year"]:
        counted = date.fromisoformat(data["count_date"])
        if counted.year != data["year"] or counted.month != 12:
            errors["count_date"] = f"Räkningen ska göras en dag mellan 1 och 31 december {data['year']}."
    parts = [data["ewes"], data["rams"], data["lambs"]]
    if all(p is not None for p in parts) and data["total"] is not None and sum(parts) != data["total"]:
        errors["total"] = f"Honor + hanar + ungdjur = {sum(parts)}, vilket inte stämmer med totalen."
    if data["reported_on"] and data["count_date"] and data["reported_on"] < data["count_date"]:
        errors["reported_on"] = "Du kan inte rapportera innan du har räknat."
    return data, errors


# --- registers: contacts, animals, ear tags, herd log ---------------------------


def parse_contact_form(form):
    errors = {}
    data = {
        "ppn": normalize_ppn(form.get("ppn")),
        "name": _text(form, "name"),
        "keeper": _text(form, "keeper"),
        "kind": form.get("kind") or "farm",
        "address": _text(form, "address"),
        "phone": _text(form, "phone"),
        "email": _text(form, "email"),
        "notes": _text(form, "notes"),
    }
    if not data["name"]:
        errors["name"] = "Ange gårdens eller företagets namn."
    if data["kind"] not in CONTACT_KINDS:
        errors["kind"] = "Välj typ."
    return data, errors


def _partial_date(form, name, errors, label):
    """YYYY-MM-DD, or YYYY-MM when the day is unknown."""
    raw = (form.get(name) or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        return raw
    return _date(form, name, errors, label, required=False)


def parse_animal_form(form):
    errors = {}
    data = {
        "species": form.get("species") or "sheep",
        "ppn": normalize_ppn(form.get("ppn")),
        "individual_number": _text(form, "individual_number"),
        "tag_year": _int(form, "tag_year", errors, "Årtal på märket"),
        "tag_type": form.get("tag_type") or None,
        "tag_model": _text(form, "tag_model"),
        "tag_colour": _text(form, "tag_colour"),
        "electronic_tag": _checkbox(form, "electronic_tag"),
        "name": _text(form, "name"),
        "sex": form.get("sex") or None,
        "birth_date": _partial_date(form, "birth_date", errors, "födelsedatum"),
        "birth_year": _int(form, "birth_year", errors, "Födelseår"),
        "colour": _text(form, "colour"),
        "breed": _text(form, "breed"),
        "markings": _text(form, "markings"),
        "mother_id": normalize_ref(form.get("mother_id")),
        "mother_name": _text(form, "mother_name"),
        "mother_elite_no": _text(form, "mother_elite_no"),
        "father_id": normalize_ref(form.get("father_id")),
        "father_name": _text(form, "father_name"),
        "father_elite_no": _text(form, "father_elite_no"),
        "elite_no": _text(form, "elite_no"),
        "elite_code": _text(form, "elite_code"),
        "notes": _text(form, "notes"),
    }
    if data["species"] not in SPECIES:
        errors["species"] = "Välj får eller get."
    if not data["ppn"]:
        errors["ppn"] = "Ange PPN på öronmärket."
    if not data["individual_number"]:
        errors["individual_number"] = "Ange individnummer."
    if data["tag_type"] and data["tag_type"] not in TAG_TYPES:
        errors["tag_type"] = "Välj enkelt eller dubbla märken."
    if data["sex"] and data["sex"] not in SEXES:
        errors["sex"] = "Välj hona eller hane."
    if data["birth_date"] and not data["birth_year"]:
        data["birth_year"] = int(data["birth_date"][:4])
    if data["birth_date"] and data["birth_year"] and int(data["birth_date"][:4]) != data["birth_year"]:
        errors["birth_year"] = "Födelseår och födelsedatum stämmer inte överens."
    return data, errors


def parse_tag_range_form(form):
    """A tag order: numbers from..to (inclusive), zero-padded like the first number."""
    errors = {}
    first = (form.get("first") or "").strip()
    last = (form.get("last") or "").strip() or first
    data = {
        "species": form.get("species") or "sheep",
        "tag_type": form.get("tag_type") or "single",
        "tag_model": _text(form, "tag_model"),
        "tag_colour": _text(form, "tag_colour"),
        "order_ref": _text(form, "order_ref"),
    }
    numbers = []
    if not first.isdigit():
        errors["first"] = "Ange första individnumret, t.ex. 00013."
    elif not last.isdigit():
        errors["last"] = "Ange sista individnumret."
    elif int(last) < int(first):
        errors["last"] = "Sista numret måste vara samma som eller efter det första."
    elif int(last) - int(first) >= 1000:
        errors["last"] = "Lägg till högst 1000 märken åt gången."
    else:
        width = max(len(first), 5)
        numbers = [str(n).zfill(width) for n in range(int(first), int(last) + 1)]
    if data["tag_type"] not in TAG_TYPES:
        errors["tag_type"] = "Välj enkelt eller dubbla märken."
    return [{**data, "individual_number": n} for n in numbers], errors


def parse_herd_event_form(form, animal_keys):
    """One herd event per selected animal, or one for a group. Returns (events, errors).

    animal_keys: the (ppn, individual_number) pairs ticked in the form.
    """
    errors = {}
    base = {
        "event_date": _date(form, "event_date", errors, "datum"),
        "kind": form.get("kind") or "",
        "species": form.get("species") or "sheep",
        "subject": _text(form, "subject"),
        "description": _text(form, "description"),
        "product": _text(form, "product"),
        "dose": _text(form, "dose"),
        "withdrawal_until": _date(form, "withdrawal_until", errors, "slutdatum för karenstid", required=False),
        "prescribed_by": _text(form, "prescribed_by"),
        "notes": _text(form, "notes"),
    }
    if base["kind"] not in HERD_EVENT_KINDS:
        errors["kind"] = "Välj vad som gjordes."
    if base["kind"] in MEDICINE_KINDS and not base["product"]:
        errors["product"] = "Ange vilket läkemedel eller vaccin som användes."
    if not animal_keys and not base["subject"]:
        errors["subject"] = "Markera djuren, eller beskriv gruppen (t.ex. alla tackor)."
    if base["withdrawal_until"] and base["event_date"] and base["withdrawal_until"] < base["event_date"]:
        errors["withdrawal_until"] = "Karenstiden kan inte sluta före behandlingen."
    if animal_keys:
        events = [{**base, "ppn": p, "individual_number": n} for p, n in animal_keys]
    else:
        events = [{**base, "ppn": None, "individual_number": None}]
    return events, errors


# --- dashboard -----------------------------------------------------------------


def compliance_warnings(holding, today):
    """Things the keeper should act on. List of (level, message, link)."""
    items = []
    if holding is None:
        items.append((
            "error",
            "Fyll i uppgifterna om anläggningen (PPN och djurhållare) innan du börjar journalföra.",
            url_for("main.holding"),
        ))
        return items

    for species, stock in store.balance().items():
        if stock["present"] < 0:
            items.append((
                "error",
                f"Journalens saldo för {SPECIES_PLURAL[species]} är negativt "
                f"({stock['present']}). Några inkomna eller födda djur saknas.",
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
            f"{flag_counts['no_cause']} dödsfall utan angiven dödsorsak.",
            url_for("journal.index", flag="no_cause"),
        ))
    if flag_counts["no_transport"]:
        items.append((
            "warning",
            f"{flag_counts['no_transport']} utgående rad(er) saknar uppgifter om transportör. "
            "Det går bra om djuren inte transporterades; annars lägg till chaufför och fordon.",
            url_for("journal.index", flag="no_transport"),
        ))
    if flag_counts["late"]:
        items.append((
            "warning",
            f"{flag_counts['late']} rad(er) fördes in mer än 48 timmar efter händelsen.",
            url_for("journal.index", flag="late"),
        ))

    animals = store.individual_animals().values()
    unrecorded = [a for a in animals if a["status"] == "unrecorded"]
    if unrecorded:
        items.append((
            "warning",
            f"{len(unrecorded)} djur i djurregistret saknar rader i journalen. För in hur de "
            "kom till anläggningen (t.ex. öronmärkning av lamm födda här).",
            url_for("animals.index", status="unrecorded"),
        ))
    single_tagged = [
        a for a in animals
        if a["status"] in ("present", "away") and a["tag_type"] == "single"
        and older_than_12_months(a, today)
    ]
    if single_tagged:
        items.append((
            "warning",
            f"{len(single_tagged)} djur äldre än 12 månader har bara ett öronmärke. "
            "Djur som hålls längre än 12 månader ska ha två märken.",
            url_for("animals.index", status="present"),
        ))
    if store.list_tags():
        for tag_type, label in (("single", "enkla"), ("double", "dubbla")):
            left = len(store.available_tags(holding_species(holding)[0], tag_type))
            if left < 3:
                items.append((
                    "info",
                    f"Bara {left} oanvända {label} öronmärken kvar i lager.",
                    url_for("registers.tags"),
                ))

    first_entry = entries[0]["event_date"] if entries else None
    last_year = today.year - 1
    for species in holding_species(holding):
        name = SPECIES_PLURAL[species]
        if today.month == 12 and store.get_count(today.year, species) is None:
            items.append((
                "info",
                f"December: räkna alla {name} på anläggningen en valfri dag den här månaden "
                "och rapportera antalet till Jordbruksverket.",
                url_for("main.counts"),
            ))
        previous = store.get_count(last_year, species)
        if previous is None and first_entry and first_entry <= f"{last_year}-12-31":
            items.append((
                "warning",
                f"Ingen decemberräkning registrerad för {name} {last_year}.",
                url_for("main.counts"),
            ))
        elif previous is not None and not previous["reported_on"]:
            items.append((
                "info",
                f"Decemberräkningen {last_year} för {name} är inte markerad som rapporterad "
                "till Jordbruksverket.",
                url_for("main.counts", year=last_year, species=species),
            ))
    return items
