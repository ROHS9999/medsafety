"""Loads the DDInter interaction pairs into the app's database. Run once:
    python load_interactions.py
or with another folder:
    python load_interactions.py "Dataset/processed/DDIndex"
Safe to run again: it replaces the old pairs."""
import csv
import sys
from collections import Counter
from pathlib import Path

import models
from database import Base, SessionLocal, engine
from safety import SEVERITY_RANK

DEFAULT_FOLDER = Path("Dataset") / "processed" / "DDIndex"


def load_folder(db, folder) -> dict:
    files = sorted(Path(folder).glob("DDIndex_*.csv"))
    if not files:
        raise FileNotFoundError(f"No DDIndex_*.csv files found in {folder}")

    pairs = {}
    for file in files:
        with open(file, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                drug_a = (row.get("Drug_A") or "").strip().lower()
                drug_b = (row.get("Drug_B") or "").strip().lower()
                level = (row.get("Level") or "").strip().title()
                if level not in SEVERITY_RANK:
                    level = "Unknown"
                if not drug_a or not drug_b or drug_a == drug_b:
                    continue
                key = tuple(sorted((drug_a, drug_b)))
                # if the same pair appears twice, keep the more serious level
                if key not in pairs or SEVERITY_RANK[level] < SEVERITY_RANK[pairs[key]]:
                    pairs[key] = level

    db.query(models.DrugInteraction).delete()
    db.bulk_insert_mappings(
        models.DrugInteraction,
        [{"drug_a": a, "drug_b": b, "level": level} for (a, b), level in pairs.items()],
    )
    db.commit()
    return {"files": len(files), "pairs": len(pairs), "levels": dict(Counter(pairs.values()))}


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FOLDER
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        result = load_folder(session, folder)
    except FileNotFoundError as error:
        raise SystemExit(str(error))
    finally:
        session.close()
    print(f"Loaded {result['pairs']} interaction pairs from {result['files']} files.")
    print("By severity:", result["levels"])
