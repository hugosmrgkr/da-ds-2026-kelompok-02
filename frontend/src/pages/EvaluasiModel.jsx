/**
 * EvaluasiModel.jsx — Halaman Evaluasi Model
 *
 * Menampilkan metrik evaluasi model prediksi SBP (future_7d_mean_sbp) dari
 * artefak eksperimen yang tersimpan. Tidak menghitung ulang metrik dari filter
 * aktif dan tidak mengklaim validitas klinis atau performa pada data aktual.
 *
 * Direfactor oleh Nahesson (feat/validated-model-release):
 *   - Pisah menjadi sub-komponen yang terbaca dan dapat diuji sendiri
 *   - Tambah panel StatusSumber: banner sintetis/aktual yang lebih informatif
 *   - Tambah panel LimaErrorTerbesar: 5 origin dengan absolute error terbesar
 *   - Tambah panel RingkasanBias: bias sistematis (signed error) per model
 *   - Pertahankan seluruh logika dan data eksperimen yang sudah ada
 */

import React from 'react';
import { Target, AlertTriangle, CheckCircle } from 'lucide-react';
import { Card, Notice, MiniTable, Loading } from '../components/Common';
import {
  ModelComparison,
  ActualVsPredicted,
  ResidualPlot,
  ValidationVsTest,
  ResidualHistogram,
} from '../components/Visuals';
import { fmt, whole } from '../lib/api';
import { ChartCard, Explainer } from '../components/page-shared/Analysis';

// ─── Helper ────────────────────────────────────────────────────────────────

/** Konversi nama model ke kunci kolom pada actual_vs_predicted */
const columnKey = (name) => name.toLowerCase().replace(/[ -]/g, '_');

/** Format angka atau tampilkan "Tidak tersedia" */
const nf = (value, digits = 3) =>
  value == null ? 'Tidak tersedia' : fmt(value, digits);

// ─── Sub-komponen: Status Sumber Data ──────────────────────────────────────

/**
 * StatusSumber — banner yang menjelaskan status data secara eksplisit.
 * Membedakan sintetis (eksperimen, bukan penelitian), aktual (belum aktif),
 * dan kondisi artefak tidak tersedia.
 */
function StatusSumber({ sourceKind, targetApproved }) {
  if (sourceKind === 'synthetic') {
    return (
      <Notice tone="warning">
        <strong>DATA SINTETIS / SIMULASI.</strong> Metrik dibaca dari artefak
        eksperimen yang tersimpan, bukan dihitung ulang dari filter aktif.
        Hasil ini tidak membuktikan performa model pada responden asli dan
        bukan bukti penelitian yang telah divalidasi.
        {!targetApproved && (
          <>
            {' '}
            Target <code>future_7d_mean_sbp</code> belum disetujui dosen;
            hasil ini tidak boleh diklaim sebagai evaluasi final penelitian.
          </>
        )}
      </Notice>
    );
  }

  if (sourceKind === 'actual') {
    return (
      <Notice tone="warning">
        <strong>Sumber aktual terdeteksi.</strong> Evaluasi model pada data
        aktual belum diaktifkan. Hasil yang ditampilkan masih berasal dari
        artefak eksperimen sintetis sampai rilis model aktual tersedia dan
        diverifikasi.
      </Notice>
    );
  }

  return (
    <Notice tone="warning">
      Sumber data belum diketahui atau warehouse kosong. Metrik eksperimen
      sintetis ditampilkan sebagai referensi teknis.
    </Notice>
  );
}

// ─── Sub-komponen: Ringkasan Metrik Utama ──────────────────────────────────

/** MetricsOverview — grid ringkasan split dan ukuran dataset */
function MetricsOverview({ data }) {
  const items = [
    ['Target regresi', 'Rerata SBP ' + (data.horizon_days ?? 7) + ' hari berikutnya (mmHg)'],
    ['Responden train / test', `${whole(data.respondents_train?.length)} / ${whole(data.respondents_test?.length)} ID`],
    ['Window train / test', `${whole(data.rows_training)} / ${whole(data.rows_test)}`],
    ['Cutoff training', data.cutoff ?? '—'],
    ['Sumber data', data.dataset ?? '—'],
    ['Strategi pemisahan', 'ID terpisah + batas waktu + target uji tidak overlap'],
  ];

  return (
    <div className="metrics-overview">
      {items.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <b>{value}</b>
        </div>
      ))}
    </div>
  );
}

// ─── Sub-komponen: Peringatan Dataset Kecil ────────────────────────────────

/** PeringatanSampelKecil — tampilkan bila ukuran test sangat kecil */
function PeringatanSampelKecil({ rowsTest }) {
  if (!rowsTest || rowsTest > 15) return null;
  return (
    <Notice tone="warning">
      Ukuran test hanya <strong>{whole(rowsTest)} origin</strong>. Metrik
      sangat tidak stabil — perbedaan kecil antar-model tidak mencerminkan
      performa yang sesungguhnya. Baca selalu bersama jumlah ID dan split.
    </Notice>
  );
}

// ─── Sub-komponen: Ringkasan Bias ──────────────────────────────────────────

/**
 * RingkasanBias — tabel bias sistematis (signed error = prediksi - aktual)
 * per model pada set test.
 *
 * Bias positif → model rata-rata memprediksi terlalu tinggi.
 * Bias negatif → model rata-rata memprediksi terlalu rendah.
 *
 * Dihitung dari actual_vs_predicted pada artefak; bukan dari filter aktif.
 */
function RingkasanBias({ rows, modelNames }) {
  if (!rows || rows.length === 0 || !modelNames || modelNames.length === 0) {
    return null;
  }

  const biasRows = modelNames.map((name) => {
    const key = columnKey(name);
    const valid = rows.filter(
      (r) => Number.isFinite(r.actual) && Number.isFinite(r[key])
    );
    if (valid.length === 0) {
      return { model: name, n: 0, bias: null, under: null, over: null };
    }
    const errors = valid.map((r) => r[key] - r.actual); // signed: prediksi - aktual
    const bias = errors.reduce((s, e) => s + e, 0) / errors.length;
    const under = errors.filter((e) => e < 0).length;
    const over = errors.filter((e) => e > 0).length;
    return {
      model: name,
      n: whole(valid.length),
      bias: fmt(bias, 2),
      under: whole(under),
      over: whole(over),
    };
  });

  return (
    <Card title="Ringkasan bias prediksi pada set test">
      <MiniTable
        rows={biasRows}
        columns={[
          ['model', 'Model'],
          ['n', 'Origin test'],
          ['bias', 'Bias rata-rata (mmHg)'],
          ['under', 'Prediksi terlalu rendah'],
          ['over', 'Prediksi terlalu tinggi'],
        ]}
      />
      <Explainer>
        Bias = rata-rata (prediksi − aktual) dalam mmHg. Positif berarti model
        rata-rata memprediksi terlalu tinggi; negatif berarti terlalu rendah.
        Dengan sampel test yang sangat kecil, arah bias ini tidak dapat
        digeneralisasi ke populasi. Ini adalah ringkasan deskriptif, bukan
        uji signifikansi.
      </Explainer>
    </Card>
  );
}

// ─── Sub-komponen: 5 Error Terbesar ────────────────────────────────────────

/**
 * LimaErrorTerbesar — tabel 5 origin dengan absolute error terbesar
 * untuk model yang terpilih, dibandingkan dengan baseline naif.
 *
 * Berguna untuk memahami kondisi terburuk model dan apakah baseline naif
 * lebih baik pada kasus-kasus ekstrem tersebut.
 */
function LimaErrorTerbesar({ rows, selectedModel }) {
  if (!rows || rows.length === 0 || !selectedModel) return null;

  const selectedKey = columnKey(selectedModel);
  const naifKey = columnKey('Naive 7-day mean');

  const withError = rows
    .filter(
      (r) =>
        Number.isFinite(r.actual) &&
        Number.isFinite(r[selectedKey])
    )
    .map((r) => ({
      respondent_id: r.respondent_id,
      asof_date: r.asof_date ?? '—',
      aktual: fmt(r.actual, 1),
      prediksi: fmt(r[selectedKey], 1),
      abs_error: fmt(Math.abs(r[selectedKey] - r.actual), 2),
      _abs: Math.abs(r[selectedKey] - r.actual),
      naive_mae:
        Number.isFinite(r[naifKey])
          ? fmt(Math.abs(r[naifKey] - r.actual), 2)
          : '—',
      arah: r[selectedKey] > r.actual ? 'Terlalu tinggi' : 'Terlalu rendah',
    }))
    .sort((a, b) => b._abs - a._abs)
    .slice(0, 5);

  if (withError.length === 0) return null;

  return (
    <Card title={`5 Error Terbesar — ${selectedModel} (test)`}>
      <MiniTable
        rows={withError}
        columns={[
          ['respondent_id', 'ID'],
          ['asof_date', 'Origin'],
          ['aktual', 'Aktual (mmHg)'],
          ['prediksi', 'Prediksi (mmHg)'],
          ['abs_error', 'Error absolut (mmHg)'],
          ['naive_mae', 'Error baseline naif (mmHg)'],
          ['arah', 'Arah error'],
        ]}
      />
      <Explainer>
        Target pada setiap baris adalah rerata SBP 7 hari setelah origin,
        bukan satu pembacaan tekanan darah. Error besar tidak berarti model
        gagal secara umum; sampel test sangat kecil sehingga setiap baris
        memengaruhi metrik agregat secara signifikan. Bandingkan kolom
        "Error baseline naif" untuk melihat apakah prediksi naif lebih baik
        pada kasus terburuk ini.
      </Explainer>
    </Card>
  );
}

// ─── Sub-komponen: Detail Eksperimen ───────────────────────────────────────

/** DetailEksperimen — panel keterbatasan dan metadata eksperimen */
function DetailEksperimen({ data }) {
  return (
    <Card title="Detail eksperimen dan keterbatasan">
      <p>
        <b>Split:</b> {data.split ?? '—'}.
      </p>
      <p>
        <b>Run artefak:</b> {data.run_id ?? '—'}; seed {data.seed ?? '—'};
        validasi {data.validation_folds ?? '—'} fold.
      </p>
      <p>
        <b>Fitur:</b>{' '}
        {(data.features ?? []).join(', ') || 'Tidak tersedia'}.
      </p>
      <p>
        <b>Keterbatasan:</b> {data.limitation ?? '—'}
      </p>
      <Explainer>
        Hasil tidak membuktikan generalisasi atau validitas klinis. Langkah
        lanjut menunggu persetujuan target oleh dosen, validasi data aktual,
        dan paket rilis model terverifikasi (models/releases/).
      </Explainer>
    </Card>
  );
}

// ─── Sub-komponen: Fallback Baseline (CP3 lama) ────────────────────────────

/**
 * EvaluasiBaseline — tampilan alternatif bila endpoint /api/model/comparison
 * belum tersedia (hanya ada baseline dua-metode CP3).
 */
function EvaluasiBaseline({ model, modelLoading }) {
  if (modelLoading) return <Loading />;
  if (!model?.available) {
    return (
      <Notice tone="warning">
        {model?.message ||
          'Hasil baseline belum tersedia atau dataset aktif bukan sintetis. Tidak ada metrik contoh.'}
      </Notice>
    );
  }

  const predictions = model.actual_vs_predicted || [];
  const scores = model.scores || [];

  return (
    <>
      <StatusSumber sourceKind="synthetic" targetApproved={false} />

      <div className="metrics-overview">
        <div>
          <span>Target regresi</span>
          <b>Rerata SBP 7 hari berikutnya (mmHg)</b>
        </div>
        <div>
          <span>Baris training</span>
          <b>{whole(model.rows_training)}</b>
        </div>
        <div>
          <span>Baris test</span>
          <b>{whole(model.rows_test)}</b>
        </div>
        <div>
          <span>Pemisahan data</span>
          <b>ID terpisah + batas waktu + target uji tidak overlap</b>
        </div>
      </div>

      <PeringatanSampelKecil rowsTest={model.rows_test} />

      <div className="page-grid two">
        <ChartCard
          title="Perbandingan MAE metode awal"
          sample={`${whole(model.rows_test)} baris test pada artefak`}
          description="MAE adalah rata-rata besar kesalahan absolut dalam mmHg; lebih kecil lebih baik. Ini bukan akurasi persen."
        >
          <ModelComparison model={model} />
        </ChartCard>

        <Card title="Tabel metrik eksperimen">
          <MiniTable
            rows={scores.map((row) => ({
              ...row,
              mae: fmt(row.mae, 3),
              rmse: fmt(row.rmse, 3),
              r2: fmt(row.r2, 3),
            }))}
            columns={[
              ['model', 'Metode'],
              ['mae', 'MAE (mmHg)'],
              ['rmse', 'RMSE (mmHg)'],
              ['r2', 'R²'],
            ]}
          />
          <Explainer>
            RMSE memberi bobot lebih besar pada error besar. R² membandingkan
            variasi yang dijelaskan terhadap prediksi rerata; dapat negatif
            dan bukan persentase akurasi. Baseline naif dibandingkan dengan
            Linear Regression.
          </Explainer>
        </Card>

        <ChartCard
          title="Aktual vs prediksi Linear Regression"
          sample={`${whole(predictions.length)} pasangan yang tersimpan pada artefak`}
          description="Titik dekat garis prediksi = aktual menunjukkan error lebih kecil. Rentang garis dihitung dari pasangan hasil, bukan batas tekanan darah buatan."
        >
          <ActualVsPredicted model={model} />
        </ChartCard>

        <ChartCard
          title="Residual prediksi Linear Regression"
          sample={`${whole(predictions.length)} pasangan pada artefak`}
          description="Residual = aktual - prediksi dalam mmHg. Nilai positif berarti prediksi terlalu rendah; pola atau sebaran lebar perlu ditinjau pada eksperimen lanjutan."
        >
          <ResidualPlot model={model} />
        </ChartCard>
      </div>

      <Card title="Batas eksperimen dan rencana setelah CP3">
        <p>
          <b>Split:</b> {model.split}. ID train dan test dipisahkan.
        </p>
        {model.run_id && (
          <p>
            <b>Run artefak:</b> {model.run_id}; cutoff {model.cutoff}. Target
            belum disetujui dosen.
          </p>
        )}
        {model.warehouse_batch_match !== true && (
          <Notice tone="warning">
            Fingerprint batch warehouse belum cocok atau belum tersedia. Metrik
            ini tetap milik eksperimen tersimpan, bukan evaluasi ulang data
            aktif.
          </Notice>
        )}
        <p>
          <b>Fitur tersimpan:</b>{' '}
          {(model.features ?? []).join(', ') || 'Tidak tersedia'}.
        </p>
        <p>
          <b>Keterbatasan:</b> {model.limitation}
        </p>
        <Explainer>
          Setelah definisi target dan kelayakan data aktual disetujui: tambah
          algoritma, tuning, validasi dan error analysis. Tahap ini tidak
          melatih ulang model atau mengklaim model terbaik final.
        </Explainer>
      </Card>
    </>
  );
}

// ─── Komponen Utama ────────────────────────────────────────────────────────

/**
 * Evaluasi — halaman utama Evaluasi Model.
 *
 * Menerima dua sumber data:
 *   - comparison: hasil /api/model/comparison (tiga algoritma + baseline, P2+)
 *   - model: hasil /api/model/baseline (dua metode CP3, fallback)
 *
 * Bila comparison tersedia, tampilkan panel perbandingan lengkap termasuk
 * panel baru (bias + 5 error terbesar). Bila tidak, fallback ke EvaluasiBaseline.
 */
export default function Evaluasi({ model, modelLoading, comparison, comparisonLoading }) {
  if (comparisonLoading) return <Loading />;

  // ── Fallback ke tampilan baseline CP3 bila comparison belum tersedia ──
  if (!comparison?.available) {
    return <EvaluasiBaseline model={model} modelLoading={modelLoading} />;
  }

  // ── Tampilan utama: perbandingan tiga algoritma ──
  const rows = comparison.comparison ?? [];
  const selected = comparison.selected_model;
  const selectedKey = columnKey(selected);
  const predictions = comparison.actual_vs_predicted ?? [];

  // Daftar nama model (urutan: baseline naif pertama)
  const modelNames = rows.map((r) => r.model);

  // Error per responden: MAE model terpilih vs baseline naif, per ID
  const naifModel = rows[0]?.model ?? 'Naive 7-day mean';
  const naifKey = columnKey(naifModel);
  const byId = Object.values(
    predictions.reduce((acc, row) => {
      const item =
        acc[row.respondent_id] ||
        (acc[row.respondent_id] = {
          respondent_id: row.respondent_id,
          n: 0,
          absSelected: 0,
          absNaif: 0,
        });
      item.n++;
      if (Number.isFinite(row.actual) && Number.isFinite(row[selectedKey]))
        item.absSelected += Math.abs(row.actual - row[selectedKey]);
      if (Number.isFinite(row.actual) && Number.isFinite(row[naifKey]))
        item.absNaif += Math.abs(row.actual - row[naifKey]);
      return acc;
    }, {})
  ).map((item) => ({
    respondent_id: item.respondent_id,
    n: whole(item.n),
    mae: fmt(item.absSelected / item.n, 2),
    naive: fmt(item.absNaif / item.n, 2),
  }));

  return (
    <>
      {/* Banner status sumber */}
      <StatusSumber
        sourceKind={comparison.dataset === 'fixture' ? 'synthetic' : comparison.source_kind}
        targetApproved={comparison.target_approved}
      />

      {/* Peringatan dari artefak (mis. ukuran test kecil) */}
      {(comparison.warnings ?? []).map((w) => (
        <Notice key={w} tone="warning">
          {w}
        </Notice>
      ))}

      {/* Ringkasan dimensi eksperimen */}
      <MetricsOverview data={comparison} />

      {/* Peringatan sampel kecil */}
      <PeringatanSampelKecil rowsTest={comparison.rows_test} />

      {/* Grafik RMSE dan MAE: validasi vs test */}
      <div className="page-grid two">
        <ChartCard
          title="RMSE: validasi vs test"
          sample={`${whole(rows[0]?.validation?.n)} window validasi; ${whole(rows[0]?.test?.n)} origin test`}
          description="RMSE dalam mmHg (lebih kecil lebih baik), memberi bobot lebih pada error besar. Validasi dipakai memilih model; test dilihat sekali setelah pemilihan dan tidak untuk memilih ulang."
        >
          <ValidationVsTest comparison={comparison} metric="rmse" />
        </ChartCard>

        <ChartCard
          title="MAE: validasi vs test"
          sample={`${whole(rows[0]?.validation?.n)} window validasi; ${whole(rows[0]?.test?.n)} origin test`}
          description="MAE adalah rata-rata besar kesalahan absolut dalam mmHg. Ini bukan akurasi persen."
        >
          <ValidationVsTest comparison={comparison} metric="mae" />
        </ChartCard>
      </div>

      {/* Tabel metrik lengkap semua algoritma */}
      <Card title="Tabel metrik perbandingan semua algoritma">
        <MiniTable
          rows={rows.map((row) => ({
            model:
              row.model +
              (row.model === selected ? ' ✓ terpilih' : ''),
            kind: row.kind,
            vmae: nf(row.validation?.mae),
            vrmse: nf(row.validation?.rmse),
            vr2: nf(row.validation?.r2),
            tmae: nf(row.test?.mae),
            trmse: nf(row.test?.rmse),
            tr2: nf(row.test?.r2),
          }))}
          columns={[
            ['model', 'Metode'],
            ['kind', 'Jenis'],
            ['vmae', 'MAE validasi (mmHg)'],
            ['vrmse', 'RMSE validasi (mmHg)'],
            ['vr2', 'R² validasi'],
            ['tmae', 'MAE test (mmHg)'],
            ['trmse', 'RMSE test (mmHg)'],
            ['tr2', 'R² test'],
          ]}
        />
        <Explainer>
          R² membandingkan variasi yang dijelaskan terhadap prediksi rerata;
          dapat negatif dan bukan persentase akurasi. Model terpilih
          ditentukan aturan tetap:{' '}
          <em>{comparison.selection?.rule ?? '—'}</em>. Mengalahkan baseline
          naif pada validasi:{' '}
          <b>
            {comparison.selection?.beats_naive_on_validation ? 'ya' : 'tidak'}
          </b>
          .
        </Explainer>
      </Card>

      {/* Panel baru: Ringkasan Bias */}
      <RingkasanBias rows={predictions} modelNames={modelNames} />

      {/* Panel baru: 5 Error Terbesar */}
      <LimaErrorTerbesar rows={predictions} selectedModel={selected} />

      {/* Grafik aktual vs prediksi dan residual */}
      <div className="page-grid two">
        <ChartCard
          title={`Aktual vs prediksi — ${selected}`}
          sample={`${whole(predictions.length)} origin uji`}
          description="Titik dekat garis prediksi = aktual berarti error kecil. Sampel uji sangat kecil sehingga pola tidak stabil."
        >
          <ActualVsPredicted
            model={comparison}
            field={selectedKey}
            label={selected}
          />
        </ChartCard>

        <ChartCard
          title={`Residual — ${selected}`}
          sample={`${whole(predictions.length)} origin uji`}
          description="Residual = aktual - prediksi (mmHg). Positif berarti prediksi terlalu rendah."
        >
          <ResidualPlot model={comparison} field={selectedKey} />
        </ChartCard>

        <ChartCard
          title="Distribusi error (histogram residual)"
          sample={`${whole(predictions.length)} origin uji`}
          description="Histogram residual model terpilih. Dengan sampel kecil, bentuk distribusi tidak boleh ditafsirkan sebagai sifat model secara umum."
        >
          <ResidualHistogram model={comparison} field={selectedKey} />
        </ChartCard>

        <Card title="Error per responden (test)">
          <MiniTable
            rows={byId}
            columns={[
              ['respondent_id', 'ID'],
              ['n', 'Origin uji'],
              ['mae', 'MAE model terpilih (mmHg)'],
              ['naive', 'MAE baseline naif (mmHg)'],
            ]}
          />
          <Explainer>
            Analisis per kelompok memakai ID karena atribut lain terlalu
            sedikit pada test. Satu atau dua origin per ID tidak cukup untuk
            kesimpulan per kelompok.
          </Explainer>
        </Card>
      </div>

      {/* Detail dan keterbatasan eksperimen */}
      <DetailEksperimen data={comparison} />
    </>
  );
}
