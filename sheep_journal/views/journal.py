from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import clock, rules, store
from ..constants import EVENT_TYPES, TAG_TYPES, holding_species

bp = Blueprint("journal", __name__, url_prefix="/journal")

FILTERS = ("direction", "species", "year", "event_type", "q", "flag")


def _holding_or_redirect():
    holding = store.get_holding()
    if holding is None:
        flash("Fyll i anläggningen först: journalen behöver ditt produktionsplatsnummer (PPN).", "warning")
    return holding


def _default_species(holding):
    return holding_species(holding)[0]


def _acknowledged(warnings):
    return set(warnings) <= set(request.form.getlist("ack"))


def _suggestions():
    """Datalist options for the entry forms: known holdings and possible mothers."""
    animals = store.individual_animals().values()
    mothers = sorted(
        (a for a in animals if a["sex"] != "M" and a["status"] in ("present", "away", "gone")),
        key=lambda a: (a["status"] != "present", a["ref"]),
    )
    return {"contacts": store.list_contacts(), "mothers": mothers}


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
            flash(f"Sparat: {EVENT_TYPES[saved['event_type']].label}.", "success")
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
        **_suggestions(),
    )


@bp.route("/<int:entry_id>/edit", methods=["GET", "POST"])
def edit(entry_id):
    entry = store.get_entry(entry_id)
    if entry is None:
        abort(404)
    if entry["voided_at"]:
        flash("Makulerade rader kan inte ändras.", "warning")
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
            flash("Raden har uppdaterats.", "success")
            return redirect(url_for(".index"))
        values = request.form
    else:
        values = dict(entry)
    return render_template(
        "journal/form.html",
        values=values, errors=errors, warnings=warnings, direction=entry["direction"], entry=entry,
        **_suggestions(),
    )


@bp.route("/<int:entry_id>/void", methods=["POST"])
def void(entry_id):
    entry = store.get_entry(entry_id)
    if entry is None:
        abort(404)
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Ange varför raden makuleras.", "error")
        return redirect(url_for(".edit", entry_id=entry_id))
    store.void_entry(entry_id, reason)
    flash("Raden är makulerad. Den finns kvar i journalen, överstruken.", "success")
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
            errors["individual_number"] = "Ange djurets nya individnummer."
        if not form.get("birth_year"):
            errors["birth_year"] = "Ange födelseår."
        if not errors:
            for entry in (out_entry, in_entry):
                entry_errors, entry_warnings = rules.validate_entry(entry, holding, today)
                errors.update(entry_errors)
                warnings += [w for w in entry_warnings if w not in warnings]
        if not errors and _acknowledged(warnings):
            store.insert_entries([out_entry, in_entry])
            flash(f"Djur {holding['ppn']}-{individual} är nu individregistrerat.", "success")
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


TAG_ROWS = 6


@bp.route("/tag", methods=["GET", "POST"])
def tag_lambs():
    """Ear-tag lambs or kids whose birth is already recorded (identifiering).

    Each lamb gets a tagging row in the journal and an entry in the animal
    register. Tagging rows don't change the balance: the lambs were counted
    when the birth was recorded.
    """
    holding = _holding_or_redirect()
    if holding is None:
        return redirect(url_for("main.holding"))
    today = clock.today()
    rows = min(max(request.values.get("rows", TAG_ROWS, type=int), 1), 30)
    errors, warnings = {}, []

    if request.method == "POST":
        form = request.form
        entries, animals, numbers = [], [], []
        for i in range(rows):
            number = (form.get(f"number_{i}") or "").strip()
            if not number:
                continue
            if number in numbers:
                errors[f"number_{i}"] = f"{number} är angivet två gånger."
                continue
            numbers.append(number)
            entry, entry_errors = rules.parse_entry_form({
                "event_type": "tagging",
                "event_date": form.get("event_date"),
                "species": form.get("species"),
                "ppn": holding["ppn"],
                "individual_number": number,
                "sex": form.get(f"sex_{i}"),
                "birth_year": form.get("birth_year"),
                "breeding": form.get(f"breeding_{i}"),
                "mother_id": form.get(f"mother_{i}") or form.get("mother_id"),
                "breed": form.get("breed"),
            })
            errors.update({f"{k}_{i}" if k in ("sex", "mother_id") else k: v
                           for k, v in entry_errors.items()})
            tag_type = form.get(f"tag_type_{i}") or None
            if tag_type not in TAG_TYPES:
                tag_type = None
            entries.append((i, entry, tag_type))

        if not entries and not errors:
            errors["number_0"] = "Ange individnummer för minst ett djur."

        if not errors and entries[0][1]["birth_year"]:
            born, tagged = store.births_and_tagged(
                entries[0][1]["species"], holding["ppn"], entries[0][1]["birth_year"])
            if tagged + len(entries) > born:
                warnings.append(
                    f"Journalen har {born} födda {entries[0][1]['birth_year']} och "
                    f"{tagged} redan märkta, så {len(entries)} till är för många. "
                    "För in de saknade födslarna först."
                )
        if not errors:
            has_stock = bool(store.list_tags())
            for i, entry, tag_type in entries:
                entry_errors, entry_warnings = rules.validate_entry(entry, holding, today)
                for key, message in entry_errors.items():
                    errors[f"number_{i}" if key == "individual_number" else key] = message
                warnings += [w for w in entry_warnings if w not in warnings]
                label = f"{holding['ppn']}-{entry['individual_number']}"
                stock_tag = store.get_tag(entry["species"], entry["individual_number"])
                if has_stock and stock_tag is None:
                    warnings.append(f"Märke {label} finns inte i ditt märkeslager.")
                elif stock_tag and tag_type and stock_tag["tag_type"] != tag_type:
                    warnings.append(
                        f"Märke {label} är registrerat som {TAG_TYPES[stock_tag['tag_type']].lower()} i lagret."
                    )
                effective_type = tag_type or (stock_tag["tag_type"] if stock_tag else None)
                if entry["breeding"] and effective_type == "single":
                    warnings.append(rules.double_tag_warning(label))
                animals.append({
                    "species": entry["species"],
                    "ppn": holding["ppn"],
                    "individual_number": entry["individual_number"],
                    "tag_year": date_year(entry["event_date"]),
                    "tag_type": effective_type,
                    "tag_model": stock_tag["tag_model"] if stock_tag else None,
                    "tag_colour": stock_tag["tag_colour"] if stock_tag else None,
                    "name": (form.get(f"name_{i}") or "").strip() or None,
                    "sex": entry["sex"],
                    "birth_year": entry["birth_year"],
                    "breed": entry["breed"],
                    "mother_id": entry["mother_id"],
                })

        if not errors and _acknowledged(warnings):
            for _, entry, _ in entries:
                store.insert_entry(entry, commit=False)
            for animal in animals:
                store.merge_animal(animal, commit=False)
            store.commit()
            flash(f"{len(entries)} djur öronmärkta och tillagda i djurregistret.", "success")
            return redirect(url_for("animals.index"))
        values = form
    else:
        values = {
            "event_date": today.isoformat(),
            "species": _default_species(holding),
            "birth_year": today.year if today.month >= 3 else today.year - 1,
            "mother_id": request.args.get("mother_id", ""),
            "breed": holding["main_breed"] or "",
        }

    species = values.get("species") or _default_species(holding)
    return render_template(
        "journal/tag.html",
        values=values, errors=errors, warnings=warnings, rows=rows,
        free_single=store.available_tags(species, "single"),
        free_double=store.available_tags(species, "double"),
        **_suggestions(),
    )


def date_year(iso_date):
    return int(iso_date[:4]) if iso_date else None


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
