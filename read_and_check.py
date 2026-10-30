import sys
import time

from checker import check_prescription, show_checked
from reader import read_prescription


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python read_and_check.py samples\\your-photo.jpg")
    started = time.time()
    try:
        result = read_prescription(sys.argv[1])
    except Exception as error:
        raise SystemExit(f"Could not read the prescription: {error}")
    show_checked(check_prescription(result))
    print(f"(Read in {time.time() - started:.1f} seconds)")


if __name__ == "__main__":
    main()
