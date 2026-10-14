from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge

from .. import photos, rules, store
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
        "animals/list.html", animals=animals, status=status, species=species, statuses=STATUSES,
        photos=store.first_photos(),
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
        photos=store.list_photos(species, ppn, individual_number),
        max_photos=photos.MAX_PHOTOS,
    )


def _animal_exists(species, ppn, individual_number):
    return (
        (species, ppn, individual_number) in store.individual_animals()
        or bool(store.animal_history(species, ppn, individual_number))
    )


@bp.route("/<species>/<ppn>/<individual_number>/photos", methods=["POST"])
def upload_photos(species, ppn, individual_number):
    if not _animal_exists(species, ppn, individual_number):
        abort(404)
    back = redirect(url_for(".detail", species=species, ppn=ppn, individual_number=individual_number))
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if not files:
        flash("Välj en eller två bilder att ladda upp.", "error")
        return back
    existing = len(store.list_photos(species, ppn, individual_number))
    room = photos.MAX_PHOTOS - existing
    if len(files) > room:
        flash(
            f"Ett djur kan ha högst {photos.MAX_PHOTOS} bilder. "
            + (f"Det finns plats för {room} till." if room else "Ta bort en bild först."),
            "error",
        )
        return back
    saved = 0
    for file in files:
        try:
            filename = photos.save(file)
        except photos.PhotoError as exc:
            flash(str(exc), "error")
            continue
        store.add_photo(species, ppn, individual_number, filename, file.filename)
        saved += 1
    if saved:
        flash(f"{saved} bild(er) uppladdade.", "success")
    return back


@bp.route("/photos/<int:photo_id>")
def photo(photo_id):
    row = store.get_photo(photo_id) or abort(404)
    return send_from_directory(photos.folder(), row["filename"], max_age=31536000)


@bp.route("/photos/<int:photo_id>/thumb")
def photo_thumb(photo_id):
    row = store.get_photo(photo_id) or abort(404)
    return send_from_directory(photos.folder(), photos.thumb_name(row["filename"]), max_age=31536000)


@bp.route("/photos/<int:photo_id>/delete", methods=["POST"])
def delete_photo(photo_id):
    row = store.get_photo(photo_id) or abort(404)
    store.delete_photo(photo_id)
    photos.delete_files(row["filename"])
    flash("Bilden har tagits bort.", "success")
    return redirect(url_for(
        ".detail", species=row["species"], ppn=row["ppn"], individual_number=row["individual_number"],
    ))


@bp.app_errorhandler(RequestEntityTooLarge)
def too_large(exc):
    limit = request.max_content_length // (1024 * 1024) if request.max_content_length else 0
    flash(f"Uppladdningen är för stor (högst {limit} MB).", "error")
    return redirect(request.referrer or url_for(".index"))


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
