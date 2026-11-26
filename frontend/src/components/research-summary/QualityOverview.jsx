
import React from 'react';
import { whole } from '../../lib/api';

const fields = [
  { key: 'missing_sleep_hours', label: 'Durasi tidur' },
  { key: 'missing_sitting', label: 'Durasi duduk' },
  { key: 'missing_stress', label: 'Stres' },
  { key: 'missing_activity_minutes', label: 'Durasi aktivitas' },
  { key: 'missing_smoke_count', label: 'Jumlah merokok' }
];

const getCount = value => {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, number) : 0;
};

function getAxisStep(max) {
  if (max <= 0) return 1;

  const rough = max / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / magnitude;

  const nice = normalized <= 1 ? 1
    : normalized <= 2 ? 2
    : normalized <= 5 ? 5 : 10;

  return nice * magnitude;
}

function formatPercentage(value) {
  return `${value.toLocaleString('id-ID', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })}%`;
}

export default function QualityOverview({ quality }) {
  const q = quality || {};

  const daily = getCount(q.daily_records);
  const totalSessions = getCount(q.session_records);
  const validSessions = getCount(q.valid_sessions);
  const incompleteSessions = getCount(q.incomplete_sessions);
  const pendingSessions = getCount(q.pending_review_sessions);

  const chartData = fields.map(field => {
    const value = getCount(q[field.key]);

    return {
      label: field.label,
      value,
      percentage: daily > 0 ? value / daily * 100 : 0
    };
  }).sort((a, b) => b.value - a.value);

  const maxValue = Math.max(
    ...chartData.map(item => item.value),
    0
  );

  const step = getAxisStep(maxValue);
  const axisMax = maxValue > 0
    ? Math.ceil(maxValue / step) * step
    : 1;

  const ticks = Array.from(
    { length: Math.round(axisMax / step) + 1 },
    (_, index) => index * step
  );

  // Pengaturan ukuran horizontal bar chart
  const width = 900;
  const height = 290;

  const plotLeft = 190;
  const plotRight = 72;
  const plotTop = 20;
  const rowHeight = 40;
  const plotHeight = chartData.length * rowHeight;
  const plotBottom = plotTop + plotHeight;
  const plotWidth = width - plotLeft - plotRight;

  return (
    <section style={{
      background: '#fff',
      border: '1px solid #dbe4ef',
      borderRadius: 12,
      padding: 20,
      marginBottom: 16
    }}>

      <h3 style={{
        marginTop: 0,
        marginBottom: 6
      }}>
        Ringkasan Validitas dan Kelengkapan Data
      </h3>

      <p style={{
        color: '#64748b',
        fontSize: 13,
        marginTop: 0
      }}>
        Hasil pemeriksaan mengikuti filter data yang sedang digunakan.
      </p>

      {/* A. VALIDITAS SESI PENGUKURAN */}
      <div style={{ marginTop: 22 }}>

        <strong>A. Validitas Sesi Pengukuran</strong>

        <p style={{
          color: '#64748b',
          fontSize: 13,
          marginTop: 5,
          marginBottom: 14
        }}>
          Ringkasan kondisi sesi pengukuran berdasarkan filter aktif.
        </p>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: 12
        }}>

          {/* Sesi Valid */}
          <div style={{
            background: '#e6f3eb',
            borderRadius: 10,
            padding: 12
          }}>
            <div style={{
              color: '#087b3d',
              fontSize: 25,
              fontWeight: 600
            }}>
              {whole(validSessions)}
            </div>

            <div style={{
              color: '#52647a',
              fontSize: 13,
              marginTop: 3
            }}>
              Sesi valid
            </div>
          </div>

          {/* Incomplete */}
          <div style={{
            borderRadius: 10,
            padding: 12
          }}>
            <div style={{
              color: '#1e293b',
              fontSize: 25,
              fontWeight: 600
            }}>
              {whole(incompleteSessions)}
            </div>

            <div style={{
              color: '#64748b',
              fontSize: 13,
              marginTop: 3
            }}>
              Incomplete
            </div>
          </div>

          {/* Pending Review */}
          <div style={{
            borderRadius: 10,
            padding: 12
          }}>
            <div style={{
              color: '#1e293b',
              fontSize: 25,
              fontWeight: 600
            }}>
              {whole(pendingSessions)}
            </div>

            <div style={{
              color: '#64748b',
              fontSize: 13,
              marginTop: 3
            }}>
              Pending review
            </div>
          </div>

        </div>

        <p style={{
          color: '#64748b',
          fontSize: 12,
          marginTop: 12,
          marginBottom: 0
        }}>
          Total sesi: {whole(totalSessions)}.
          Status validitas mengikuti hasil pemeriksaan backend.
        </p>
      </div>

      {/* B. KELENGKAPAN CATATAN HARIAN */}
      <div style={{
        borderTop: '1px solid #e5eaf1',
        marginTop: 22,
        paddingTop: 18
      }}>

        <strong>B. Kelengkapan Catatan Harian</strong>

        <p style={{
          color: '#64748b',
          fontSize: 12,
          marginTop: 5,
          marginBottom: 8
        }}>
          Jumlah nilai kosong berdasarkan variabel.
          Total catatan harian: {whole(daily)}.
        </p>

        {daily === 0 ? (
          <p style={{
            color: '#64748b',
            fontSize: 13
          }}>
            Belum ada catatan harian pada filter ini.
          </p>
        ) : (
          <div style={{
            width: '100%',
            overflowX: 'auto'
          }}>

            <svg
              viewBox={`0 0 ${width} ${height}`}
              width="100%"
              height="auto"
              role="img"
              aria-label="Diagram batang horizontal jumlah nilai kosong berdasarkan variabel"
              style={{
                display: 'block',
                minWidth: 560,
                fontFamily: 'Arial, sans-serif'
              }}
            >

              {/* Garis grid dan sumbu horizontal */}
              {ticks.map(tick => {
                const x = plotLeft +
                  (tick / axisMax) * plotWidth;

                return (
                  <g key={tick}>
                    <line
                      x1={x}
                      y1={plotTop}
                      x2={x}
                      y2={plotBottom}
                      stroke="#e5eaf1"
                      strokeWidth="1"
                    />

                    <text
                      x={x}
                      y={plotBottom + 20}
                      textAnchor="middle"
                      fill="#64748b"
                      fontSize="12"
                    >
                      {whole(tick)}
                    </text>
                  </g>
                );
              })}

              {/* Batang horizontal dan label */}
              {chartData.map((item, index) => {
                const centerY =
                  plotTop + index * rowHeight + rowHeight / 2;

                const barWidth =
                  (item.value / axisMax) * plotWidth;

                const barEnd = plotLeft + barWidth;

                const valueLabel =
                  `${whole(item.value)} (${formatPercentage(item.percentage)})`;

                const labelAtEnd = barEnd + 8;
                const useEndAnchor =
                  labelAtEnd + 100 > width - 8;

                return (
                  <g key={item.label}>

                    {/* Label variabel */}
                    <text
                      x={plotLeft - 12}
                      y={centerY + 4}
                      textAnchor="end"
                      fill="#334155"
                      fontSize="13"
                    >
                      {item.label}
                    </text>

                    {/* Batang */}
                    <rect
                      x={plotLeft}
                      y={centerY - 14}
                      width={barWidth}
                      height={28}
                      fill="#24418F"
                      rx="1"
                    >
                      <title>{valueLabel}</title>
                    </rect>

                    {/* Jumlah dan persentase */}
                    <text
                      x={useEndAnchor ? barEnd - 8 : labelAtEnd}
                      y={centerY + 4}
                      textAnchor={useEndAnchor ? 'end' : 'start'}
                      fill="#1e293b"
                      fontSize="12"
                    >
                      {valueLabel}
                    </text>

                  </g>
                );
              })}

              {/* Judul sumbu X */}
              <text
                x={plotLeft + plotWidth / 2}
                y={height - 8}
                textAnchor="middle"
                fill="#475569"
                fontSize="13"
              >
                Jumlah nilai kosong
              </text>

            </svg>
          </div>
        )}
      </div>

      {/* CATATAN */}
      <div style={{
        borderTop: '1px solid #e5eaf1',
        paddingTop: 12,
        marginTop: 14,
        fontSize: 12,
        color: '#52647a',
        lineHeight: 1.6
      }}>
        Catatan: nilai kosong tidak selalu menunjukkan kesalahan
        pengisian. Khusus jumlah merokok, perlu diperiksa apakah
        responden memang tidak merokok sebelum menyimpulkan
        bahwa datanya hilang.
      </div>

    </section>
  );
}
