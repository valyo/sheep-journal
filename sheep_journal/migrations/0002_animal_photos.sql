CREATE TABLE animal_photo (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    species           TEXT NOT NULL CHECK (species IN ('sheep', 'goat')),
    ppn               TEXT NOT NULL,
    individual_number TEXT NOT NULL,
    filename          TEXT NOT NULL UNIQUE,
    original_name     TEXT,
    uploaded_at       TEXT NOT NULL
);

CREATE INDEX animal_photo_animal_idx ON animal_photo (species, ppn, individual_number);
