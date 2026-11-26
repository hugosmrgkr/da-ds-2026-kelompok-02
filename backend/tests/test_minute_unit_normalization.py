"""Normalisasi satuan menit (kolom 17 dan 18): jam eksplisit dikonversi, angka telanjang tetap menit.

Fixture di sini SINTETIS: contoh jawaban dibuat untuk menguji parser, bukan salinan jawaban responden.
Aturan: satuan jam harus eksplisit; nilai ambigu atau di luar 0-1440 tetap ditolak (NA + isu).
"""
import pandas as pd

from pathlib import Path
from backend.app.survey_schema import DAILY_FIELDS, parse_value, parse_numeric

DATA = Path(__file__).resolve().parents[2] / "data" / "sample"

ACTIVITY = next(f for f in DAILY_FIELDS if f["technical"] == "activity_minutes")
HEAVY = next(f for f in DAILY_FIELDS if f["technical"] == "heavy_minutes")

VALID = {
    "0": 0, "30": 30, "30 menit": 30, "30 Menit": 30, " 45  menit ": 45,
    "90 mnt": 90, "90 min": 90,
    "1 jam": 60, "1,5 jam": 90, "1.5 jam": 90, "2 jam": 120, "0,5 jam": 30,
    "1 jam 30 menit": 90, "1 jam 30": 90, "1jam30": 90, "2 jam 5 menit": 125,
    "24 jam": 1440,
}
INVALID = ["abc", "", "1.5", "1,5", "25 jam", "-5 menit", "-1 jam", "0,01 jam",
           "2 jam 90 menit", "1 jam 75", "jam", "1 hari", "1 jam lebih", "1440,5"]


def test_nilai_valid_dikonversi_ke_menit_bulat():
    for raw, expected in VALID.items():
        for synthetic in (True, False):
            value, issue = parse_value(raw, ACTIVITY, synthetic=synthetic)
            assert (value, issue) == (expected, None), (raw, synthetic, value, issue)


def test_kolom_menit_berat_memakai_aturan_sama():
    assert parse_value("1,5 jam", HEAVY, synthetic=False) == (90, None)
    assert parse_value("15 menit", HEAVY, synthetic=False) == (15, None)


def test_nilai_ambigu_atau_di_luar_rentang_ditolak_tanpa_menebak():
    for raw in INVALID:
        value, issue = parse_value(raw, ACTIVITY, synthetic=False)
        if raw == "":
            assert (value, issue) == (None, None), raw  # kosong = NA tanpa isu, seperti sebelumnya
        else:
            assert (value, issue) == (None, "invalid_number_or_unit"), (raw, value, issue)


def test_satuan_lain_tidak_berubah():
    assert parse_numeric("170 cm", "cm", [80, 250]) == 170
    assert parse_numeric("170 kg", "cm", [80, 250]) is None
    assert parse_numeric("5 hari", "hari/minggu", [0, 7], True) == 5
    assert parse_numeric("30 tahun", "tahun", [0, 120], True) == 30
    assert parse_numeric("1 jam", "kg", [15, 300]) is None  # jam hanya berlaku untuk menit


def test_konversi_tercatat_sebagai_normalisasi_pada_pipeline():
    """Nilai '1,5 jam' menjadi 90 dan tercatat di normalizations_by_field (audit), bukan diam-diam."""
    from backend.app.pipeline import prepare
    profiles = pd.read_csv(str(DATA / "Data_Responden_Sintetis.csv"), dtype=str, keep_default_na=False)
    days = pd.read_csv(str(DATA / "Data_Harian_Sintetis.csv"), dtype=str, keep_default_na=False)
    baseline = prepare(profiles, days.copy(), synthetic=True)[3]["normalizations_by_field"]
    days.iloc[0, 16] = "1,5 jam"
    _, rows, _, quality = prepare(profiles, days, synthetic=True)
    assert rows[0]["activity_minutes"] == 90
    assert quality["normalizations_by_field"]["activity_minutes"] == baseline.get("activity_minutes", 0) + 1
