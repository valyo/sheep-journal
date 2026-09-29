-- The holding (produktionsplats) this journal belongs to. Exactly one row.
CREATE TABLE IF NOT EXISTS holding (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    ppn           TEXT NOT NULL,              -- produktionsplatsnummer
    keeper_name   TEXT NOT NULL,              -- djurhållare
    address       TEXT,
    species       TEXT NOT NULL DEFAULT 'sheep' CHECK (species IN ('sheep', 'goat', 'both')),
    category      TEXT,                       -- kött, mjölk, ull, hobby ...
    main_breed    TEXT,                       -- huvudsaklig ras
    journal_start TEXT                        -- date the journal was started
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
    CHECK (individual_number IS NULL OR count = 1)
);

CREATE INDEX IF NOT EXISTS entry_date_idx ON entry (event_date, id);
CREATE INDEX IF NOT EXISTS entry_animal_idx ON entry (species, ppn, individual_number);

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
