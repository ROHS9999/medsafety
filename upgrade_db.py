"""Run after updating models.py. Adds any new columns to your existing database,
so you keep your data. Safe to run more than once."""
from sqlalchemy import text

from database import engine

NEW_COLUMNS = [
    ("prescriptions", "list_confirmed", "BOOLEAN NOT NULL DEFAULT 0"),
    ("prescriptions", "reading_note", "VARCHAR"),
]

with engine.begin() as connection:
    for table, column, definition in NEW_COLUMNS:
        existing = [row[1] for row in connection.execute(text(f"PRAGMA table_info({table})"))]
        if column in existing:
            print(f"{table}.{column}: already there")
        else:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
            print(f"{table}.{column}: added")
print("Done. Your data is kept.")
