CREATE TABLE IF NOT EXISTS listings (
    id                INTEGER PRIMARY KEY,
    item_id           TEXT UNIQUE NOT NULL,
    source_url        TEXT,
    marca             TEXT,
    modelo            TEXT,
    version           TEXT,
    trim_level        TEXT,
    anio              INTEGER,
    kilometros        REAL,
    condicion         TEXT,
    vehiculo_edad     INTEGER,
    cilindrada_cc     INTEGER,
    combustible       TEXT,
    transmision       TEXT,
    traccion          TEXT,
    tipo_carroceria   TEXT,
    puertas           INTEGER,
    color             TEXT,
    precio            REAL,
    moneda            TEXT,
    es_concesionario  INTEGER,
    provincia         TEXT,
    km_por_anio       REAL,
    scraped_at        TEXT,
    created_at        TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_listings_marca ON listings(marca);
CREATE INDEX IF NOT EXISTS idx_listings_modelo ON listings(modelo);
CREATE INDEX IF NOT EXISTS idx_listings_anio ON listings(anio);
