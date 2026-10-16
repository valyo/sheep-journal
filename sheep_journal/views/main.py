import csv
import io

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from .. import clock, rules, store
from ..constants import holding_species
from ..filters import event_label_sv

bp = Blueprint("main", __name__)


@bp.route("/")
def dashboard():
    holding = store.get_holding()
    stock = store.balance()
    animals = store.individual_animals().values()

    species_list = holding_species(holding) + [s for s in stock if s not in holding_species(holding)]
    summary = []
    for species in species_list:
        counts = stock.get(species, {"present": 0, "away": 0})
        individuals = sum(1 for a in animals if a["species"] == species and a["status"] == "present")
        summary.append({
            "species": species,
            "present": counts["present"],
            "away": counts["away"],
            "individuals": individuals,
            "groups": counts["present"] - individuals,
        })

    return render_template(
        "dashboard.html",
        summary=summary,
        warnings=rules.compliance_warnings(holding, clock.today()),
        recent=store.list_entries(include_voided=False, newest_first=True, limit=8),
    )


@bp.route("/holding", methods=["GET", "POST"])
def holding():
    errors = {}
    if request.method == "POST":
        data, errors = rules.parse_holding_form(request.form)
        if not errors:
            store.save_holding(data)
            flash("Uppgifterna om anläggningen har sparats.", "success")
            return redirect(url_for(".dashboard"))
        values = request.form
    else:
        current = store.get_holding()
        values = dict(current) if current else {"species": "sheep"}
    return render_template("holding.html", values=values, errors=errors)


@bp.route("/counts", methods=["GET", "POST"])
def counts():
    today = clock.today()
    errors = {}
    if request.method == "POST":
        data, errors = rules.parse_count_form(request.form)
        if not errors:
            store.save_count(data)
            flash(f"Decemberräkningen {data['year']} har sparats.", "success")
            return redirect(url_for(".counts"))
        values = request.form
    else:
        default_year = today.year if today.month == 12 else today.year - 1
        year = request.args.get("year", type=int) or default_year
        species = request.args.get("species") or holding_species(store.get_holding())[0]
        existing = store.get_count(year, species)
        if existing:
            values = dict(existing)
        else:
            values = {
                "year": year,
                "species": species,
                "count_date": today.isoformat() if today.month == 12 and year == today.year else "",
            }

    rows = []
    for count in store.list_counts():
        journal = store.balance(as_of=count["count_date"]).get(count["species"], {"present": 0, "away": 0})
        rows.append((count, journal["present"] + journal["away"]))
    return render_template("counts.html", values=values, errors=errors, rows=rows)


EXPORT_COLUMNS = [
    ("id", "id"),
    ("direction", "plus/minus"),
    ("event_type", "event_type"),
    (None, "händelse"),
    ("event_date", "datum"),
    ("species", "djurslag"),
    ("ppn", "ppn"),
    ("individual_number", "individnummer"),
    ("count", "antal"),
    ("sex", "kön"),
    ("birth_year", "födelseår"),
    ("breeding", "livdjur"),
    ("counterparty", "leverantör/mottagare"),
    ("driver_name", "chaufför"),
    ("vehicle_reg", "fordon regnr"),
    ("cause_of_death", "dödsorsak"),
    ("breed", "ras"),
    ("genotype", "genotyp"),
    ("electronic_tag", "elektroniskt märke"),
    ("previous_id", "tidigare id"),
    ("notes", "övrigt"),
    ("created_at", "registrerad"),
    ("updated_at", "ändrad"),
    ("voided_at", "makulerad"),
    ("void_reason", "makuleringsorsak"),
]


@bp.route("/export.csv")
def export_csv():
    out = io.StringIO()
    # Semicolons and a BOM so Excel with Swedish settings opens it correctly.
    out.write("﻿")
    writer = csv.writer(out, delimiter=";")
    writer.writerow([header for _, header in EXPORT_COLUMNS])
    for entry in store.list_entries():
        row = []
        for column, _ in EXPORT_COLUMNS:
            if column is None:
                row.append(event_label_sv(entry["event_type"]))
            elif column == "direction":
                row.append("+" if entry["direction"] == "in" else "-")
            else:
                row.append("" if entry[column] is None else entry[column])
        writer.writerow(row)
    filename = f"stalljournal_{clock.today().isoformat()}.csv"
    return Response(
        out.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
