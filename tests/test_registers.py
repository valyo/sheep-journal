import sqlite3

from conftest import add

from sheep_journal import create_app, store


def animals(app):
    with app.app_context():
        return store.individual_animals()


def present(app):
    with app.app_context():
        return store.balance().get("sheep", {"present": 0})["present"]


def tag(client, rows, **shared):
    data = {"event_date": "2026-09-29", "species": "sheep", "birth_year": "2026",
            "rows": str(len(rows)), **shared}
    for i, row in enumerate(rows):
        for key, value in row.items():
            data[f"{key}_{i}"] = value
    return client.post("/journal/tag", data=data)


def test_tagging_is_balance_neutral(app, client, holding):
    add(client, event_type="birth", ppn="12345", count="3", birth_year="2026")
    response = tag(client, [
        {"number": "00001", "sex": "F", "name": "Bea"},
        {"number": "00002", "sex": "M"},
    ])
    assert response.status_code == 302
    assert present(app) == 3
    bea = animals(app)[("sheep", "12345", "00001")]
    assert bea["status"] == "present" and bea["name"] == "Bea" and bea["tag_year"] == 2026


def test_tagging_more_than_born_warns(client, holding):
    add(client, event_type="birth", ppn="12345", count="1", birth_year="2026")
    response = tag(client, [{"number": "00001"}, {"number": "00002"}])
    assert b"more is too many" in response.data


def test_tag_stock_and_double_tag_rule(app, client, holding):
    client.post("/tags", data={"first": "00013", "last": "00015", "tag_type": "single",
                               "species": "sheep", "order_ref": "2023/1"})
    with app.app_context():
        assert len(store.available_tags("sheep", "single")) == 3
    add(client, event_type="birth", ppn="12345", count="2", birth_year="2026")

    response = tag(client, [{"number": "00099"}])
    assert b"not in your ear tag stock" in response.data

    response = tag(client, [{"number": "00013", "breeding": "1"}])
    assert b"single ear tag" in response.data

    tag(client, [{"number": "00013"}], ack=[])  # no warnings for a slaughter lamb
    with app.app_context():
        assert [t["individual_number"] for t in store.available_tags("sheep")] == ["00014", "00015"]
        assert store.animal_by_key("sheep", "12345", "00013")["tag_type"] == "single"


def test_birth_split_cannot_exceed_count(client, holding):
    response = add(client, event_type="birth", ppn="12345", count="2", birth_year="2026",
                   males="2", females="1")
    assert b"more than the number born" in response.data


def test_birth_with_mother(app, client, holding):
    add(client, event_type="purchase", ppn="5554", individual_number="00012", breeding="1",
        sex="F", counterparty="5554", event_date="2026-09-01")
    add(client, event_type="birth", ppn="12345", count="2", birth_year="2026",
        mother_id="SE5554-2020-00012", males="1", females="1")
    with app.app_context():
        birth = store.list_entries(event_type="birth")[0]
    assert birth["mother_id"] == "5554-00012" and birth["males"] == 1


def test_placeholder_vehicle_is_flagged(app, client, holding):
    add(client, event_type="birth", ppn="12345", count="2", birth_year="2026")
    response = client.post("/journal/new", data={
        "event_type": "slaughter", "event_date": "2026-09-29", "species": "sheep", "ppn": "12345",
        "count": "1", "counterparty": "099", "driver_name": "V. G.", "vehicle_reg": "XXX 000"})
    assert b"look like a registration number" in response.data


def test_contacts_show_in_journal(client, holding):
    client.post("/contacts/new", data={"ppn": "SE 234567", "name": "Grannby", "kind": "farm"})
    add(client, event_type="purchase", ppn="234567", count="2", counterparty="234567")
    assert b"234567 (Grannby)" in client.get("/journal/").data
    response = client.post("/contacts/new", data={"ppn": "234567", "name": "Dup", "kind": "farm"})
    assert b"already registered" in response.data


def test_animal_details_and_number_lock(app, client, holding):
    response = client.post("/animals/new", data={
        "species": "sheep", "ppn": "34567", "individual_number": "19011", "name": "Stina",
        "sex": "F", "birth_date": "2019-03-16", "tag_type": "double"})
    assert response.status_code == 302
    stina = animals(app)[("sheep", "34567", "19011")]
    assert stina["status"] == "unrecorded" and stina["birth_year"] == 2019
    response = client.post(f"/animals/{stina['id']}/edit", data={
        "species": "sheep", "ppn": "34567", "individual_number": "99999", "name": "Stina"})
    assert b"can&#39;t be changed here" in response.data
    assert b"have no journal rows" in client.get("/").data


def test_herd_log(app, client, holding):
    add(client, event_type="purchase", ppn="5554", individual_number="00012", breeding="1",
        counterparty="5554")
    response = client.post("/log/new", data={
        "event_date": "2026-09-29", "kind": "treatment", "species": "sheep",
        "animal": ["5554|00012"]})
    assert b"Record which medicine" in response.data
    client.post("/log/new", data={
        "event_date": "2026-09-29", "kind": "treatment", "species": "sheep",
        "animal": ["5554|00012"], "product": "Test-vet", "withdrawal_until": "2026-10-20"})
    client.post("/log/new", data={
        "event_date": "2026-09-29", "kind": "shearing", "species": "sheep", "subject": "all ewes"})
    with app.app_context():
        events = store.list_herd_events()
    assert len(events) == 2
    treatment = next(e for e in events if e["kind"] == "treatment")
    client.post(f"/log/{treatment['id']}/delete")
    with app.app_context():
        assert len(store.list_herd_events()) == 2  # medicine records are kept
    assert b"Test-vet" in client.get("/animals/sheep/5554/00012").data


def test_new_pages_render(client, holding):
    for url in ["/journal/tag", "/tags", "/log", "/log/new", "/contacts", "/contacts/new",
                "/animals/new", "/animals/?status=unrecorded"]:
        assert client.get(url).status_code == 200, url


OLD_SCHEMA = """
CREATE TABLE holding (id INTEGER PRIMARY KEY CHECK (id = 1), ppn TEXT NOT NULL,
    keeper_name TEXT NOT NULL, address TEXT, species TEXT NOT NULL DEFAULT 'sheep',
    category TEXT, main_breed TEXT, journal_start TEXT);
CREATE TABLE entry (id INTEGER PRIMARY KEY AUTOINCREMENT, direction TEXT NOT NULL,
    event_type TEXT NOT NULL, event_date TEXT NOT NULL, species TEXT NOT NULL DEFAULT 'sheep',
    ppn TEXT NOT NULL, individual_number TEXT, count INTEGER NOT NULL DEFAULT 1, sex TEXT,
    birth_year INTEGER, breeding INTEGER NOT NULL DEFAULT 0, counterparty TEXT, driver_name TEXT,
    vehicle_reg TEXT, cause_of_death TEXT, breed TEXT, genotype TEXT,
    electronic_tag INTEGER NOT NULL DEFAULT 0, previous_id TEXT, notes TEXT,
    created_at TEXT NOT NULL, updated_at TEXT, voided_at TEXT, void_reason TEXT);
CREATE TABLE annual_count (year INTEGER NOT NULL, species TEXT NOT NULL, count_date TEXT NOT NULL,
    total INTEGER NOT NULL, ewes INTEGER, rams INTEGER, lambs INTEGER, reported_on TEXT,
    notes TEXT, PRIMARY KEY (year, species));
INSERT INTO holding (id, ppn, keeper_name) VALUES (1, '12345', 'Old Farm');
INSERT INTO entry (direction, event_type, event_date, ppn, count, created_at)
    VALUES ('in', 'birth', '2026-04-01', '12345', 4, '2026-04-01T10:00:00');
"""


def test_migration_keeps_data_and_matches_fresh_schema(tmp_path):
    old = tmp_path / "old.sqlite"
    con = sqlite3.connect(old)
    con.executescript(OLD_SCHEMA)
    con.close()

    create_app({"TESTING": True, "DATABASE": str(old)})
    fresh = tmp_path / "fresh.sqlite"
    create_app({"TESTING": True, "DATABASE": str(fresh)})

    def columns(path):
        con = sqlite3.connect(path)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        result = {t: sorted(r[1] for r in con.execute(f"PRAGMA table_info({t})")) for t in tables}
        version = con.execute("PRAGMA user_version").fetchone()[0]
        con.close()
        return result, version

    assert columns(old) == columns(fresh)
    con = sqlite3.connect(old)
    assert con.execute("SELECT count FROM entry").fetchone()[0] == 4
    con.close()
