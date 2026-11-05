"""Reads every prescription listed in samples/answers.csv and scores the reader.
Usage:  python score_reader.py                      (all files)
        python score_reader.py mock_prescription_2.jpg   (only some files)"""
import sys
import time
from pathlib import Path

from checker import check_prescription
from reader import read_prescription
from scoring import add_up, load_answers, percent, score_prescription

SAMPLES = Path("samples")


def main() -> None:
    answers = load_answers(SAMPLES / "answers.csv")
    names = sys.argv[1:] or list(answers)
    scores = []

    for file_name in names:
        if file_name not in answers:
            print(f"{file_name}: not in samples/answers.csv, skipped")
            continue
        path = SAMPLES / file_name
        if not path.is_file():
            print(f"{file_name}: file not found in the samples folder, skipped")
            continue
        try:
            checked = check_prescription(read_prescription(path))
        except Exception as error:
            print(f"{file_name}: could not be read -> {str(error)[:110]}")
            continue

        score = score_prescription(answers[file_name], checked)
        scores.append(score)
        print(f"\n{file_name}: {score['found']}/{score['expected']} medicines found, "
              f"date {'OK' if score['date_ok'] else 'WRONG'}, flagged {score['flagged']}")
        parts = [f"{field} {score['fields'][field][0]}/{score['fields'][field][1]}" for field in score["fields"]]
        print("   " + " | ".join(parts))
        if score["missed"]:
            print("   MISSED:", ", ".join(score["missed"]))
        if score["extra"]:
            print("   EXTRA (not on the answer sheet):", ", ".join(score["extra"]))
        for line in score["wrong"]:
            print("   WRONG:", line)
        for line in score["warnings"]:
            print("   WARNING:", line)
        time.sleep(2)          # be gentle with the free limit

    if scores:
        total = add_up(scores)
        print("\n===== TOTAL =====")
        print(f"files read: {total['files']} | medicines found: {total['found']}/{total['expected']} "
              f"({percent(total['found'], total['expected'])}) | extra: {total['extra']}")
        print(f"dates right: {total['dates_ok']}/{total['files']}")
        for field, (right, count) in total["fields"].items():
            print(f"{field}: {right}/{count} ({percent(right, count)})")


if __name__ == "__main__":
    main()
