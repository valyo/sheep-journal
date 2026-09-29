"""Demo herd, modelled on the example in Jordbruksverket's journal instructions."""

from datetime import date

from . import clock, store
from .constants import EVENT_TYPES

OWN_PPN = "12345"
SLAUGHTERHOUSE = "700001"


def _entry(event_type, event_date, **fields):
    entry = {
        "event_type": event_type,
        "direction": EVENT_TYPES[event_type].direction,
        "event_date": event_date.isoformat(),
        "species": "sheep",
        "count": 1,
        "breeding": 0,
        "electronic_tag": 0,
    }
    entry.update(fields)
    return entry


def seed():
    if not store.is_empty():
        return False

    today = clock.today()
    last = today.year - 1

    def day(year, month, dd):
        return min(date(year, month, dd), today)

    store.save_holding({
        "ppn": OWN_PPN,
        "keeper_name": "Demo Farm",
        "address": "Fårvägen 1, 123 45 Byn",
        "species": "sheep",
        "category": "Meat (kött)",
        "main_breed": "Gotlandsfår",
        "journal_start": date(last, 2, 2).isoformat(),
    })

    entries = []
    for n in range(1, 6):
        entries.append(_entry(
            "opening_balance", date(last, 2, 2), ppn="76543",
            individual_number=f"0010{n}", sex="F", birth_year=last - 3, breeding=1,
        ))
    entries += [
        _entry("birth", date(last, 4, 25), ppn=OWN_PPN, count=12, birth_year=last),
        _entry(
            "loan_in", date(last, 9, 22), ppn="5554", individual_number="60010", sex="M",
            breeding=1, counterparty="5554", breed="Dorset",
        ),
        _entry(
            "slaughter", date(last, 10, 15), ppn=OWN_PPN, count=9, counterparty=SLAUGHTERHOUSE,
            driver_name="L. Lasso", vehicle_reg="QWX123",
        ),
        _entry(
            "loan_return", date(last, 12, 5), ppn="5554", individual_number="60010",
            counterparty="5554", driver_name="L. Lina", vehicle_reg="ABC321",
        ),
        _entry(
            "recruitment_out", day(today.year, 2, 1), ppn=OWN_PPN, counterparty=OWN_PPN,
            birth_year=last, notes="Individnr 00201",
        ),
        _entry(
            "recruitment_in", day(today.year, 2, 1), ppn=OWN_PPN, individual_number="00201",
            sex="F", birth_year=last, breeding=1, counterparty=OWN_PPN,
        ),
        _entry(
            "slaughter", day(today.year, 2, 1), ppn=OWN_PPN, count=2,
            counterparty=SLAUGHTERHOUSE, driver_name="L. Lasso", vehicle_reg="QWX123",
        ),
    ]
    for entry in entries:
        # Pretend each entry was made on the day of the event.
        store.insert_entry(entry, created_at=f"{entry['event_date']}T18:00:00")

    store.save_count({
        "year": last,
        "species": "sheep",
        "count_date": date(last, 12, 15).isoformat(),
        "total": 8,
        "ewes": 5,
        "rams": 0,
        "lambs": 3,
        "reported_on": day(today.year, 1, 10).isoformat(),
    })
    return True
