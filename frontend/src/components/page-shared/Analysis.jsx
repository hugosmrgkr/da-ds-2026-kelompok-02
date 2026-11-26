import React from 'react';
import {Card} from '../Common';

export function Explainer({children}){return <p className="chart-explainer">{children}</p>}
/* Kartu Data Partisipan (class `participant-card`) memakai urutan anak tetap: judul, catatan sampel,
   area grafik (`.chart-body`), deskripsi, agar CSS subgrid dapat menyejajarkan tiap bagian.
   Kartu halaman lain mempertahankan struktur DOM semula tanpa pembungkus. */
export function ChartCard({title,sample,description,children,className=''}){
 const participant=className.split(/\s+/).includes('participant-card');
 return <Card title={title} className={('analysis-card '+className).trim()}>{sample&&<p className="sample-note">{sample}</p>}{participant?<div className="chart-body">{children}</div>:children}<Explainer>{description}</Explainer></Card>}
