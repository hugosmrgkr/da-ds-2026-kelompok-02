"""Label hasil praproses data aktual: Makan / Tidak Makan (asin/olahan) dan Makan Buah / Tidak Makan Buah."""
import pytest

from backend.app.survey_schema import (
    DAILY_FIELDS, FRUIT_NO, FRUIT_YES, SALTY_NO, SALTY_YES, parse_value,
)

SALTY = next(f for f in DAILY_FIELDS if f["technical"] == "salty_food")
FRUIT = next(f for f in DAILY_FIELDS if f["technical"] == "fruit")


def test_label_sesuai_keputusan_tim():
    assert (SALTY_YES, SALTY_NO) == ("Makan", "Tidak Makan")
    assert (FRUIT_YES, FRUIT_NO) == ("Makan Buah", "Tidak Makan Buah")


@pytest.mark.parametrize("raw,expected", [
    ("Tidak sama sekali", SALTY_NO), ("1 kali", SALTY_YES), ("2 kali", SALTY_YES),
    ("3 kali atau lebih", SALTY_YES),
    ("Makan", SALTY_YES), ("makan", SALTY_YES), ("Tidak Makan", SALTY_NO), (" tidak  makan ", SALTY_NO),
])
def test_salty_jawaban_lama_dan_revisi(raw, expected):
    assert parse_value(raw, SALTY, synthetic=False) == (expected, None)


@pytest.mark.parametrize("raw,expected", [
    ("Tidak mengonsumsi buah", FRUIT_NO), ("1 porsi", FRUIT_YES), ("2 porsi", FRUIT_YES),
    ("3 porsi atau lebih", FRUIT_YES),
    ("Makan Buah", FRUIT_YES), ("makan buah", FRUIT_YES), ("Tidak Makan Buah", FRUIT_NO),
])
def test_buah_jawaban_lama_dan_revisi(raw, expected):
    assert parse_value(raw, FRUIT, synthetic=False) == (expected, None)


def test_jawaban_tak_dikenal_tidak_ditebak():
    assert parse_value("sering", SALTY, synthetic=False) == (None, "invalid_category")
    assert parse_value("entahlah", FRUIT, synthetic=False) == (None, "invalid_category")
