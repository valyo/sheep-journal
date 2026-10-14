from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import rules, store
from ..constants import holding_species

bp = Blueprint("animals", __name__, url_prefix="/animals")

STATUSES = {
    "present": "På anläggningen",
    "away": "Tillfälligt ute",
    "gone": "Utgått / döda",
    "unrecorded": "Saknas i journalen",
    "all": "Alla",
}


@bp.route("/")
def index():
    status = request.args.get("status", "present")
    if status not in STATUSES:
        status = "present"
    species = request.args.get("species") or None
    animals = [
        a for a in store.individual_animals().values()
        if (status == "all" or a["status"] == status) and (not species or a["species"] == species)
    ]
    animals.sort(key=lambda a: (a["species"], a["ppn"], a["individual_number"]))
    return render_template(
        "animals/list.html", animals=animals, status=status, species=species, statuses=STATUSES
    )


@bp.route("/<species>/<ppn>/<individual_number>")
def detail(species, ppn, individual_number):
    animal = store.individual_animals().get((species, ppn, individual_number))
    history = store.animal_history(species, ppn, individual_number)
    if animal is None and not history:
        abort(404)
    return render_template(
        "animals/detail.html",
        animal=animal, history=history, statuses=STATUSES,
        species=species, ppn=ppn, individual_number=individual_number,
        herd_events=store.list_herd_events(species=species, ppn=ppn, individual_number=individual_number),
        children=store.offspring(f"{ppn}-{individual_number}"),
    )


def _form(animal_id=None):
    errors = {}
    if request.method == "POST":
        data, errors = rules.parse_animal_form(request.form)
        if not errors:
            existing = store.animal_by_key(data["species"], data["ppn"], data["individual_number"])
            if existing and existing["id"] != animal_id:
                errors["individual_number"] = "Ett annat djur i registret har redan det här numret."
        if not errors:
            if animal_id is not None:
                current = store.get_animal(animal_id)
                if (current["species"], current["ppn"], current["individual_number"]) != (
                        data["species"], data["ppn"], data["individual_number"]):
                    errors["individual_number"] = (
                        "Öronmärkesnumret kan inte ändras här: det kopplar djuret till dess "
                        "rader i journalen. För in ommärkning i journalen i stället."
                    )
        if not errors:
            store.save_animal(data)
            flash("Djuruppgifterna har sparats.", "success")
            return redirect(url_for(
                ".detail", species=data["species"], ppn=data["ppn"],
                individual_number=data["individual_number"],
            ))
        values = request.form
    elif animal_id is not None:
        values = dict(store.get_animal(animal_id))
    else:
        holding = store.get_holding()
        values = {
            "species": request.args.get("species") or holding_species(holding)[0],
            "ppn": request.args.get("ppn") or (holding["ppn"] if holding else ""),
            "individual_number": request.args.get("individual_number", ""),
        }
        # Pre-fill from the journal if the animal is already recorded there.
        key = (values["species"], values["ppn"], values["individual_number"])
        known = store.individual_animals().get(key)
        if known:
            for field in ("sex", "birth_year", "breed", "mother_id"):
                if known.get(field):
                    values[field] = known[field]
    return render_template(
        "animals/form.html", values=values, errors=errors, animal_id=animal_id,
        mothers=[a for a in store.individual_animals().values() if a["sex"] != "M"],
    )


@bp.route("/new", methods=["GET", "POST"])
def new():
    return _form()


@bp.route("/<int:animal_id>/edit", methods=["GET", "POST"])
def edit(animal_id):
    if store.get_animal(animal_id) is None:
        abort(404)
    return _form(animal_id)
