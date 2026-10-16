"""Contacts (PPN register), ear tag stock and the herd log."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import clock, rules, store
from ..constants import HERD_EVENT_KINDS, MEDICINE_KINDS, holding_species

bp = Blueprint("registers", __name__)


# --- contacts ------------------------------------------------------------------


@bp.route("/contacts")
def contacts():
    return render_template("registers/contacts.html", contacts=store.list_contacts())


@bp.route("/contacts/new", methods=["GET", "POST"])
@bp.route("/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
def contact_form(contact_id=None):
    current = store.get_contact(contact_id) if contact_id else None
    if contact_id and current is None:
        abort(404)
    errors = {}
    if request.method == "POST":
        data, errors = rules.parse_contact_form(request.form)
        if not errors and data["ppn"]:
            other = store.contact_by_ppn(data["ppn"])
            if other and other["id"] != contact_id:
                errors["ppn"] = f"{data['ppn']} är redan registrerat som {other['name']}."
        if not errors:
            store.save_contact(data, contact_id)
            flash(f"{data['name']} har sparats.", "success")
            return redirect(url_for(".contacts"))
        values = request.form
    else:
        values = dict(current) if current else {"kind": "farm", "ppn": request.args.get("ppn", "")}
    return render_template("registers/contact_form.html", values=values, errors=errors, contact=current)


# --- ear tags ------------------------------------------------------------------


@bp.route("/tags", methods=["GET", "POST"])
def tags():
    holding = store.get_holding()
    species = request.args.get("species") or holding_species(holding)[0]
    errors = {}
    if request.method == "POST":
        new_tags, errors = rules.parse_tag_range_form(request.form)
        if not errors:
            added = store.add_tags(new_tags)
            skipped = len(new_tags) - added
            message = f"{added} öronmärken tillagda i lagret."
            if skipped:
                message += f" {skipped} nummer fanns redan i lagret."
            flash(message, "success")
            return redirect(url_for(".tags", species=request.form.get("species")))
        values = request.form
    else:
        values = {"species": species, "tag_type": "single"}

    all_tags = store.list_tags(species)
    animals = store.individual_animals()
    own_ppn = holding["ppn"] if holding else ""
    rows = [(t, animals.get((t["species"], own_ppn, t["individual_number"]))) for t in all_tags]
    summary = {
        tag_type: sum(1 for t in all_tags if t["tag_type"] == tag_type and not t["used"] and not t["lost"])
        for tag_type in ("single", "double")
    }
    return render_template(
        "registers/tags.html", rows=rows, summary=summary, values=values, errors=errors,
        species=species,
    )


@bp.route("/tags/<int:tag_id>/lost", methods=["POST"])
def tag_lost(tag_id):
    store.set_tag_lost(tag_id, request.form.get("lost") == "1")
    return redirect(request.referrer or url_for(".tags"))


# --- herd log ------------------------------------------------------------------


@bp.route("/log")
def herd_log():
    kind = request.args.get("kind") or None
    year = request.args.get("year") or None
    events = store.list_herd_events(kind=kind, year=year)
    animals = store.individual_animals()
    return render_template(
        "registers/log.html", events=events, kind=kind, year=year, animals=animals,
    )


@bp.route("/log/new", methods=["GET", "POST"])
def herd_log_new():
    holding = store.get_holding()
    if holding is None:
        flash("Fyll i anläggningen först.", "warning")
        return redirect(url_for("main.holding"))
    errors = {}
    present = sorted(
        (a for a in store.individual_animals().values() if a["status"] in ("present", "away")),
        key=lambda a: (a["species"], a["ref"]),
    )
    if request.method == "POST":
        keys = []
        for value in request.form.getlist("animal"):
            ppn, _, number = value.partition("|")
            if ppn and number:
                keys.append((ppn, number))
        events, errors = rules.parse_herd_event_form(request.form, keys)
        if not errors:
            store.insert_herd_events(events)
            flash(f"{HERD_EVENT_KINDS[events[0]['kind']]} registrerad.", "success")
            return redirect(url_for(".herd_log"))
        values = request.form
        selected = set(request.form.getlist("animal"))
    else:
        values = {
            "event_date": clock.today().isoformat(),
            "kind": request.args.get("kind", ""),
            "species": holding_species(holding)[0],
        }
        selected = set(request.args.getlist("animal"))
    return render_template(
        "registers/log_form.html", values=values, errors=errors, present=present, selected=selected,
    )


@bp.route("/log/<int:event_id>/delete", methods=["POST"])
def herd_log_delete(event_id):
    event = next((e for e in store.list_herd_events() if e["id"] == event_id), None)
    if event is None:
        abort(404)
    if event["kind"] in MEDICINE_KINDS:
        flash("Läkemedelsanteckningar ska sparas i 5 år och kan inte tas bort.", "error")
    else:
        store.delete_herd_event(event_id)
        flash("Anteckningen har tagits bort.", "success")
    return redirect(url_for(".herd_log"))
