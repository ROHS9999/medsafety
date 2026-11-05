from checker import check_medicine, check_prescription
from reader import PrescriptionRead, ReadMedicine


def med(written, name, strength=None, dose=None, frequency=None, duration=None, unclear=False):
    return ReadMedicine(
        written_text=written, name=name, strength=strength, dose=dose,
        frequency=frequency, duration=duration, unclear=unclear,
    )


def test_a_clean_line_passes_untouched():
    result = check_medicine(med("1. Tab Dolo 650 mg 1-1-1 after food x 5 days", "Tab Dolo",
                                strength="650 mg", frequency="1-1-1 after food", duration="x 5 days"))
    assert result.problems == [] and result.unclear is False
    assert (result.strength, result.frequency, result.duration) == ("650 mg", "1-1-1 after food", "x 5 days")


def test_an_invented_dose_is_removed():
    # The real mistake from your Colab test: "typically 2 scoops" was never written.
    result = check_medicine(med("5. Provigor-HP Powder x 1 mth", "Provigor-HP Powder",
                                dose="typically 2 scoops/teaspoons", duration="x 1 mth"))
    assert result.dose is None
    assert result.duration == "x 1 mth"
    assert result.unclear is True
    assert any("dose" in p for p in result.problems)


def test_an_invented_duration_is_removed():
    result = check_medicine(med("5. Tab Thyronorm 50 mcg 1 OD empty stomach Continue", "Tab Thyronorm",
                                strength="50 mcg", duration="30 days"))
    assert result.duration is None and result.unclear is True


def test_a_number_hiding_inside_another_number_is_not_accepted():
    # Dose "1" is not written. It only appears inside "10 days".
    result = check_medicine(med("3. Tab Pan 40 mg OD x 10 days", "Tab Pan", dose="1", duration="x 10 days"))
    assert result.dose is None
    assert result.duration == "x 10 days"


def test_spaces_and_capitals_do_not_matter():
    result = check_medicine(med("Tab Dolo 650mg  od  x5 days", "tab dolo", strength="650 mg",
                                frequency="OD", duration="x 5 days"))
    assert result.problems == [] and result.strength == "650 mg" and result.frequency == "OD"


def test_different_dash_characters_match():
    result = check_medicine(med("Tab Dolo 650 mg 1-0-1", "Tab Dolo", frequency="1\u20130\u20131"))
    assert result.problems == []


def test_a_salt_name_that_is_not_written_is_flagged():
    result = check_medicine(med("1. Tab Dolo 650", "Paracetamol"))
    assert result.unclear is True
    assert any("name" in p for p in result.problems)


def test_unreadable_marks_make_it_unclear():
    result = check_medicine(med("Tab ???? 1 OD", "Tab ????", frequency="OD"))
    assert result.unclear is True and result.problems == []


def test_the_ai_saying_unclear_is_respected():
    result = check_medicine(med("Tab Dolo 650", "Tab Dolo", unclear=True))
    assert result.unclear is True and result.problems == []


def test_empty_strings_count_as_not_written():
    result = check_medicine(med("Tab Dolo 650", "Tab Dolo", dose="", duration="  "))
    assert result.dose is None and result.duration is None and result.problems == []


def test_a_missing_written_line_is_flagged():
    result = check_medicine(med("", "Tab Dolo"))
    assert result.unclear is True and result.problems


def test_whole_prescription_keeps_the_date_exactly_and_counts_checks():
    read = PrescriptionRead(medicine_lines_on_page=None, 
        prescription_date="05/10/2026", doctor_name="Dr. A. Rao",
        medicines=[med("Tab Dolo 650 mg 1 OD", "Tab Dolo", strength="650 mg"),
                   med("Tab Pan 40 mg", "Tab Pan", duration="10 days")],
    )
    checked = check_prescription(read)
    assert checked.prescription_date == "05/10/2026"
    assert [m.unclear for m in checked.medicines] == [False, True]


def test_the_original_answer_is_not_changed():
    original = med("Tab Pan 40 mg", "Tab Pan", duration="10 days")
    check_medicine(original)
    assert original.duration == "10 days"


# ---------- Brick 20: dates and the medicine count ----------
import pytest

from checker import date_looks_complete


@pytest.mark.parametrize("text,ok", [
    ("05/10/2026", True), ("5/10/26", True), ("24-7-2023", True), ("24.07.2023", True),
    ("2026-10-05", True), ("5 Oct 2026", True), ("5th October 2026", True), ("Oct 5, 2026", True), ("October 5th 2026", True), ("Oct 2026", False),
    ("6/6/", False), ("6/6", False), ("05/10", False), ("2026", False), ("hello", False), ("", False),
])
def test_date_looks_complete(text, ok):
    assert date_looks_complete(text) is ok


def make_reading(count, how_many, date="05/10/2026"):
    medicines = [med(f"{i}. Tab Drug{i} 10 mg", f"Tab Drug{i}", strength="10 mg") for i in range(1, how_many + 1)]
    return PrescriptionRead(medicine_lines_on_page=count, prescription_date=date, doctor_name=None, medicines=medicines)


def test_a_missing_medicine_gives_a_warning():
    checked = check_prescription(make_reading(count=5, how_many=3))
    assert len(checked.warnings) == 1 and "5" in checked.warnings[0] and "3" in checked.warnings[0]


def test_matching_count_gives_no_warning():
    assert check_prescription(make_reading(count=3, how_many=3)).warnings == []


def test_no_count_from_the_ai_gives_no_count_warning():
    assert check_prescription(make_reading(count=None, how_many=3)).warnings == []


def test_an_incomplete_date_gives_a_warning():
    checked = check_prescription(make_reading(count=2, how_many=2, date="6/6/"))
    assert len(checked.warnings) == 1 and "6/6/" in checked.warnings[0]


def test_a_missing_date_is_not_a_warning():
    assert check_prescription(make_reading(count=2, how_many=2, date=None)).warnings == []
