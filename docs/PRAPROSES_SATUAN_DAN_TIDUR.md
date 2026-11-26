# Praproses satuan menit, tidur berunit eksplisit, dan ringkasan isu per kolom

Catatan perubahan kecil pada praproses. Semua contoh jawaban di tes adalah **fixture sintetis**;
belum ada ekspor aktual yang diperiksa, jadi dokumen ini tidak menyatakan data aktual tervalidasi.

## 1. Satuan menit (kolom 17 dan 18)

`activity_minutes` dan `heavy_minutes` kini menerima satuan jam yang ditulis **eksplisit** dan
mengonversinya ke menit bulat. Berlaku di jalur sintetis maupun aktual.

| Jawaban | Hasil |
|---|---|
| `30`, `30 menit`, `90 mnt`, `90 min` | 30, 30, 90, 90 |
| `1 jam`, `1,5 jam`, `0,5 jam` | 60, 90, 30 |
| `1 jam 30 menit`, `1 jam 30`, `1jam30` | 90 |
| `1.5`, `1,5` (tanpa satuan, bukan bilangan bulat) | ditolak, `invalid_number_or_unit` |
| `25 jam`, `2 jam 90 menit`, `-5 menit`, `0,01 jam` | ditolak (di luar 0–1440 menit, menit ≥ 60, negatif, bukan menit bulat) |

Angka tanpa satuan tetap dianggap menit sesuai bunyi pertanyaan. Konversi tercatat di
`normalizations_by_field`, jadi tidak terjadi diam-diam. Satuan lain (`cm`, `kg`, `tahun`, `hari`)
tidak berubah.

## 2. Tidur data aktual berunit eksplisit (di belakang flag, default MATI)

Keputusan arti tidur aktual belum ada (lihat `DATA_DICTIONARY.md`), sehingga perilaku lama
dipertahankan: semua jawaban tidur aktual = NA + `sleep_semantics_unconfirmed`.

Bila `TOBA_SLEEP_EXPLICIT_UNITS=1` diset, hanya bentuk **berunit eksplisit** yang dikonversi ke jam desimal:

| Jawaban | Hasil (jam) |
|---|---|
| `7 jam`, `7,5 jam` | 7.0, 7.5 |
| `7 jam 30 menit`, `7 jam 30` | 7.5 |
| `420 menit`, `450 mnt` | 7.0, 7.5 |
| `19 jam`, `7 jam 75 menit`, `1200 menit` | NA, `invalid_sleep_duration` |
| `7`, `420`, `06:30`, `0.3` | NA, tetap `sleep_semantics_unconfirmed` (ambigu, tidak ditebak) |

Jalur sintetis tidak terpengaruh flag (`06:30` → 6,5 jam seperti sebelumnya).

**Keputusan yang masih harus diambil tim/dosen sebelum flag dinyalakan:**
1. Apakah `HH:MM` adalah durasi atau jam tidur.
2. Apakah angka telanjang pada pertanyaan "Berapa jam Anda tidur" boleh dianggap jam.
3. Catat keputusan beserta tanggal dan pemutusnya di sini. Jangan menyalakan flag di lingkungan
   yang dipakai untuk melatih atau menyajikan model sebelum itu.

Menyalakan flag mengubah isi `sleep_hours` dan karena itu fitur `past_7d_sleep`. Model yang
sudah dilatih dengan sleep = NA tidak otomatis kompatibel; koordinasikan dengan pemilik model.

## 3. Ringkasan isu per kolom (`etl/audit_field_issues.py`)

Read-only, tidak menyentuh database. Menampilkan jumlah isu per (sumber, kolom, kode) beserta
porsinya terhadap jumlah baris mentah. Tidak ada nomor baris maupun nilai mentah pada keluarannya.

```powershell
python -m etl.audit_field_issues --source-kind synthetic
python -m etl.audit_field_issues --source-kind actual `
  --profile data/private/incoming/form_awal.csv `
  --daily data/private/incoming/catatan_harian.csv `
  --report-dir data/private/readiness/batch-YYYYMMDD
```

Pengaman sama seperti `etl.import_data`: file `data/sample` tidak boleh dilabel aktual, dan laporan
aktual hanya boleh ditulis di `data/private/`. Header yang tidak cocok menghentikan proses (kode keluar 2).
Keluaran `--report-dir`: `field_issue_summary.csv` dan `field_issue_summary.json`.

Berguna untuk daftar "kuesioner yang salah": kolom dengan porsi `invalid_category` atau
`invalid_number_or_unit` tinggi menunjukkan opsi atau satuan di form yang tidak cocok dengan skema.

## Yang sengaja TIDAK diubah

- `pipeline.py` (hash-nya dicatat di manifest baseline), kontrak header, dan semua jalur sintetis.
- Alias tanda hubung `sitting`, alias opsi pendek, `caffeine_ml`, dan cek silang aktivitas:
  menunggu ekspor aktual atau keputusan form.

## Cara menjalankan tes

```powershell
python -m pytest backend/tests/test_minute_unit_normalization.py backend/tests/test_sleep_explicit_units.py backend/tests/test_audit_field_issues.py -q -p no:cacheprovider
python -m pytest backend/tests -q -p no:cacheprovider
```
