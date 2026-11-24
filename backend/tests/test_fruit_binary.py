"""Preprocessing buah (kolom 22): hanya dua kategori, Makan buah / Tidak makan buah."""
import pandas as pd
import pytest

from backend.app.pipeline import prepare, verify_headers, EXPECTED_DAILY_HEADERS, DataQualityError
from backend.app.survey_schema import DAILY_FIELDS, parse_value, FRUIT_YES, FRUIT_NO

FRUIT = next(f for f in DAILY_FIELDS if f["technical"] == "fruit")

YES = ["2 porsi", "1 porsi", "1", "2", "dua", "satu", "1 prsi", "3 porsi atau lebih", "Dua", " 2  porsi ", "1.0"]
NO = ["", "0", "-", "tdk", "Tidak mengonsumsi buah", "tidak mengonsumsi buah", "0 porsi", "tidak", "nan", "–"]


@pytest.mark.parametrize("raw", YES)
def test_nilai_bermakna_menjadi_makan_buah(raw):
    assert parse_value(raw, FRUIT, synthetic=False) == (FRUIT_YES, None)


@pytest.mark.parametrize("raw", NO)
def test_kosong_nol_strip_tidak_menjadi_tidak_makan_buah(raw):
    assert parse_value(raw, FRUIT, synthetic=False) == (FRUIT_NO, None)


@pytest.mark.parametrize("raw", ["banyak sekali", "tidak 2 porsi", "xyz"])
def test_jawaban_ambigu_tidak_ditebak(raw):
    assert parse_value(raw, FRUIT, synthetic=False) == (None, "invalid_category")


def test_header_versi_banyak_buah_diterima():
    cols = list(EXPECTED_DAILY_HEADERS)
    i = next(n for n, c in enumerate(cols) if c.startswith("22."))
    cols[i] = "22. Hari ini, berapa banyak buah yang Anda makan?"
    verify_headers(pd.DataFrame(columns=cols), EXPECTED_DAILY_HEADERS, "Form Harian")
    cols[i] = "22. Pertanyaan lain"
    with pytest.raises(DataQualityError):
        verify_headers(pd.DataFrame(columns=cols), EXPECTED_DAILY_HEADERS, "Form Harian")


def test_csv_sintetis_tidak_berubah_empat_label_asli():
    profiles = pd.read_csv("data/sample/Data_Responden_Sintetis.csv", dtype=str, keep_default_na=False)
    daily = pd.read_csv("data/sample/Data_Harian_Sintetis.csv", dtype=str, keep_default_na=False)
    _, days, _, _ = prepare(profiles, daily)
    assert {d["fruit"] for d in days} == {"Tidak mengonsumsi buah", "1 porsi", "2 porsi", "3 porsi atau lebih"}


def test_data_aktual_hanya_dua_kategori_lewat_pipeline():
    profiles = pd.read_csv("data/sample/Data_Responden_Sintetis.csv", dtype=str, keep_default_na=False)
    daily = pd.read_csv("data/sample/Data_Harian_Sintetis.csv", dtype=str, keep_default_na=False)
    col = next(c for c in daily.columns if c.startswith("22."))
    daily[col] = ["dua", "", "-", "1 prsi"] * (len(daily) // 4) + ["satu"] * (len(daily) % 4)
    profiles["1. ID Responden"] = profiles["1. ID Responden"]
    from backend.app.pipeline import parse_days
    ids = set(profiles[profiles.columns[1]])
    days, _, _ = parse_days(daily, ids, synthetic=False)
    assert {d["fruit"] for d in days} == {FRUIT_YES, FRUIT_NO}
