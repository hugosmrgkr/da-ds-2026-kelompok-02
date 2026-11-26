/* Token visualisasi bersama untuk grafik Plotly.
   Nilai warna sama persis dengan palet yang sudah dipakai halaman Dashboard,
   Analisis Faktor Risiko, dan Tren (components/Visuals.jsx). Warna UI
   (kartu, badge, teks) berada di dashboard-theme.css sebagai custom property. */

export const FONT_FAMILY = "'Segoe UI', Inter, sans-serif";

export const CHART = {
  blue: '#2789ed',    // warna utama dashboard
  navy: '#173b65',    // pasangan gelap warna utama (garis rerata, anotasi)
  teal: '#397e8b',    // sekunder
  amber: '#c58b36',   // sekunder (redup)
  violet: '#8664b1',
  rose: '#ca657f',
  sky: '#58a3bc',
  neutral: '#94a3b8', // kategori "Tidak diketahui" / "Lainnya"
  ink: '#13243d',     // teks utama di dalam grafik
  muted: '#586b85',   // teks pendukung di dalam grafik
  grid: '#e8edf4',
  tooltip: '#172954',
};

/* Urutan kategorikal dashboard; dipakai bila kategori tidak punya warna tetap. */
export const CATEGORICAL = [CHART.blue, CHART.teal, CHART.amber, CHART.violet, CHART.rose, CHART.sky];

/* Ukuran teks di dalam grafik (px). Satu skala untuk semua grafik halaman ini. */
export const CHART_TEXT = { tick: 12, label: 13, title: 13, value: 13, annotation: 12, tooltip: 13, legend: 13 };

/* Nada per jenis informasi: base = warna batang/area, dark = ujung gelap ramp peringkat. */
export const TONES = {
  blue: { base: CHART.blue, dark: CHART.navy },
  teal: { base: CHART.teal, dark: '#1f4a53' },
  amber: { base: CHART.amber, dark: '#7a5316' },
};

export const GENDER_COLORS = { 'Laki-laki': CHART.blue, 'Perempuan': CHART.rose };

/* Properti layout yang sama untuk setiap grafik di halaman Data Partisipan. */
export const baseFont = { family: FONT_FAMILY, size: CHART_TEXT.tick, color: CHART.muted };
export const baseHoverLabel = { bgcolor: CHART.tooltip, bordercolor: CHART.tooltip, font: { family: FONT_FAMILY, color: '#fff', size: CHART_TEXT.tooltip } };
export const axisTitle = text => ({ text, font: { size: CHART_TEXT.title, color: CHART.muted }, standoff: 10 });

/* Warna campuran linier antara dua heks (#rrggbb); t=0 -> a, t=1 -> b. */
export const mixColor = (a, b, t) => {
  const parse = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const [x, y] = [parse(a), parse(b)];
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0')).join('');
};
