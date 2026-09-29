from flask import Blueprint, abort, render_template, request

from .. import store

bp = Blueprint("animals", __name__, url_prefix="/animals")

STATUSES = {"present": "On the holding", "away": "Temporarily away", "gone": "Left / dead", "all": "All"}


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
    history = store.animal_history(species, ppn, individual_number)
    if not history:
        abort(404)
    animal = store.individual_animals().get((species, ppn, individual_number))
    return render_template(
        "animals/detail.html", history=history, animal=animal, statuses=STATUSES,
        species=species, ppn=ppn, individual_number=individual_number,
    )
