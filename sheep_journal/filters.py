from flask import g

from . import clock, store
from .constants import (
    CATEGORIES,
    CONTACT_KINDS,
    EVENT_TYPES,
    FLAG_LABELS,
    HERD_EVENT_KINDS,
    HOLDING_SPECIES,
    MEDICINE_KINDS,
    SEXES,
    SPECIES,
    TAG_TYPES,
)
from .ids import tag_label


def event_label(key):
    event = EVENT_TYPES.get(key)
    return event.label if event else key


def event_label_sv(key):
    event = EVENT_TYPES.get(key)
    return event.label_sv if event else key


def _contacts_by_ppn():
    if "contacts_by_ppn" not in g:
        g.contacts_by_ppn = {c["ppn"]: c for c in store.list_contacts() if c["ppn"]}
    return g.contacts_by_ppn


def party(value):
    """A supplier / recipient PPN with the name from the contact register."""
    if not value:
        return ""
    contact = _contacts_by_ppn().get(value)
    if contact:
        return f"{value} ({contact['name']})"
    holding = store.get_holding()
    if holding and value == holding["ppn"]:
        return f"{value} (egen anläggning)"
    return value


def remarks(entry, holding=None):
    """The 'Övrigt' column of the paper journal."""
    parts = [event_label_sv(entry["event_type"])]
    sexes = []
    if entry["males"]:
        sexes.append(f"{entry['males']} {'bagge' if entry['males'] == 1 else 'baggar'}")
    if entry["females"]:
        sexes.append(f"{entry['females']} {'tacka' if entry['females'] == 1 else 'tackor'}")
    if sexes:
        parts[0] += f" ({', '.join(sexes)})"
    if entry["mother_id"]:
        parts.append(f"mor {entry['mother_id']}")
    main_breed = holding["main_breed"] if holding else None
    if entry["breed"] and entry["breed"] != main_breed:
        parts.append(entry["breed"])
    if entry["genotype"]:
        parts.append(f"genotyp {entry['genotype']}")
    if entry["electronic_tag"]:
        parts.append("elektroniskt märke")
    if entry["previous_id"]:
        parts.append(f"tidigare ID {entry['previous_id']}")
    if entry["cause_of_death"]:
        parts.append(f"dödsorsak: {entry['cause_of_death']}")
    if entry["notes"]:
        parts.append(entry["notes"])
    return ", ".join(parts)


def init_app(app):
    app.add_template_filter(event_label)
    app.add_template_filter(event_label_sv)
    app.add_template_filter(party)
    app.add_template_filter(lambda key: SPECIES.get(key, key), "species_label")
    app.add_template_filter(lambda key: SEXES.get(key, key or ""), "sex_label")
    app.add_template_filter(lambda key: TAG_TYPES.get(key, key or ""), "tag_type_label")
    app.add_template_filter(lambda key: HERD_EVENT_KINDS.get(key, key), "herd_kind_label")

    @app.context_processor
    def inject_globals():
        return {
            "holding": store.get_holding(),
            "today": clock.today(),
            "EVENT_TYPES": EVENT_TYPES,
            "SPECIES": SPECIES,
            "HOLDING_SPECIES": HOLDING_SPECIES,
            "SEXES": SEXES,
            "TAG_TYPES": TAG_TYPES,
            "CONTACT_KINDS": CONTACT_KINDS,
            "HERD_EVENT_KINDS": HERD_EVENT_KINDS,
            "MEDICINE_KINDS": MEDICINE_KINDS,
            "CATEGORY_OPTIONS": {c: c for c in CATEGORIES},
            "FLAG_LABELS": FLAG_LABELS,
            "remarks": remarks,
            "tag_label": tag_label,
        }
