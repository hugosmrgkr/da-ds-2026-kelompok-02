# Model Card — Rilis `synthetic-protocol-v1`

- **Status rilis:** `candidate` (`source_kind=synthetic`)
- **Run ID:** `6ef9947486d221ec0321`
- **Algoritma terpilih:** **Linear Regression**
- **Target & horizon:** `future_7d_mean_sbp` (histori 7 hari, horizon 7 hari, satuan mmHg)
- **Fitur berurutan (`cp3-history7-v1`):** past_7d_sbp, past_7d_dbp, past_7d_sbp_std, age, bmi, past_7d_activity, past_7d_sleep, past_7d_stress
- **Persetujuan target dosen:** `False` (Belum ada catatan persetujuan final dosen.)
- **Dilatih pada (UTC):** `2026-11-26T02:13:57.704824+00:00`
- **Training data fingerprint:** `51394dad1ec8fa22d6ff2ed5503319625e956b366fe8ed87b92e8e0824d32427`

## Ringkasan Evaluasi (synthetic_protocol_dry_run)

Validasi memilih **Linear Regression** berdasarkan `RMSE validasi terkecil di antara model terlatih; tie dipecah MAE lalu nama`. Mengalahkan baseline naif pada validasi: **False**.

| Metode | Jenis | MAE Val | RMSE Val | MAE Test | RMSE Test | R² Test |
|---|---|---:|---:|---:|---:|---:|
| Naive 7-day mean | baseline naif | 1.908 | 2.377 | 1.934 | 2.235 | 0.850 |
| Linear Regression | terlatih | 2.180 | 2.759 | 2.575 | 3.114 | 0.709 |
| Random Forest | terlatih | 3.178 | 4.750 | 2.959 | 3.441 | 0.645 |
| Hist Gradient Boosting | terlatih | 3.353 | 4.600 | 3.693 | 4.832 | 0.300 |

## Keterbatasan & Batas Penggunaan

- Kalender training belum cukup panjang untuk inner CV kronologis murni; inner validation menggunakan GroupKFold berbasis responden (kalender fit/val dapat beririsan).
- Ukuran test utama kecil (7 origin dari 7 ID); metrik test bersifat tidak stabil dan bukan bukti generalisasi klinis.
- Dataset berstatus DATA SINTETIS / SIMULASI; tidak boleh digunakan untuk klaim penelitian aktual.
