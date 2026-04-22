"""Migrate CSV data from ml_scraper/data/ into the SQLite database."""

import argparse
import csv
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "avm.db"
SCHEMA_PATH = DB_DIR / "schema.sql"
DATA_DIR = Path(__file__).resolve().parent.parent / "ml_scraper" / "data"

# Columns that exist in the DB schema (excluding auto-generated ones)
DB_COLUMNS = [
    "item_id", "source_url", "marca", "modelo", "version", "anio",
    "kilometros", "condicion", "vehiculo_edad", "cilindrada_cc",
    "combustible", "transmision", "traccion", "tipo_carroceria",
    "puertas", "color", "precio", "moneda", "es_concesionario",
    "provincia", "km_por_anio", "scraped_at",
]


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Create the database and apply the schema if needed."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    schema_sql = SCHEMA_PATH.read_text()
    conn.executescript(schema_sql)
    return conn


def _coerce(value: str, column: str) -> object:
    """Coerce a CSV string value to the appropriate Python type."""
    if value == "" or value is None:
        return None

    int_cols = {"anio", "vehiculo_edad", "cilindrada_cc", "puertas", "es_concesionario"}
    float_cols = {"kilometros", "precio", "km_por_anio"}

    if column in int_cols:
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
    if column in float_cols:
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return value


def migrate_csv(csv_path: Path, conn: sqlite3.Connection) -> int:
    """Upsert rows from a CSV file into the listings table.

    Returns the number of rows upserted.
    """
    placeholders = ", ".join(["?"] * len(DB_COLUMNS))
    cols = ", ".join(DB_COLUMNS)
    update_cols = ", ".join(
        f"{c} = excluded.{c}" for c in DB_COLUMNS if c != "item_id"
    )
    sql = (
        f"INSERT INTO listings ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(item_id) DO UPDATE SET {update_cols}"
    )

    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            values = [_coerce(row.get(col, ""), col) for col in DB_COLUMNS]
            conn.execute(sql, values)
            count += 1

    conn.commit()
    return count


def find_csv_files(data_dir: Path = DATA_DIR) -> list[Path]:
    """Find all car_*.csv files in the data directory, sorted by name."""
    return sorted(data_dir.glob("car_*.csv"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate CSV data into SQLite DB")
    parser.add_argument(
        "--csv",
        type=Path,
        help="Path to a specific CSV file. If omitted, migrates all car_*.csv in ml_scraper/data/",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Path to SQLite database (default: {DB_PATH})",
    )
    args = parser.parse_args()

    conn = init_db(args.db)
    log.info("Database ready at %s", args.db)

    csv_files = [args.csv] if args.csv else find_csv_files()
    if not csv_files:
        log.warning("No CSV files found in %s", DATA_DIR)
        return

    total = 0
    for csv_path in csv_files:
        n = migrate_csv(csv_path, conn)
        log.info("Upserted %d rows from %s", n, csv_path.name)
        total += n

    row_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    log.info("Total rows in database: %d (upserted %d this run)", row_count, total)
    conn.close()


if __name__ == "__main__":
    main()
