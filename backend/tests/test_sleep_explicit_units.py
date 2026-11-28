"""Durasi tidur data AKTUAL distandarkan ke JAM desimal (keputusan tim, 27 Nov 2026).

Default AKTIF: bentuk berunit eksplisit dan angka tanpa satuan (= jam) dikonversi. HH:MM dan teks lain
tetap NA. TOBA_SLEEP_EXPLICIT_UNITS=0 / TOBA_SLEEP_BARE_NUMERIC_IS_HOURS=0 mematikan perilaku baru.
Fixture di sini SINTETIS.
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
BARE_HOURS = {"7": 7.0, "6.5": 6.5, "6,5": 6.5, "4.5": 4.5, "8.0": 8.0}
AMBIGUOUS = ["06:30", "6:05", "0.3", "tujuh", "sekitar 7 jam"]
OUT_OF_RANGE = ["19 jam", "1200 menit", "7 jam 75 menit", "24 jam", "420"]


def test_default_aktif_standar_jam():
    with flag(None):
        assert sleep_explicit_enabled()
        for raw, hours in {**EXPLICIT, **BARE_HOURS}.items():
            assert parse_value(raw, SLEEP, synthetic=False) == (hours, None), raw


def test_flag_nol_mengembalikan_perilaku_lama():
    import os
    old = os.environ.get("TOBA_SLEEP_BARE_NUMERIC_IS_HOURS")
    os.environ["TOBA_SLEEP_BARE_NUMERIC_IS_HOURS"] = "0"
    try:
        with flag("0"):
            assert not sleep_explicit_enabled()
            for raw in list(EXPLICIT) + list(BARE_HOURS):
                assert parse_value(raw, SLEEP, synthetic=False) == UNCONFIRMED, raw
    finally:
        if old is None:
            os.environ.pop("TOBA_SLEEP_BARE_NUMERIC_IS_HOURS", None)
        else:
            os.environ["TOBA_SLEEP_BARE_NUMERIC_IS_HOURS"] = old


def test_bentuk_ambigu_tetap_unconfirmed():
    with flag(None):
        for raw in AMBIGUOUS:
            assert parse_value(raw, SLEEP, synthetic=False) == UNCONFIRMED, raw


def test_di_luar_rentang_ditandai_invalid():
    with flag(None):
        for raw in OUT_OF_RANGE:
            assert parse_value(raw, SLEEP, synthetic=False) == (None, "invalid_sleep_duration"), raw


def test_kosong_tetap_na_tanpa_isu():
    for value in (None, "0"):
        with flag(value):
            assert parse_value("", SLEEP, synthetic=False) == (None, None)
            assert parse_value("nan", SLEEP, synthetic=False) == (None, None)


def test_jalur_sintetis_tidak_terpengaruh_flag():
    for value in (None, "0", "1"):
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


def test_pipeline_aktual_tidur_terisi_dan_hhmm_tetap_na():
    from backend.app.pipeline import prepare
    p, d = _sources()
    d.iloc[0, 19] = "7 jam 30 menit"
    d.iloc[1, 19] = "420 menit"
    d.iloc[2, 19] = "6.5"
    with flag(None):
        _, days, _, q = prepare(p, d, synthetic=False)
    assert [days[i]["sleep_hours"] for i in range(3)] == [7.5, 7.0, 6.5]
    # Sisa baris fixture berbentuk HH:MM: ambigu, tidak ditebak.
    assert sum(row["sleep_hours"] is not None for row in days) == 3
    filled = int((d.iloc[:, 19].str.strip() != "").sum())  # sel kosong = NA tanpa isu
    assert q["issue_counts"]["sleep_semantics_unconfirmed"] == filled - 3
