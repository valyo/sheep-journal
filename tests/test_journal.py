from conftest import add

from sheep_journal import store


def balance(app, species="sheep"):
    with app.app_context():
        return store.balance().get(species, {"present": 0, "away": 0})


def entries(app):
    with app.app_context():
        return store.list_entries()


def test_dashboard_asks_for_holding_first(client):
    response = client.get("/")
    assert b"Set up your holding" in response.data


def test_new_entry_requires_holding(client):
    response = client.get("/journal/new")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/holding")


def test_holding_ppn_is_normalised(app, holding):
    with app.app_context():
        assert store.get_holding()["ppn"] == "12345"


def test_birth_updates_balance(app, client, holding):
    response = add(client, event_type="birth", ppn="12345", count="12", birth_year="2026")
    assert response.status_code == 302
    assert balance(app)["present"] == 12


def test_birth_requires_birth_year(client, holding):
    response = add(client, event_type="birth", ppn="12345", count="3")
    assert b"Births must be recorded with the birth year" in response.data


def test_death_requires_cause(client, holding):
    add(client, event_type="purchase", ppn="5554", individual_number="00012",
        breeding="1", counterparty="5554")
    response = add(client, event_type="death", ppn="5554", individual_number="00012")
    assert b"Record the cause of death" in response.data


def test_breeding_animal_must_be_individual(client, holding):
    response = add(client, event_type="purchase", ppn="5554", count="3",
                   breeding="1", counterparty="5554")
    assert b"must be recorded individually" in response.data


def test_movement_requires_counterparty(client, holding):
    response = add(client, event_type="purchase", ppn="5554", count="3")
    assert b"Enter the supplier" in response.data


def test_individual_row_has_count_one(client, holding):
    response = add(client, event_type="purchase", ppn="5554", individual_number="1",
                   count="4", counterparty="5554")
    assert b"on its own row" in response.data


def test_future_date_rejected(client, holding):
    response = add(client, event_type="birth", ppn="12345", count="1",
                   birth_year="2026", event_date="2026-10-01")
    assert b"can&#39;t be in the future" in response.data


def test_warning_must_be_acknowledged(app, client, holding):
    add(client, event_type="birth", ppn="12345", count="5", birth_year="2026")
    data = {"event_type": "slaughter", "event_date": "2026-09-29", "species": "sheep",
            "ppn": "12345", "count": "2", "counterparty": "700001"}
    response = client.post("/journal/new", data=data)
    assert response.status_code == 200
    assert b"driver&#39;s name" in response.data
    assert balance(app)["present"] == 5

    response = add(client, **{k: v for k, v in data.items() if k not in ("event_date", "species")})
    assert response.status_code == 302
    assert balance(app)["present"] == 3


def test_negative_balance_warns(client, holding):
    data = {"event_type": "slaughter", "event_date": "2026-09-29", "species": "sheep",
            "ppn": "12345", "count": "2", "counterparty": "700001",
            "driver_name": "L. Lasso", "vehicle_reg": "qwx123"}
    response = client.post("/journal/new", data=data)
    assert b"makes the balance negative" in response.data


def test_late_entry_is_flagged(app, client, holding):
    add(client, event_type="purchase", ppn="5554", count="2", counterparty="5554",
        event_date="2026-09-20")
    with app.app_context():
        from sheep_journal.rules import entry_flags
        assert entry_flags(store.list_entries()[0]) == ["late"]
    assert b"more than 48 hours" in client.get("/").data


def test_void_removes_entry_from_balance(app, client, holding):
    add(client, event_type="birth", ppn="12345", count="4", birth_year="2026")
    entry_id = entries(app)[0]["id"]
    client.post(f"/journal/{entry_id}/void", data={"reason": "entered twice"})
    assert balance(app)["present"] == 0
    assert entries(app)[0]["void_reason"] == "entered twice"
    # Voided entries stay visible, crossed out.
    assert b"entered twice" in client.get("/journal/").data


def test_edit_entry(app, client, holding):
    add(client, event_type="birth", ppn="12345", count="4", birth_year="2026")
    entry_id = entries(app)[0]["id"]
    response = client.post(f"/journal/{entry_id}/edit", data={
        "event_type": "birth", "event_date": "2026-09-29", "species": "sheep",
        "ppn": "12345", "count": "6", "birth_year": "2026",
    })
    assert response.status_code == 302
    assert balance(app)["present"] == 6
    assert entries(app)[0]["updated_at"]


def test_temporary_stay(app, client, holding):
    add(client, event_type="birth", ppn="12345", count="10", birth_year="2026")
    add(client, event_type="temp_out", ppn="12345", count="4", counterparty="99999")
    assert balance(app) == {"present": 6, "away": 4}
    add(client, event_type="return_home", ppn="12345", count="4", counterparty="99999")
    assert balance(app) == {"present": 10, "away": 0}


def test_recruitment_moves_animal_from_group(app, client, holding):
    add(client, event_type="birth", ppn="12345", count="5", birth_year="2026")
    response = client.post("/journal/recruit", data={
        "event_date": "2026-09-29", "species": "sheep", "individual_number": "00201",
        "birth_year": "2026", "sex": "F",
    })
    assert response.status_code == 302
    rows = entries(app)
    assert [r["event_type"] for r in rows] == ["birth", "recruitment_out", "recruitment_in"]
    assert rows[2]["individual_number"] == "00201" and rows[2]["breeding"] == 1
    assert balance(app)["present"] == 5
    with app.app_context():
        animal = store.individual_animals()[("sheep", "12345", "00201")]
    assert animal["status"] == "present"


def test_borrowed_ram_history(app, client, holding):
    add(client, event_type="loan_in", ppn="5554", individual_number="60010",
        breeding="1", counterparty="5554", breed="Dorset", event_date="2026-09-22")
    add(client, event_type="loan_return", ppn="5554", individual_number="60010",
        counterparty="5554", driver_name="L. Lina", vehicle_reg="ABC321")
    with app.app_context():
        animal = store.individual_animals()[("sheep", "5554", "60010")]
    assert animal["status"] == "gone"
    page = client.get("/animals/sheep/5554/60010")
    assert page.status_code == 200 and b"Dorset" in page.data


def test_december_count_validation(client, holding):
    response = client.post("/counts", data={
        "year": "2025", "species": "sheep", "count_date": "2025-11-30", "total": "8",
    })
    assert b"between 1 and 31 December 2025" in response.data
    response = client.post("/counts", data={
        "year": "2025", "species": "sheep", "count_date": "2025-12-15", "total": "8",
        "ewes": "5", "rams": "0", "lambs": "2",
    })
    assert b"doesn&#39;t match the total" in response.data
    response = client.post("/counts", data={
        "year": "2025", "species": "sheep", "count_date": "2025-12-15", "total": "7",
        "ewes": "5", "rams": "0", "lambs": "2", "reported_on": "2026-01-10",
    })
    assert response.status_code == 302


def test_missing_december_count_warns(client, holding):
    add(client, event_type="birth", ppn="12345", count="3", birth_year="2025",
        event_date="2025-06-01")
    assert b"No December count recorded" in client.get("/").data


def test_csv_export(client, holding):
    add(client, event_type="birth", ppn="12345", count="3", birth_year="2026")
    response = client.get("/export.csv")
    text = response.data.decode("utf-8-sig")
    assert response.mimetype == "text/csv"
    assert text.splitlines()[0].startswith("id;plus/minus;event_type;händelse")
    assert ";Födda;" in text


def test_print_sheets(client, holding):
    add(client, event_type="birth", ppn="12345", count="3", birth_year="2026")
    add(client, event_type="slaughter", ppn="12345", count="1", counterparty="700001",
        driver_name="L. Lasso", vehicle_reg="QWX123")
    plus = client.get("/journal/print?sheet=plus").data
    minus = client.get("/journal/print?sheet=minus").data
    assert b"Leverant" in plus and b"QWX123" not in plus
    assert b"QWX123" in minus and b"Chauff" in minus
    assert client.get("/journal/print?sheet=nope").status_code == 404


def test_all_pages_render(client, holding):
    for url in ["/", "/journal/", "/journal/new?direction=in", "/journal/new?direction=out",
                "/journal/recruit", "/animals/", "/animals/?status=all", "/counts", "/holding"]:
        assert client.get(url).status_code == 200, url


def test_demo_seed(app):
    from sheep_journal.demo import seed

    with app.app_context():
        assert seed() is True
        assert seed() is False
        assert store.balance()["sheep"]["present"] == 6  # 5 ewes + 1 recruited ewe lamb
