"""Ringkasan isu per kolom dari dry-run ETL (hanya agregat, tidak menulis database).

Menjawab "kolom/kuesioner mana yang bermasalah": jumlah isu per (sumber, kolom, kode isu).
Tidak ada nomor baris dan tidak ada nilai mentah responden pada keluarannya.

Contoh dari root repository:
  python -m etl.audit_field_issues --source-kind synthetic
  python -m etl.audit_field_issues --source-kind actual \
      --profile data/private/incoming/form_awal.csv --daily data/private/incoming/catatan_harian.csv \
      --report-dir data/private/readiness/batch-YYYYMMDD
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.pipeline import prepare, DataQualityError

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["source", "field", "code", "action", "count", "share_of_raw_rows"]
HINTS = {
    "invalid_category": "Jawaban tidak cocok dengan opsi di skema: periksa teks opsi di form.",
    "invalid_number_or_unit": "Angka atau satuan tidak terbaca atau di luar rentang: periksa satuan pertanyaan.",
    "invalid_sleep_duration": "Durasi tidur di luar 0-18 jam atau menit tidak valid.",
    "sleep_semantics_unconfirmed": "Arti jawaban tidur aktual belum diputuskan; semua nilai tidur masih NA.",
    "ambiguous_excel_sleep_fraction": "Pecahan 0-1 pada tidur ambigu (bisa pecahan hari Excel).",
    "unmapped_other_category_review": "Pilihan 'lainnya' ditahan untuk review manual.",
    "text_too_long": "Jawaban melebihi panjang maksimum kolom.",
    "invalid_time": "Format jam tidak dikenali.",
    "invalid_date_or_timestamp": "Format tanggal tidak dikenali.",
    "invalid_stress": "Skor stres bukan 1-5 atau label form.",
    "smoking_status_count_conflict": "Status tidak merokok tetapi jumlah rokok > 0.",
    "smoker_count_missing": "Status merokok Ya tetapi jumlah rokok kosong.",
    "sbp_not_above_dbp": "Sistolik tidak lebih besar dari diastolik.",
}


def summarize_issues(quality):
    """Hitung isu per (source, field, code, action). Tidak membawa baris atau nilai mentah."""
    outcomes = quality.get("row_outcomes", {})
    raw_rows = {"profiles": outcomes.get("profiles", {}).get("raw", 0),
                "daily": outcomes.get("daily", {}).get("raw", 0)}
    counter = Counter((i.get("source", ""), i.get("field", ""), i.get("code", ""), i.get("action", ""))
                      for i in quality.get("issues", []))
    rows = []
    for (source, field, code, action), count in counter.items():
        total = raw_rows.get(source) or 0
        rows.append(dict(source=source, field=field, code=code, action=action, count=count,
                         share_of_raw_rows=round(count / total, 4) if total else None))
    rows.sort(key=lambda r: (-r["count"], r["source"], r["field"], r["code"]))
    return rows


def render_table(rows):
    if not rows:
        return "Tidak ada isu tercatat.\n"
    header = f"{'sumber':9} {'kolom':22} {'kode isu':32} {'jumlah':>7} {'porsi':>7}"
    lines = [header, "-" * len(header)]
    for r in rows:
        share = "-" if r["share_of_raw_rows"] is None else f"{r['share_of_raw_rows'] * 100:.1f}%"
        lines.append(f"{r['source']:9} {r['field']:22} {r['code']:32} {r['count']:>7} {share:>7}")
    lines.append("")
    lines.append("Arti kode isu:")
    for code in sorted({r["code"] for r in rows}):
        lines.append(f"  {code}: {HINTS.get(code, '(belum ada keterangan)')}")
    return "\n".join(lines) + "\n"


def write_report(rows, quality, target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    with open(target / "field_issue_summary.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(source_kind=quality.get("source_kind"), row_outcomes=quality.get("row_outcomes"),
                   issue_counts=quality.get("issue_counts"),
                   normalizations_by_field=quality.get("normalizations_by_field"), fields=rows)
    (target / "field_issue_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default=str(ROOT / "data/sample/Data_Responden_Sintetis.csv"))
    parser.add_argument("--daily", default=str(ROOT / "data/sample/Data_Harian_Sintetis.csv"))
    parser.add_argument("--source-kind", choices=["synthetic", "actual"], required=True)
    parser.add_argument("--report-dir", help="Tulis field_issue_summary.csv/json (agregat saja)")
    args = parser.parse_args(argv)
    sample = (ROOT / "data/sample").resolve()
    if args.source_kind == "actual":
        if any(Path(path).resolve().is_relative_to(sample) for path in (args.profile, args.daily)):
            parser.error("File data/sample adalah fixture sintetis. Gunakan --source-kind synthetic.")
        if args.report_dir and not Path(args.report_dir).resolve().is_relative_to((ROOT / "data/private").resolve()):
            parser.error("Laporan aktual harus disimpan pada data/private/ yang diabaikan Git.")
    try:
        profiles = pd.read_csv(args.profile, dtype=str, keep_default_na=False)
        daily = pd.read_csv(args.daily, dtype=str, keep_default_na=False)
        _, _, _, quality = prepare(profiles, daily, synthetic=args.source_kind == "synthetic")
    except DataQualityError as exc:
        quality = getattr(exc, "quality", None)
        if quality is None:
            print("Batch ditolak sebelum audit isu: " + str(exc), file=sys.stderr)
            return 2
        print("Peringatan: batch ditolak (" + str(exc) + "); ringkasan isu tetap ditampilkan.", file=sys.stderr)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        print("File sumber tidak dapat dibaca: " + type(exc).__name__, file=sys.stderr)
        return 2
    rows = summarize_issues(quality)
    sys.stdout.write(render_table(rows))
    if args.report_dir:
        write_report(rows, quality, args.report_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
