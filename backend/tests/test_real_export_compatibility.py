import pandas as pd

from backend.app.pipeline import (
    EXPECTED_PROFILE_HEADERS,
    EXPECTED_DAILY_HEADERS,
    prepare,
    verify_headers,
)
from backend.app.survey_schema import PROFILE_FIELDS, DAILY_FIELDS, parse_value


def _profile_row():
    values = []
    for spec in PROFILE_FIELDS:
        name = spec["technical"]
        values.append({
            "submitted_at": "01/11/2026 10:00:00",
            "respondent_id": "R001",
            "direct_identity": "PRIVATE NAME",
            "age": "25",
            "gender": "Laki- laki",
            "province": "Sumatera Utara",
            "city": "Toba",
            "occupation": "Mahasiswa",
            "education": "SMA atau SMK atau sederajat",
            "height_cm": "170",
            "weight_kg": "60",
            "usual_activity": "Jalan kaki untuk olahraga",
            "active_days_week": "3 hari",
        }.get(name, "Tidak"))
    return values


def _daily_row():
    values = []
    for spec in DAILY_FIELDS:
        name = spec["technical"]
        values.append({
            "submitted_at": "01/11/2026 21:00:00",
            "respondent_id": "R001",
            "date": "01/11/2026",
            "morning_time": "07:00",
            "evening_time": "20:00",
            "morning_sbp1": "120",
            "morning_dbp1": "80",
            "morning_sbp2": "118",
            "morning_dbp2": "79",
            "evening_sbp1": "121",
            "evening_dbp1": "81",
            "evening_sbp2": "119",
            "evening_dbp2": "80",
            "morning_context": "Tidak ada kegiatan di atas",
            "evening_context": "Tidak ada dari kegiatan di atas",
            "activity_type": "Jalan kaki untuk olahraga, Pekerjaan rumah, seperti menyapu, mengepel, atau berkebun",
            "activity_minutes": "30",
            "heavy_minutes": "0",
            "sitting": "4–7 jam",
            "sleep_hours": "7",
            "salty_food": "Tidak sama sekali",
            "fruit": "Tidak mengonsumsi buah",
            "vegetable": "Tidak mengonsumsi sayur",
            "caffeine": "Tidak mengonsumsi",
            "smoked": "Tidak berlaku karena saya tidak merokok",
            "smoke_count": "",
            "medication": "Saya tidak menggunakan obat tekanan darah",
            "stress": "3 = Sedang",
        }.get(name, ""))
    return values


def test_real_profile_export_ignores_only_trailing_score_column():
    profiles = pd.DataFrame(
        [_profile_row() + [""]],
        columns=EXPECTED_PROFILE_HEADERS + ["Score"],
    )
    daily = pd.DataFrame([_daily_row()], columns=EXPECTED_DAILY_HEADERS)

    parsed_profiles, parsed_days, sessions, quality = prepare(
        profiles, daily, synthetic=True
    )

    assert len(parsed_profiles) == 1
    assert len(parsed_days) == 1
    assert len(sessions) == 2
    assert quality["ignored_profile_columns"] == ["Score"]


def test_gender_spacing_variant_is_normalized():
    assert parse_value("Laki- laki", PROFILE_FIELDS[4], False) == ("Laki-laki", None)


def test_known_multi_select_labels_with_internal_commas_are_parsed():
    value = (
        "Jalan kaki untuk olahraga, "
        "Pekerjaan rumah, seperti menyapu, mengepel, atau berkebun"
    )
    parsed, issue = parse_value(value, DAILY_FIELDS[15], False)
    assert parsed == value
    assert issue is None


def test_actual_no_activity_context_wording_is_accepted():
    assert parse_value(
        "Tidak ada dari kegiatan di atas", DAILY_FIELDS[8], False
    ) == ("Tidak ada kegiatan di atas", None)


def test_real_fruit_and_vegetable_header_wording_is_accepted():
    daily = pd.DataFrame(columns=[
        h.replace("22. Hari ini, berapa porsi buah yang Anda makan?",
                  "22. Hari ini, berapa banyak buah yang Anda makan?")
         .replace("23. Hari ini, berapa porsi sayur yang Anda makan?",
                  "23. Hari ini, berapa banyak sayur yang Anda makan?")
        for h in EXPECTED_DAILY_HEADERS
    ])
    verify_headers(daily, EXPECTED_DAILY_HEADERS, "Form Harian")


def test_actual_numeric_sleep_is_hours_by_default(monkeypatch):
    monkeypatch.delenv("TOBA_SLEEP_EXPLICIT_UNITS", raising=False)
    monkeypatch.delenv("TOBA_SLEEP_BARE_NUMERIC_IS_HOURS", raising=False)
    assert parse_value("6.5", DAILY_FIELDS[19], False) == (6.5, None)
    assert parse_value("420 menit", DAILY_FIELDS[19], False) == (7.0, None)


def test_bare_numeric_sleep_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("TOBA_SLEEP_BARE_NUMERIC_IS_HOURS", "0")
    assert parse_value("6.5", DAILY_FIELDS[19], False) == (
        None, "sleep_semantics_unconfirmed"
    )
