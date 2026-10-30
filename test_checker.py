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
    read = PrescriptionRead(
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
