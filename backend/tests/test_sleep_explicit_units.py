"""Durasi tidur berunit eksplisit untuk data AKTUAL, di belakang flag TOBA_SLEEP_EXPLICIT_UNITS.

Default MATI: perilaku lama (semua jawaban tidur aktual = NA + sleep_semantics_unconfirmed) tidak berubah
sampai tim/dosen menyetujui definisi tidur. Fixture di sini SINTETIS.
"""
import os
from contextlib import contextmanager

import pandas as pd

from pathlib import Path
from backend.app.survey_schema import (DAILY_FIELDS, SLEEP_FLAG, parse_value, parse_sleep_explicit,
                                       sleep_explicit_enabled)

DATA = Path(__file__).resolve().parents[2] / "data" / "sample"

SLEEP = next(f for f in DAILY_FIELDS if f["technical"] == "sleep_hours")
UNCONFIRMED = (None, "sleep_semantics_unconfirmed")


@contextmanager
def flag(value):
    old = os.environ.get(SLEEP_FLAG)
    try:
        if value is None:
            os.environ.pop(SLEEP_FLAG, None)
        else:
            os.environ[SLEEP_FLAG] = value
        yield
    finally:
        if old is None:
            os.environ.pop(SLEEP_FLAG, None)
        else:
            os.environ[SLEEP_FLAG] = old


EXPLICIT = {"7 jam": 7.0, "7,5 jam": 7.5, "7.5 JAM": 7.5, "7 jam 30 menit": 7.5, "7 jam 30": 7.5,
            "420 menit": 7.0, "450 mnt": 7.5, "90 min": 1.5, "0 jam": 0.0, "18 jam": 18.0,
            "6 jam 20 menit": 6.333}
AMBIGUOUS = ["7", "7,5", "420", "06:30", "6:05", "0.3", "tujuh", "sekitar 7 jam"]
OUT_OF_RANGE = ["19 jam", "1200 menit", "7 jam 75 menit", "24 jam"]


def test_default_mati_semua_bentuk_tetap_unconfirmed():
    with flag(None):
        assert not sleep_explicit_enabled()
        for raw in list(EXPLICIT) + AMBIGUOUS + OUT_OF_RANGE:
            assert parse_value(raw, SLEEP, synthetic=False) == UNCONFIRMED, raw


def test_flag_selain_satu_tidak_mengaktifkan():
    for value in ("0", "", "true", "yes", "2", " "):
        with flag(value):
            assert not sleep_explicit_enabled(), value
            assert parse_value("7 jam", SLEEP, synthetic=False) == UNCONFIRMED


def test_flag_aktif_bentuk_eksplisit_dikonversi_ke_jam_desimal():
    with flag("1"):
        assert sleep_explicit_enabled()
        for raw, hours in EXPLICIT.items():
            assert parse_value(raw, SLEEP, synthetic=False) == (hours, None), raw


def test_flag_aktif_bentuk_ambigu_tetap_unconfirmed():
    with flag("1"):
        for raw in AMBIGUOUS:
            assert parse_value(raw, SLEEP, synthetic=False) == UNCONFIRMED, raw


def test_flag_aktif_di_luar_rentang_ditandai_invalid():
    with flag("1"):
        for raw in OUT_OF_RANGE:
            assert parse_value(raw, SLEEP, synthetic=False) == (None, "invalid_sleep_duration"), raw


def test_kosong_tetap_na_tanpa_isu():
    for value in (None, "1"):
        with flag(value):
            assert parse_value("", SLEEP, synthetic=False) == (None, None)
            assert parse_value("nan", SLEEP, synthetic=False) == (None, None)


def test_jalur_sintetis_tidak_terpengaruh_flag():
    for value in (None, "1"):
        with flag(value):
            assert parse_value("06:30", SLEEP, synthetic=True) == (6.5, None)
            assert parse_value("7", SLEEP, synthetic=True) == (7.0, None)
            assert parse_value("0.3", SLEEP, synthetic=True) == (None, "ambiguous_excel_sleep_fraction")


def test_parse_sleep_explicit_matched_flag():
    assert parse_sleep_explicit("7") == (False, None)
    assert parse_sleep_explicit("06:30") == (False, None)
    assert parse_sleep_explicit("7 jam 75 menit") == (True, None)
    assert parse_sleep_explicit("7 jam") == (True, 7.0)


def _sources():
    p = pd.read_csv(str(DATA / "Data_Responden_Sintetis.csv"), dtype=str, keep_default_na=False)
    d = pd.read_csv(str(DATA / "Data_Harian_Sintetis.csv"), dtype=str, keep_default_na=False)
    return p, d


def _filled_sleep_cells(d):
    """Sel tidur terisi; sel kosong adalah NA tanpa isu pada kedua mode."""
    return int((d.iloc[:, 19].str.strip() != "").sum())


def test_pipeline_aktual_flag_mati_semua_tidur_na():
    from backend.app.pipeline import prepare
    p, d = _sources()
    d.iloc[0, 19] = "7 jam 30 menit"
    with flag(None):
        _, days, _, q = prepare(p, d, synthetic=False)
    assert q["issue_counts"]["sleep_semantics_unconfirmed"] == _filled_sleep_cells(d)
    assert all(row["sleep_hours"] is None for row in days)


def test_pipeline_aktual_flag_aktif_hanya_bentuk_eksplisit_terisi():
    from backend.app.pipeline import prepare
    p, d = _sources()
    d.iloc[0, 19] = "7 jam 30 menit"
    with flag("1"):
        _, days, _, q = prepare(p, d, synthetic=False)
    assert days[0]["sleep_hours"] == 7.5
    # Baris lain (HH:MM sintetis) tetap ambigu: tidak ada yang ditebak.
    assert q["issue_counts"]["sleep_semantics_unconfirmed"] == _filled_sleep_cells(d) - 1
    assert sum(row["sleep_hours"] is not None for row in days) == 1
