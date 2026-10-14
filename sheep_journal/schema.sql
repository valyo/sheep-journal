-- Full current schema, used for new databases. Existing databases are brought
-- up to date by the scripts in migrations/ (see db.py).

-- The holding (produktionsplats) this journal belongs to. Exactly one row.
CREATE TABLE IF NOT EXISTS holding (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),
    ppn                  TEXT NOT NULL,       -- produktionsplatsnummer / anläggningsnummer
    keeper_name          TEXT NOT NULL,       -- djurhållare
    address              TEXT,
    species              TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat', 'both')),
    category             TEXT,                -- kategori, e.g. "Avelsbesättning; Hobby"
    main_breed           TEXT,                -- huvudsaklig ras
    journal_start        TEXT,                -- date the journal was started
    postal_address       TEXT,
    county               TEXT,                -- län
    municipality         TEXT,                -- kommun
    property_designation TEXT,                -- fastighetsbeteckning
    area_ha              REAL,
    housing              TEXT,                -- djuren hålls: inomhus / utomhus / både
    max_capacity         INTEGER,
    registered_from      TEXT,                -- registered with Jordbruksverket from
    phone                TEXT,
    email                TEXT
);

-- Other holdings and businesses animals come from or go to (PPN register).
CREATE TABLE IF NOT EXISTS contact (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ppn     TEXT UNIQUE,                      -- NULL for e.g. a private buyer without a holding
    name    TEXT NOT NULL,                    -- farm or business name
    keeper  TEXT,                             -- person responsible
    kind    TEXT NOT NULL DEFAULT 'farm' CHECK (kind IN ('farm', 'slaughterhouse', 'other')),
    address TEXT,
    phone   TEXT,
    email   TEXT,
    notes   TEXT
);

-- One row in the journal. direction 'in' = plusblad, 'out' = minusblad.
-- A row is either one individual animal (individual_number set, count = 1)
-- or a group of animals identified only by PPN (count >= 1).
CREATE TABLE IF NOT EXISTS entry (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    direction         TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    event_type        TEXT NOT NULL,
    event_date        TEXT NOT NULL,          -- händelsedatum / identifieringsdatum (YYYY-MM-DD)
    species           TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat')),
    ppn               TEXT NOT NULL,          -- PPN from the ear tag, or EU country code
    individual_number TEXT,                   -- individnummer
    count             INTEGER NOT NULL DEFAULT 1 CHECK (count > 0),
    sex               TEXT CHECK (sex IS NULL OR sex IN ('F', 'M')),
    birth_year        INTEGER,
    breeding          INTEGER NOT NULL DEFAULT 0,   -- livdjur: intended to live >= 12 months
    counterparty      TEXT,                   -- leverantör / mottagare (PPN or name and address)
    driver_name       TEXT,                   -- transportör: chaufförens namn
    vehicle_reg       TEXT,                   -- transportör: registreringsnummer
    cause_of_death    TEXT,
    breed             TEXT,
    genotype          TEXT,
    electronic_tag    INTEGER NOT NULL DEFAULT 0,
    previous_id       TEXT,                   -- original ID if the animal was re-tagged
    notes             TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    voided_at         TEXT,                   -- entries are voided (makulerade), never deleted
    void_reason       TEXT,
    mother_id         TEXT,                   -- births and tagging: 'PPN-individnr' of the mother
    males             INTEGER,                -- births: how many of the count are male
    females           INTEGER,
    source            TEXT,                   -- where the row came from, e.g. a spreadsheet import
    CHECK (individual_number IS NULL OR count = 1)
);

CREATE INDEX IF NOT EXISTS entry_date_idx ON entry (event_date, id);
CREATE INDEX IF NOT EXISTS entry_animal_idx ON entry (species, ppn, individual_number);

-- Details about individually identified animals. The journal rows say where the
-- animal is; this table says who it is.
CREATE TABLE IF NOT EXISTS animal (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    species           TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat')),
    ppn               TEXT NOT NULL,
    individual_number TEXT NOT NULL,
    tag_year          INTEGER,                -- year printed on the ear tag
    tag_type          TEXT CHECK (tag_type IS NULL OR tag_type IN ('single', 'double')),
    tag_model         TEXT,                   -- e.g. micro
    tag_colour        TEXT,
    electronic_tag    INTEGER NOT NULL DEFAULT 0,
    name              TEXT,
    sex               TEXT CHECK (sex IS NULL OR sex IN ('F', 'M')),
    birth_date        TEXT,                   -- YYYY-MM-DD, or YYYY-MM if the day is unknown
    birth_year        INTEGER,
    colour            TEXT,
    breed             TEXT,
    markings          TEXT,                   -- kännetecken
    mother_id         TEXT,                   -- 'PPN-individnr' or as written on the tag
    mother_name       TEXT,
    mother_elite_no   TEXT,
    father_id         TEXT,
    father_name       TEXT,
    father_elite_no   TEXT,
    elite_no          TEXT,                   -- elitlamm registration number
    elite_code        TEXT,
    notes             TEXT,
    UNIQUE (species, ppn, individual_number)
);

-- Photos of an animal (at most 2), keyed by ear tag like the journal rows, so
-- they also work for animals that only appear in the journal. The files live in
-- the uploads folder next to the database.
CREATE TABLE IF NOT EXISTS animal_photo (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    species           TEXT NOT NULL CHECK (species IN ('sheep', 'goat')),
    ppn               TEXT NOT NULL,
    individual_number TEXT NOT NULL,
    filename          TEXT NOT NULL UNIQUE,   -- <name>.jpg, thumbnail <name>_thumb.jpg
    original_name     TEXT,
    uploaded_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS animal_photo_animal_idx ON animal_photo (species, ppn, individual_number);

-- Ear tags ordered for the own holding. A tag is used once an animal or a
-- journal row with the own PPN carries its number.
CREATE TABLE IF NOT EXISTS ear_tag (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    species           TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat')),
    individual_number TEXT NOT NULL,
    tag_type          TEXT NOT NULL DEFAULT 'single' CHECK (tag_type IN ('single', 'double')),
    tag_model         TEXT,
    tag_colour        TEXT,
    order_ref         TEXT,                   -- order / journal number from the tag supplier
    lost              INTEGER NOT NULL DEFAULT 0,  -- lost or destroyed before use
    UNIQUE (species, individual_number)
);

-- Husbandry events that are not movements: shearing, treatments, vaccinations ...
CREATE TABLE IF NOT EXISTS herd_event (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date        TEXT NOT NULL,
    kind              TEXT NOT NULL,
    species           TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat')),
    ppn               TEXT,                   -- the animal, if the event concerns one animal
    individual_number TEXT,
    subject           TEXT,                   -- otherwise which animals, e.g. "all ewes"
    description       TEXT,
    product           TEXT,                   -- medicine or vaccine
    dose              TEXT,
    withdrawal_until  TEXT,                   -- karenstid ends
    prescribed_by     TEXT,
    notes             TEXT,
    created_at        TEXT NOT NULL,
    source            TEXT
);

CREATE INDEX IF NOT EXISTS herd_event_animal_idx ON herd_event (species, ppn, individual_number);

-- The yearly December count (får- och geträkning), reported to Jordbruksverket.
CREATE TABLE IF NOT EXISTS annual_count (
    year        INTEGER NOT NULL,
    species     TEXT NOT NULL CHECK (species IN ('sheep', 'goat')),
    count_date  TEXT NOT NULL,
    total       INTEGER NOT NULL CHECK (total >= 0),
    ewes        INTEGER,                      -- tackor / getter
    rams        INTEGER,                      -- baggar / bockar
    lambs       INTEGER,                      -- lamm / killingar
    reported_on TEXT,                         -- date reported to Jordbruksverket
    notes       TEXT,
    PRIMARY KEY (year, species)
);
