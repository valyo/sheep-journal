from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import clock, rules, store
from ..constants import EVENT_TYPES, holding_species

bp = Blueprint("journal", __name__, url_prefix="/journal")

FILTERS = ("direction", "species", "year", "event_type", "q", "flag")


def _holding_or_redirect():
    holding = store.get_holding()
    if holding is None:
        flash("Set up your holding first: the journal needs your production site number (PPN).", "warning")
    return holding


def _default_species(holding):
    return holding_species(holding)[0]


def _acknowledged(warnings):
    return set(warnings) <= set(request.form.getlist("ack"))


@bp.route("/")
def index():
    filters = {k: request.args.get(k) or None for k in FILTERS}
    entries = store.list_entries(
        direction=filters["direction"],
        species=filters["species"],
        year=filters["year"],
        event_type=filters["event_type"],
        search=filters["q"],
    )
    rows = [(entry, rules.entry_flags(entry)) for entry in entries]
    if filters["flag"]:
        rows = [row for row in rows if filters["flag"] in row[1]]
    return render_template(
        "journal/list.html", rows=rows, filters=filters, years=store.available_years()
    )


def _save(holding, entry_id=None):
    """Validate the posted entry and save it. Returns (saved_entry, errors, warnings)."""
    entry, errors = rules.parse_entry_form(request.form)
    warnings = []
    if not errors:
        errors, warnings = rules.validate_entry(entry, holding, clock.today(), entry_id)
    if errors or not _acknowledged(warnings):
        return None, errors, warnings
    if entry_id is None:
        store.insert_entry(entry)
    else:
        store.update_entry(entry_id, entry)
    return entry, errors, warnings


@bp.route("/new", methods=["GET", "POST"])
def new():
    holding = _holding_or_redirect()
    if holding is None:
        return redirect(url_for("main.holding"))

    errors, warnings = {}, []
    if request.method == "POST":
        saved, errors, warnings = _save(holding)
        if saved:
            flash(f"Saved: {EVENT_TYPES[saved['event_type']].label}.", "success")
            if "add_another" in request.form:
                return redirect(url_for(
                    ".new",
                    event_type=saved["event_type"],
                    event_date=saved["event_date"],
                    species=saved["species"],
                ))
            return redirect(url_for(".index"))
        values = request.form
    else:
        values = {
            "event_type": request.args.get("event_type", ""),
            "event_date": request.args.get("event_date") or clock.today().isoformat(),
            "species": request.args.get("species") or _default_species(holding),
        }

    event = EVENT_TYPES.get(values.get("event_type") or "")
    direction = event.direction if event else request.args.get("direction", "in")
    if direction not in ("in", "out"):
        direction = "in"
    return render_template(
        "journal/form.html",
        values=values, errors=errors, warnings=warnings, direction=direction, entry=None,
    )


@bp.route("/<int:entry_id>/edit", methods=["GET", "POST"])
def edit(entry_id):
    entry = store.get_entry(entry_id)
    if entry is None:
        abort(404)
    if entry["voided_at"]:
        flash("Voided entries can't be changed.", "warning")
        return redirect(url_for(".index"))
    holding = _holding_or_redirect()
    if holding is None:
        return redirect(url_for("main.holding"))

    errors, warnings = {}, []
    if request.method == "POST":
        if EVENT_TYPES.get(request.form.get("event_type") or "", None) and \
                EVENT_TYPES[request.form["event_type"]].direction != entry["direction"]:
            abort(400)
        saved, errors, warnings = _save(holding, entry_id)
        if saved:
            flash("Entry updated.", "success")
            return redirect(url_for(".index"))
        values = request.form
    else:
        values = dict(entry)
    return render_template(
        "journal/form.html",
        values=values, errors=errors, warnings=warnings, direction=entry["direction"], entry=entry,
    )


@bp.route("/<int:entry_id>/void", methods=["POST"])
def void(entry_id):
    entry = store.get_entry(entry_id)
    if entry is None:
        abort(404)
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Give a reason for voiding the entry.", "error")
        return redirect(url_for(".edit", entry_id=entry_id))
    store.void_entry(entry_id, reason)
    flash("Entry voided. It stays in the journal, crossed out.", "success")
    return redirect(url_for(".index"))


@bp.route("/recruit", methods=["GET", "POST"])
def recruit():
    """Move one group-recorded young animal to individual recording (egen rekrytering)."""
    holding = _holding_or_redirect()
    if holding is None:
        return redirect(url_for("main.holding"))
    today = clock.today()
    errors, warnings = {}, []

    if request.method == "POST":
        form = request.form
        individual = (form.get("individual_number") or "").strip()
        shared = {
            "event_date": form.get("event_date"),
            "species": form.get("species"),
            "ppn": holding["ppn"],
            "birth_year": form.get("birth_year"),
            "counterparty": holding["ppn"],
        }
        out_entry, out_errors = rules.parse_entry_form({
            **shared, "event_type": "recruitment_out", "count": "1",
            "notes": f"Individnr {individual}" if individual else None,
        })
        in_entry, in_errors = rules.parse_entry_form({
            **shared, "event_type": "recruitment_in", "individual_number": individual,
            "sex": form.get("sex"), "breed": form.get("breed"), "breeding": "1",
            "electronic_tag": form.get("electronic_tag"), "previous_id": form.get("previous_id"),
            "notes": form.get("notes"),
        })
        errors = {**out_errors, **in_errors}
        if not individual:
            errors["individual_number"] = "Enter the animal's new individual number."
        if not form.get("birth_year"):
            errors["birth_year"] = "Enter the birth year."
        if not errors:
            for entry in (out_entry, in_entry):
                entry_errors, entry_warnings = rules.validate_entry(entry, holding, today)
                errors.update(entry_errors)
                warnings += [w for w in entry_warnings if w not in warnings]
        if not errors and _acknowledged(warnings):
            store.insert_entries([out_entry, in_entry])
            flash(f"Animal {holding['ppn']}-{individual} is now recorded individually.", "success")
            return redirect(url_for(".index"))
        values = form
    else:
        values = {
            "event_date": today.isoformat(),
            "species": _default_species(holding),
            "birth_year": today.year if today.month >= 7 else today.year - 1,
            "breed": holding["main_breed"] or "",
        }
    return render_template("journal/recruit.html", values=values, errors=errors, warnings=warnings)


SHEETS = {
    "plus": "Plusblad: födda och inkommande djur",
    "minus": "Minusblad: döda och utgående djur",
    "temp": "Tillfälligt ute",
}


@bp.route("/print")
def print_sheet():
    sheet = request.args.get("sheet", "plus")
    if sheet not in SHEETS:
        abort(404)
    year = request.args.get("year") or None
    species = request.args.get("species") or None
    entries = store.list_entries(year=year, species=species)
    if sheet == "temp":
        rows = [e for e in entries if EVENT_TYPES[e["event_type"]].temporary]
    else:
        direction = "in" if sheet == "plus" else "out"
        rows = [
            e for e in entries
            if e["direction"] == direction and not EVENT_TYPES[e["event_type"]].temporary
        ]
    counts = []
    if sheet == "plus":
        counts = [
            c for c in store.list_counts()
            if (not year or str(c["year"]) == year) and (not species or c["species"] == species)
        ]
    return render_template(
        "journal/print.html",
        sheet=sheet, title=SHEETS[sheet], rows=rows, counts=counts,
        year=year, species=species, years=store.available_years(),
    )
