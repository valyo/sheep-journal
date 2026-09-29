from . import clock, store
from .constants import (
    CATEGORIES,
    EVENT_TYPES,
    FLAG_LABELS,
    HOLDING_SPECIES,
    SEXES,
    SPECIES,
)


def event_label(key):
    event = EVENT_TYPES.get(key)
    return event.label if event else key


def event_label_sv(key):
    event = EVENT_TYPES.get(key)
    return event.label_sv if event else key


def remarks(entry, holding=None):
    """The 'Övrigt' column of the paper journal."""
    parts = [event_label_sv(entry["event_type"])]
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
    app.add_template_filter(lambda key: SPECIES.get(key, key), "species_label")
    app.add_template_filter(lambda key: SEXES.get(key, key or ""), "sex_label")

    @app.context_processor
    def inject_globals():
        return {
            "holding": store.get_holding(),
            "today": clock.today(),
            "EVENT_TYPES": EVENT_TYPES,
            "SPECIES": SPECIES,
            "HOLDING_SPECIES": HOLDING_SPECIES,
            "SEXES": SEXES,
            "CATEGORY_OPTIONS": {c: c for c in CATEGORIES},
            "FLAG_LABELS": FLAG_LABELS,
            "remarks": remarks,
        }
