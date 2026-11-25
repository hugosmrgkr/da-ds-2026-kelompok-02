# Ringkasan Hasil Evaluasi Model

- **Run ID:** `e34327cd28c78f592900`
- **Target:** future_7d_mean_sbp
- **Data sintetis:** `True`
- **Dipromosikan ke serving:** `False`

## Metrik evaluasi

| Model | Tahap | Split | MAE | RMSE | R² | n |
| --- | --- | --- | --- | --- | --- | --- |
| Naive 7-day mean | reference | historical_test | 1.9337 | 2.2347 | 0.8503 | 7 |
| Naive 7-day mean | reference | validation | 1.9077 | 2.3765 | 0.8646 | 60 |
| Linear Regression | original | historical_test | 2.5755 | 3.1140 | 0.7093 | 7 |
| Linear Regression | selected_configuration | historical_test | 2.5755 | 3.1140 | 0.7093 | 7 |
| Linear Regression | selected_configuration | validation | 2.1805 | 2.7588 | 0.8176 | 60 |
| Random Forest | original | historical_test | 2.9593 | 3.4407 | 0.6451 | 7 |
| Random Forest | selected_configuration | historical_test | 2.6820 | 3.2363 | 0.6861 | 7 |
| Random Forest | selected_configuration | validation | 2.9117 | 4.3247 | 0.5517 | 60 |
| Hist Gradient Boosting | original | historical_test | 3.6934 | 4.8316 | 0.3003 | 7 |
| Hist Gradient Boosting | selected_configuration | historical_test | 3.6305 | 4.6512 | 0.3515 | 7 |
| Hist Gradient Boosting | selected_configuration | validation | 3.3177 | 4.5104 | 0.5124 | 60 |

## Batasan interpretasi

- DATA SINTETIS / SIMULASI. Inner GroupKFold memisahkan ID, tetapi kalender fit/validasi dapat beririsan dan target window training berkorelasi. Ini bukan validasi forecasting kronologis penuh. Test CP3 sudah pernah diperiksa; evaluasi ulang bersifat historis, bukan holdout baru. Sampel kecil; bukan validasi klinis atau hasil data aktual. Persetujuan target diasumsikan untuk tugas ini; bukti akademik belum direkam dalam artefak aktif.
- Data yang digunakan bersifat sintetis/simulasi, bukan data operasional nyata.
- Hasil ini bukan validasi klinis dan tidak digunakan untuk diagnosis medis.
- Hasil tuning Week 10 tidak otomatis berarti model dipromosikan ke model serving.

## Catatan penggunaan

Angka pada tabel diekspor langsung dari `evaluation.json`. File ini merupakan ringkasan bukti eksperimen, bukan klaim bahwa model terbaik mengungguli baseline atau siap digunakan pada layanan produksi.
