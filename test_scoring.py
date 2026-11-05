from checker import CheckedMedicine, CheckedPrescription
from scoring import add_up, field_is_right, load_answers, score_prescription


def found(name, strength=None, dose=None, frequency=None, duration=None, unclear=False, written=None):
    return CheckedMedicine(
        written_text=written or f"{name} {strength or ''} {frequency or ''} {duration or ''}",
        name=name, strength=strength, dose=dose, frequency=frequency, duration=duration,
        unclear=unclear, problems=[],
    )


def prescription(medicines, date="05/10/2026", warnings=None):
    return CheckedPrescription(prescription_date=date, doctor_name=None, medicines=medicines, warnings=warnings or [])


def answer(*medicines, date="05/10/2026"):
    return {"date": date, "medicines": [
        {"name": n, "strength": s, "frequency": f, "duration": d} for n, s, f, d in medicines]}


def test_a_perfect_reading_scores_full_marks():
    score = score_prescription(
        answer(("Dolo", "650 mg", "1-1-1", "5 days"), ("Pan", "40 mg", "1 OD", "10 days")),
        prescription([found("Tab Dolo", "650 mg", None, "1-1-1", "x 5 days"),
                      found("Tab Pan", "40 mg", "1", "OD before breakfast", "x 10 days")]))
    assert score["found"] == 2 and score["missed"] == [] and score["extra"] == [] and score["wrong"] == []
    assert score["fields"] == {"strength": [2, 2], "frequency": [2, 2], "duration": [2, 2]} and score["date_ok"]


def test_a_missed_medicine_is_listed_and_its_fields_count_as_wrong():
    score = score_prescription(answer(("Dolo", "650 mg", "1-1-1", "5 days"), ("Pan", "40 mg", "1 OD", "10 days")),
                               prescription([found("Tab Dolo", "650 mg", None, "1-1-1", "x 5 days")]))
    assert score["found"] == 1 and score["missed"] == ["Pan"]
    assert score["fields"]["strength"] == [1, 2] and score["fields"]["duration"] == [1, 2]


def test_an_extra_medicine_is_listed():
    score = score_prescription(answer(("Dolo", "650 mg", "1-1-1", "5 days")),
                               prescription([found("Tab Dolo", "650 mg", None, "1-1-1", "x 5 days"), found("Tab Invented")]))
    assert score["extra"] == ["Tab Invented"]


def test_a_wrong_value_is_explained():
    score = score_prescription(answer(("Dolo", "650 mg", "1-1-1", "5 days")),
                               prescription([found("Tab Dolo", "500 mg", None, "1-1-1", "x 5 days")]))
    assert score["fields"]["strength"] == [0, 1]
    assert any("strength should be '650 mg', got '500 mg'" in w for w in score["wrong"])


def test_a_value_that_is_not_written_must_not_be_given():
    # Answer sheet: no strength written. The AI invented one: that is wrong.
    score = score_prescription(answer(("Combiflam", "", "1 TDS", "3 days")),
                               prescription([found("Tab Combiflam", "400 mg", None, "1 TDS", "x 3 days")]))
    assert score["fields"]["strength"] == [0, 1]
    clean = score_prescription(answer(("Combiflam", "", "1 TDS", "3 days")),
                               prescription([found("Tab Combiflam", None, None, "1 TDS", "x 3 days")]))
    assert clean["fields"]["strength"] == [1, 1]


def test_a_blank_duration_on_the_sheet_means_none_written():
    score = score_prescription(answer(("Dolo", "650 mg", "1 SOS", "")),
                               prescription([found("Tab Dolo", "650 mg", None, "1 SOS", None)]))
    assert score["fields"]["duration"] == [1, 1]


def test_the_dose_and_frequency_are_read_together():
    # The AI may put '1' in dose and 'OD' in frequency. Together they are '1 OD'.
    score = score_prescription(answer(("Pan", "40 mg", "1 OD", "10 days")),
                               prescription([found("Tab Pan", "40 mg", "1", "OD", "x 10 days")]))
    assert score["fields"]["frequency"] == [1, 1]


def test_a_blank_frequency_on_the_sheet_is_not_scored():
    score = score_prescription(answer(("Pan", "40 mg", "", "10 days")),
                               prescription([found("Tab Pan", "40 mg", None, "OD", "x 10 days")]))
    assert score["fields"]["frequency"] == [0, 0]


def test_the_date_must_match_exactly():
    assert score_prescription(answer(("Pan", "", "1 OD", ""), date="6/6/2026"), prescription([found("Tab Pan")], date="6/6/")) ["date_ok"] is False
    assert score_prescription(answer(("Pan", "", "1 OD", ""), date="6/6/2026"), prescription([found("Tab Pan")], date="6/6/2026"))["date_ok"] is True


def test_two_medicines_with_the_same_name_are_matched_one_each():
    score = score_prescription(answer(("Pan", "20 mg", "1 OD", ""), ("Pan", "40 mg", "1 BD", "")),
                               prescription([found("Tab Pan", "20 mg", None, "1 OD"), found("Tab Pan", "40 mg", None, "1 BD")]))
    assert score["found"] == 2 and score["extra"] == []


def test_a_name_inside_a_longer_word_is_not_a_match():
    score = score_prescription(answer(("Pan", "40 mg", "1 OD", "")), prescription([found("Tab Pancreatin", "40 mg", None, "1 OD")]))
    assert score["found"] == 0 and score["missed"] == ["Pan"] and score["extra"] == ["Tab Pancreatin"]


def test_totals_add_up_over_several_files():
    a = score_prescription(answer(("Dolo", "650 mg", "1-1-1", "5 days")), prescription([found("Tab Dolo", "650 mg", None, "1-1-1", "x 5 days")]))
    b = score_prescription(answer(("Pan", "40 mg", "1 OD", "10 days")), prescription([], date="x"))
    total = add_up([a, b])
    assert total["files"] == 2 and total["expected"] == 2 and total["found"] == 1 and total["dates_ok"] == 1
    assert total["fields"]["strength"] == [1, 2]


def test_empty_answers_for_field_is_right():
    assert field_is_right("", [None, ""]) and not field_is_right("", ["650 mg"])
    assert field_is_right("5 days", ["x 5 days"]) and not field_is_right("5 days", [None])


def test_the_answer_sheet_loads(tmp_path):
    sheet = tmp_path / "answers.csv"
    sheet.write_text("file,date,name,strength,frequency,duration\n"
                     "a.png,05/10/2026,Dolo,650 mg,1-1-1,5 days\n"
                     "a.png,05/10/2026,Pan,,1 OD,\n"
                     "b.png,1/1/2026,Zifi,200 mg,1 BD,5 days\n", encoding="utf-8-sig")
    answers = load_answers(sheet)
    assert list(answers) == ["a.png", "b.png"] and len(answers["a.png"]["medicines"]) == 2
    assert answers["a.png"]["medicines"][1] == {"name": "Pan", "strength": "", "frequency": "1 OD", "duration": ""}
    assert answers["a.png"]["date"] == "05/10/2026"


def test_the_real_answer_sheet_in_the_samples_folder_is_valid():
    from pathlib import Path
    answers = load_answers(Path("samples") / "answers.csv")
    assert len(answers) == 4 and sum(len(a["medicines"]) for a in answers.values()) == 23
    for file_name in answers:
        assert (Path("samples") / file_name).is_file(), f"{file_name} is missing"
