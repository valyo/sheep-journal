ALTER TABLE holding ADD COLUMN postal_address TEXT;
ALTER TABLE holding ADD COLUMN county TEXT;
ALTER TABLE holding ADD COLUMN municipality TEXT;
ALTER TABLE holding ADD COLUMN property_designation TEXT;
ALTER TABLE holding ADD COLUMN area_ha REAL;
ALTER TABLE holding ADD COLUMN housing TEXT;
ALTER TABLE holding ADD COLUMN max_capacity INTEGER;
ALTER TABLE holding ADD COLUMN registered_from TEXT;
ALTER TABLE holding ADD COLUMN phone TEXT;
ALTER TABLE holding ADD COLUMN email TEXT;

ALTER TABLE entry ADD COLUMN mother_id TEXT;
ALTER TABLE entry ADD COLUMN males INTEGER;
ALTER TABLE entry ADD COLUMN females INTEGER;
ALTER TABLE entry ADD COLUMN source TEXT;

CREATE TABLE contact (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ppn     TEXT UNIQUE,
    name    TEXT NOT NULL,
    keeper  TEXT,
    kind    TEXT NOT NULL DEFAULT 'farm' CHECK (kind IN ('farm', 'slaughterhouse', 'other')),
    address TEXT,
    phone   TEXT,
    email   TEXT,
    notes   TEXT
);

CREATE TABLE animal (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    species           TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat')),
    ppn               TEXT NOT NULL,
    individual_number TEXT NOT NULL,
    tag_year          INTEGER,
    tag_type          TEXT CHECK (tag_type IS NULL OR tag_type IN ('single', 'double')),
    tag_model         TEXT,
    tag_colour        TEXT,
    electronic_tag    INTEGER NOT NULL DEFAULT 0,
    name              TEXT,
    sex               TEXT CHECK (sex IS NULL OR sex IN ('F', 'M')),
    birth_date        TEXT,
    birth_year        INTEGER,
    colour            TEXT,
    breed             TEXT,
    markings          TEXT,
    mother_id         TEXT,
    mother_name       TEXT,
    mother_elite_no   TEXT,
    father_id         TEXT,
    father_name       TEXT,
    father_elite_no   TEXT,
    elite_no          TEXT,
    elite_code        TEXT,
    notes             TEXT,
    UNIQUE (species, ppn, individual_number)
);

CREATE TABLE ear_tag (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    species           TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat')),
    individual_number TEXT NOT NULL,
    tag_type          TEXT NOT NULL DEFAULT 'single' CHECK (tag_type IN ('single', 'double')),
    tag_model         TEXT,
    tag_colour        TEXT,
    order_ref         TEXT,
    lost              INTEGER NOT NULL DEFAULT 0,
    UNIQUE (species, individual_number)
);

CREATE TABLE herd_event (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date        TEXT NOT NULL,
    kind              TEXT NOT NULL,
    species           TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat')),
    ppn               TEXT,
    individual_number TEXT,
    subject           TEXT,
    description       TEXT,
    product           TEXT,
    dose              TEXT,
    withdrawal_until  TEXT,
    prescribed_by     TEXT,
    notes             TEXT,
    created_at        TEXT NOT NULL,
    source            TEXT
);

CREATE INDEX herd_event_animal_idx ON herd_event (species, ppn, individual_number);
