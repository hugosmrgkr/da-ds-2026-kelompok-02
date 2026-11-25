"""Ringkasan isu per kolom: hanya agregat, tanpa nomor baris maupun nilai mentah. Fixture SINTETIS."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.audit_field_issues import COLUMNS, summarize_issues, render_table, write_report, main  # noqa: E402

FAKE = {
    "row_outcomes": {"profiles": {"raw": 10}, "daily": {"raw": 200}},
    "issues": (
        [{"source": "daily", "row": n, "column": 19, "field": "sleep_hours",
          "code": "sleep_semantics_unconfirmed", "action": "set_null"} for n in range(2, 52)]
        + [{"source": "daily", "row": 9, "column": 18, "field": "sitting",
            "code": "invalid_category", "action": "set_null", "raw": "RAHASIA"}]
        + [{"source": "profiles", "row": 3, "column": 4, "field": "age",
            "code": "invalid_number_or_unit", "action": "set_null"}]
    ),
}


def test_hitung_per_kolom_urut_terbanyak_dan_porsi():
    rows = summarize_issues(FAKE)
    assert [(r["source"], r["field"], r["code"], r["count"]) for r in rows] == [
        ("daily", "sleep_hours", "sleep_semantics_unconfirmed", 50),
        ("daily", "sitting", "invalid_category", 1),
        ("profiles", "age", "invalid_number_or_unit", 1)]
    assert rows[0]["share_of_raw_rows"] == 0.25
    assert rows[2]["share_of_raw_rows"] == 0.1


def test_keluaran_tidak_memuat_baris_atau_nilai_mentah():
    rows = summarize_issues(FAKE)
    assert all(set(r) == set(COLUMNS) for r in rows)
    assert "RAHASIA" not in json.dumps(rows) and "RAHASIA" not in render_table(rows)


def test_tanpa_isu_dan_tanpa_baris_mentah_tidak_error():
    assert summarize_issues({}) == []
    assert "Tidak ada isu" in render_table([])
    rows = summarize_issues({"issues": [{"source": "daily", "field": "x", "code": "c"}]})
    assert rows[0]["share_of_raw_rows"] is None


def test_laporan_ditulis_csv_dan_json():
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        write_report(summarize_issues(FAKE), {"source_kind": "synthetic", "row_outcomes": FAKE["row_outcomes"]}, folder)
        csv_text = (Path(folder) / "field_issue_summary.csv").read_text(encoding="utf-8-sig")
        assert csv_text.splitlines()[0] == ",".join(COLUMNS)
        data = json.loads((Path(folder) / "field_issue_summary.json").read_text(encoding="utf-8"))
        assert data["fields"][0]["field"] == "sleep_hours"


def test_cli_sintetis_berjalan_dan_aktual_menolak_file_sampel():
    assert main(["--source-kind", "synthetic"]) == 0
    try:
        main(["--source-kind", "actual"])  # path default = data/sample -> harus ditolak
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("data/sample tidak boleh dilabel aktual")


def test_cli_aktual_menolak_report_dir_publik():
    try:
        main(["--source-kind", "actual", "--profile", str(ROOT / "README.md"), "--daily", str(ROOT / "README.md"),
              "--report-dir", str(ROOT / "reports" / "x")])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("laporan aktual tidak boleh ke folder publik")
