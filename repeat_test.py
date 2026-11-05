r"""Reads the same prescription several times, to see if the answer changes between runs.
Usage: python repeat_test.py samples\mock_prescription_1.png 3"""
import sys
import time

from checker import check_prescription
from reader import read_prescription

if len(sys.argv) < 2:
    raise SystemExit("Usage: python repeat_test.py samples\\your-photo.png 3")
path = sys.argv[1]
times = int(sys.argv[2]) if len(sys.argv) > 2 else 3

for number in range(1, times + 1):
    started = time.time()
    try:
        result = read_prescription(path)
    except Exception as error:
        print(f"Run {number}: FAILED -> {str(error)[:100]}")
        continue
    checked = check_prescription(result)
    flagged = sum(1 for med in checked.medicines if med.unclear)
    print(
        f"Run {number}: {len(checked.medicines)} medicines | AI counted on page: "
        f"{result.medicine_lines_on_page} | date: {result.prescription_date} | "
        f"flagged: {flagged} | {time.time() - started:.0f}s"
    )
    for warning in checked.warnings:
        print("   WARNING:", warning)
