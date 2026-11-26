"""Preprocessing asin/olahan (soal 21): dua kategori, Mengonsumsi asin/olahan / Tidak
mengonsumsi asin/olahan. Soal ini menggabungkan dua jenis makanan ("asin ATAU olahan") dalam
satu hitungan, jadi hanya ada/tidak-adanya konsumsi yang dipakai, bukan jumlah pastinya."""
import pandas as pd
import pytest

from backend.app.pipeline import prepare, verify_headers, EXPECTED_DAILY_HEADERS, DataQualityError, parse_days
from backend.app.survey_schema import DAILY_FIELDS, parse_value, SALTY_YES, SALTY_NO, SALTY_SYNTHETIC

SALTY = next(f for f in DAILY_FIELDS if f["technical"] == "salty_food")


@pytest.mark.parametrize("raw", ["1 kali", "2 kali", "3 kali atau lebih", " 1 Kali ", "2 KALI"])
def test_jawaban_pernah_menjadi_mengonsumsi(raw):
    assert parse_value(raw, SALTY, synthetic=False) == (SALTY_YES, None)


@pytest.mark.parametrize("raw", ["Tidak sama sekali", "tidak sama sekali", " Tidak Sama Sekali "])
def test_tidak_sama_sekali_menjadi_tidak_mengonsumsi(raw):
    assert parse_value(raw, SALTY, synthetic=False) == (SALTY_NO, None)


@pytest.mark.parametrize("raw", ["", "nan", None])
def test_kosong_tetap_na_bukan_tidak_mengonsumsi(raw):
    # Beda dari buah (teks bebas): soal ini pilihan ganda tertutup, jadi kosong berarti memang
    # tidak dijawab -- tidak boleh diam-diam disamakan dengan "Tidak sama sekali".
    assert parse_value(raw, SALTY, synthetic=False) == (None, None)


@pytest.mark.parametrize("raw", ["4 kali", "sering", "kadang-kadang", "1", "banyak"])
def test_jawaban_di_luar_empat_pilihan_tidak_ditebak(raw):
    assert parse_value(raw, SALTY, synthetic=False) == (None, "invalid_category")


def test_csv_sintetis_tidak_berubah_empat_label_asli():
    profiles = pd.read_csv("data/sample/Data_Responden_Sintetis.csv", dtype=str, keep_default_na=False)
    daily = pd.read_csv("data/sample/Data_Harian_Sintetis.csv", dtype=str, keep_default_na=False)
    _, days, _, _ = prepare(profiles, daily)
    assert {d["salty_food"] for d in days} <= set(SALTY_SYNTHETIC)


def test_data_aktual_hanya_dua_kategori_lewat_pipeline():
    profiles = pd.read_csv("data/sample/Data_Responden_Sintetis.csv", dtype=str, keep_default_na=False)
    daily = pd.read_csv("data/sample/Data_Harian_Sintetis.csv", dtype=str, keep_default_na=False)
    col = next(c for c in daily.columns if c.startswith("21."))
    pattern = ["1 kali", "Tidak sama sekali", "3 kali atau lebih", "2 kali"]
    daily[col] = (pattern * (len(daily) // len(pattern) + 1))[: len(daily)]
    ids = set(profiles[profiles.columns[1]])
    days, _, _ = parse_days(daily, ids, synthetic=False)
    assert {d["salty_food"] for d in days} == {SALTY_YES, SALTY_NO}


def test_header_soal_21_masih_diperiksa_oleh_kontrak():
    cols = list(EXPECTED_DAILY_HEADERS)
    i = next(n for n, c in enumerate(cols) if c.startswith("21."))
    cols[i] = "21. Pertanyaan lain yang tidak sesuai kontrak"
    with pytest.raises(DataQualityError):
        verify_headers(pd.DataFrame(columns=cols), EXPECTED_DAILY_HEADERS, "Form Harian")


# ---------------------------------------------------------------------------
# Regression tests for the two code-review findings (both fixed generically for every
# binary-coded field -- fruit and salty_food -- not special-cased per field).
# ---------------------------------------------------------------------------

def test_synthetic_parameter_is_required_not_defaulted():
    """A caller that forgets `synthetic` must fail loudly, not silently mis-parse a binary field
    with the wrong contract. This is the exact bug the review flagged: an actual-data caller that
    forgot `synthetic=False` would previously have had `fruit`/`salty_food` silently parsed with
    the synthetic multi-category contract instead of being grouped into the binary labels."""
    with pytest.raises(TypeError):
        parse_value("1 kali", SALTY)  # no `synthetic` argument at all


def test_max_length_is_enforced_for_binary_fields_before_the_binary_branch():
    """The review found that `kind == "binary_fruit"` returned before the shared max_length
    check ever ran, so the contract's max_length=90 was silently never enforced. Same fix
    applies to salty_food since both go through the same binary-category code path now."""
    too_long = "x" * (SALTY["max_length"] + 1)
    assert parse_value(too_long, SALTY, synthetic=False) == (None, "text_too_long")
    assert parse_value(too_long, SALTY, synthetic=True) == (None, "text_too_long")
