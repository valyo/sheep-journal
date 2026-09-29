import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from sheep_journal import create_app

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=ZoneInfo("Europe/Stockholm"))


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.sqlite"),
        "FIXED_NOW": NOW,
    })


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def holding(client):
    client.post("/holding", data={
        "ppn": "SE 12345",
        "keeper_name": "Test Farm",
        "species": "sheep",
        "main_breed": "Gotlandsfår",
    })
    return "12345"


def add(client, **fields):
    """Post a journal entry, acknowledging any warnings."""
    data = {"event_date": "2026-09-29", "species": "sheep", **fields}
    response = client.post("/journal/new", data=data)
    if response.status_code == 200 and b'name="ack"' in response.data:
        # Re-post with the warnings acknowledged, as the "Save anyway" button does.
        acks = re.findall(rb'name="ack" value="([^"]*)"', response.data)
        data["ack"] = [html.unescape(a.decode()) for a in acks]
        response = client.post("/journal/new", data=data)
    return response
