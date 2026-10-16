import io
import os

from conftest import add
from PIL import Image

from sheep_journal import store

URL = "/animals/sheep/5554/00012"


def image_file(name="ewe.png", size=(2400, 1200), fmt="PNG"):
    data = io.BytesIO()
    Image.new("RGB", size, (120, 90, 60)).save(data, fmt)
    data.seek(0)
    return (data, name)


def photos(app):
    with app.app_context():
        return store.list_photos("sheep", "5554", "00012")


def upload(client, *files):
    return client.post(f"{URL}/photos", data={"photos": list(files)},
                       content_type="multipart/form-data", follow_redirects=True)


def setup_animal(client):
    add(client, event_type="purchase", ppn="5554", individual_number="00012", breeding="1",
        counterparty="5554")


def test_upload_two_photos(app, client, holding):
    setup_animal(client)
    response = upload(client, image_file("a.png"), image_file("b.jpg", fmt="JPEG"))
    assert "2 bild(er) uppladdade".encode() in response.data
    rows = photos(app)
    assert [r["original_name"] for r in rows] == ["a.png", "b.jpg"]

    folder = app.config["UPLOAD_FOLDER"]
    with Image.open(os.path.join(folder, rows[0]["filename"])) as full:
        assert full.format == "JPEG" and max(full.size) == 1600
    thumb = client.get(f"/animals/photos/{rows[0]['id']}/thumb")
    assert thumb.status_code == 200 and thumb.mimetype == "image/jpeg"
    with Image.open(io.BytesIO(thumb.data)) as small:
        assert max(small.size) == 400

    # The list shows the first photo as a thumbnail.
    assert f"/animals/photos/{rows[0]['id']}/thumb".encode() in client.get("/animals/").data


def test_at_most_two_photos(app, client, holding):
    setup_animal(client)
    upload(client, image_file("a.png"))
    response = upload(client, image_file("b.png"), image_file("c.png"))
    assert "plats för 1 till".encode() in response.data
    upload(client, image_file("b.png"))
    response = upload(client, image_file("c.png"))
    assert "Ta bort en bild först".encode() in response.data
    assert len(photos(app)) == 2
    # The upload form disappears once the animal has two photos.
    assert b'name="photos"' not in client.get(URL).data


def test_rejects_non_images(app, client, holding):
    setup_animal(client)
    response = upload(client, (io.BytesIO(b"not an image"), "notes.txt"))
    assert "kunde inte läsas som en bild".encode() in response.data
    assert photos(app) == []


def test_delete_photo_removes_files(app, client, holding):
    setup_animal(client)
    upload(client, image_file())
    row = photos(app)[0]
    folder = app.config["UPLOAD_FOLDER"]
    assert os.path.exists(os.path.join(folder, row["filename"]))
    client.post(f"/animals/photos/{row['id']}/delete")
    assert photos(app) == []
    assert os.listdir(folder) == []
    assert client.get(f"/animals/photos/{row['id']}").status_code == 404


def test_unknown_animal(client, holding):
    response = client.post("/animals/sheep/1/2/photos", data={"photos": [image_file()]},
                           content_type="multipart/form-data")
    assert response.status_code == 404


def test_exif_orientation_is_applied_and_metadata_dropped(app, client, holding):
    setup_animal(client)
    data = io.BytesIO()
    image = Image.new("RGB", (300, 100), (10, 20, 30))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise to display
    exif[0x010F] = "PhoneMaker"
    image.save(data, "JPEG", exif=exif.tobytes())
    data.seek(0)
    upload(client, (data, "phone.jpg"))
    row = photos(app)[0]
    with Image.open(os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])) as saved:
        assert saved.size == (100, 300)
        assert not saved.getexif()
