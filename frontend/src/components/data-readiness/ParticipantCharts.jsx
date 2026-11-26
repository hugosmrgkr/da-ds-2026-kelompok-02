import React from 'react';
import {CalendarDays,MapPin,Scale,UsersRound} from 'lucide-react';
import {PlotlyChart} from '../Common';
import {fmt,whole} from '../../lib/api';
import {CHART,CHART_TEXT,TONES,GENDER_COLORS,CATEGORICAL,FONT_FAMILY,baseHoverLabel,axisTitle,mixColor} from '../../lib/chartTheme';

/* Warna grafik berasal dari lib/chartTheme.js (palet yang sama dengan Dashboard,
   Analisis Faktor Risiko, dan Tren). Nada dipilih per jenis informasi:
   biru = atribut responden, teal = lokasi dan BMI, amber = pekerjaan. */
export const TONE=TONES;

/* Tinggi area grafik (px). Setiap baris kartu memakai tinggi yang sama agar
   judul, grafik, dan deskripsi sejajar; batang tidak diperkecil demi itu. */
export const PLOT_MIN=340;
const BAR_SLOT=34,BAR_CHROME=96,BAR_MAX=34,SLOT_MAX=56;
const pick=event=>event?.points?.[0];

/* Jumlah baris kategori yang akan digambar (termasuk baris "Lainnya"). */
export const rankSlots=(rows=[],limit=12)=>{const n=rows.filter(r=>Number.isFinite(r.n)).length;return n>limit?limit+1:n};
/* Tinggi grafik batang yang cukup untuk jumlah baris terbanyak pada satu baris kartu. */
export const rankHeight=(...slots)=>Math.max(PLOT_MIN,Math.max(0,...slots)*BAR_SLOT+BAR_CHROME);

/* Batang horizontal berurutan dari terbanyak; warna memudar mengikuti peringkat. */
export function RankBars({rows=[],tone='blue',unit='responden',onSelect,limit=12,height}){
 const t=TONE[tone]||TONE.blue;
 const sorted=[...rows].filter(r=>Number.isFinite(r.n)).sort((a,b)=>b.n-a.n);
 const shown=sorted.slice(0,limit),hidden=sorted.slice(limit).reduce((s,r)=>s+r.n,0);
 const data=hidden>0?[...shown,{category:`Lainnya (${sorted.length-limit} kategori)`,n:hidden,other:true}]:shown;
 const colors=data.map((r,i)=>r.other||r.category==='Tidak diketahui'?CHART.neutral:mixColor(t.dark,t.base,shown.length>1?Math.min(1,i/(shown.length-1))*.85:0));
 const h=height||rankHeight(data.length);
 /* Bila tinggi bersama lebih besar dari kebutuhan, batang dikelompokkan di tengah dengan jarak
    antarbaris dibatasi (SLOT_MAX), bukan direntangkan; tebal batang tetap seragam di semua grafik. */
 const inner=h-BAR_CHROME+28,n=Math.max(1,data.length);
 const eff=Math.max(n,inner/SLOT_MAX),pad=(eff-n)/2;
 const bargap=Math.min(.82,Math.max(.28,1-BAR_MAX/(inner/eff)));
 return <PlotlyChart height={h}
  data={[{type:'bar',orientation:'h',x:data.map(r=>r.n),y:data.map(r=>r.category),marker:{color:colors,line:{color:'white',width:1}},
   text:data.map(r=>whole(r.n)),textposition:'outside',cliponaxis:false,textfont:{color:CHART.ink,size:CHART_TEXT.value,family:FONT_FAMILY},
   hovertemplate:'<b>%{y}</b><br>%{x} '+unit+'<extra></extra>'}]}
  onClick={onSelect?e=>{const p=pick(e);if(p?.y&&p.y!=='Tidak diketahui'&&!String(p.y).startsWith('Lainnya'))onSelect(p.y)}:undefined}
  layout={{margin:{l:16,r:52,t:12,b:60},showlegend:false,bargap,hoverlabel:baseHoverLabel,
   font:{family:FONT_FAMILY,size:CHART_TEXT.tick,color:CHART.muted},
   xaxis:{title:axisTitle(`Jumlah ${unit}`),rangemode:'tozero',zeroline:false,gridcolor:CHART.grid,tickfont:{size:CHART_TEXT.tick}},
   yaxis:{range:[n-.5+pad,-.5-pad],automargin:true,ticks:'outside',ticklen:8,tickcolor:'rgba(0,0,0,0)',tickfont:{size:CHART_TEXT.label,color:CHART.ink}}}}/>;
}

/* Donut dengan total di tengah; warna tetap per kategori bila disediakan. */
export function ShareDonut({rows=[],unit='responden',colors=GENDER_COLORS,onSelect,height=PLOT_MIN}){
 const valid=rows.filter(r=>Number.isFinite(r.n)&&r.n>0),total=valid.reduce((s,r)=>s+r.n,0);
 return <PlotlyChart height={height}
  data={[{type:'pie',labels:valid.map(r=>r.category),values:valid.map(r=>r.n),hole:.62,sort:false,direction:'clockwise',
   marker:{colors:valid.map((r,i)=>r.category==='Tidak diketahui'?CHART.neutral:colors[r.category]||CATEGORICAL[i%CATEGORICAL.length]),line:{color:'#ffffff',width:3}},
   textinfo:'percent',textfont:{color:'#fff',size:14,family:FONT_FAMILY},insidetextorientation:'horizontal',
   hovertemplate:'<b>%{label}</b><br>%{value} '+unit+' (%{percent})<extra></extra>'}]}
  onClick={onSelect?e=>{const p=pick(e);if(p?.label&&p.label!=='Tidak diketahui')onSelect(p.label)}:undefined}
  layout={{showlegend:true,legend:{orientation:'h',x:.5,xanchor:'center',y:-.02,yanchor:'top',font:{size:CHART_TEXT.legend,color:CHART.ink}},
   margin:{l:16,r:16,t:12,b:56},hoverlabel:baseHoverLabel,font:{family:FONT_FAMILY,size:CHART_TEXT.tick,color:CHART.muted},
   annotations:[{text:`<b style="font-size:28px;color:${CHART.ink}">${total.toLocaleString('id-ID')}</b><br><span style="color:${CHART.muted}">${unit}</span>`,
    x:.5,y:.5,showarrow:false,font:{size:CHART_TEXT.label,family:FONT_FAMILY}}]}}/>;
}

/* Histogram dengan garis rerata dan median agar bentuk sebaran langsung terbaca. */
export function DistributionHistogram({rows=[],field,label,unit,tone='blue',height=PLOT_MIN}){
 const t=TONE[tone]||TONE.blue;
 const values=rows.map(r=>r[field]).filter(Number.isFinite).sort((a,b)=>a-b);
 const mean=values.length?values.reduce((s,v)=>s+v,0)/values.length:null;
 const median=values.length?(values.length%2?values[(values.length-1)/2]:(values[values.length/2-1]+values[values.length/2])/2):null;
 const mid=values.length?(values[0]+values[values.length-1])/2:0;
 /* Label garis diletakkan di sisi yang lapang agar tidak terpotong di tepi grafik. */
 const mark=(x,color,dash,text,y)=>({x,text,color,dash,y,right:x>mid});
 const marks=mean==null?[]:[mark(mean,t.dark,'solid',`Rerata ${fmt(mean,1)}`,.98),mark(median,CHART.muted,'dot',`Median ${fmt(median,1)}`,.84)];
 return <PlotlyChart height={height}
  data={[{type:'histogram',x:values,marker:{color:t.base,opacity:.9,line:{color:'white',width:1.5}},
   hovertemplate:label+': %{x}<br>%{y} responden<extra></extra>'}]}
  layout={{showlegend:false,bargap:.06,margin:{l:64,r:24,t:16,b:64},hoverlabel:baseHoverLabel,
   font:{family:FONT_FAMILY,size:CHART_TEXT.tick,color:CHART.muted},
   xaxis:{title:axisTitle(`${label} (${unit})`),zeroline:false,tickfont:{size:CHART_TEXT.tick}},
   yaxis:{title:axisTitle('Jumlah responden'),rangemode:'tozero',zeroline:false,tickfont:{size:CHART_TEXT.tick}},
   shapes:marks.map(m=>({type:'line',xref:'x',yref:'paper',x0:m.x,x1:m.x,y0:0,y1:1,line:{color:m.color,width:2,dash:m.dash}})),
   annotations:marks.map(m=>({xref:'x',yref:'paper',x:m.x,y:m.y,text:m.text,showarrow:false,yanchor:'top',
    xanchor:m.right?'right':'left',xshift:m.right?-8:8,font:{size:CHART_TEXT.annotation+1,color:m.color,family:FONT_FAMILY},
    bgcolor:'rgba(255,255,255,.9)',borderpad:2}))}}/>;
}

/* Ringkasan angka di bagian atas halaman: hanya dihitung dari profil terfilter. */
export function ProfileStats({profiles=[],groups={}}){
 const mean=field=>{const v=profiles.map(r=>r[field]).filter(Number.isFinite);return v.length?v.reduce((s,x)=>s+x,0)/v.length:null};
 const age=mean('age'),bmi=mean('bmi');
 const places=name=>(groups[name]||[]).filter(r=>r.category&&r.category!=='Tidak diketahui').length;
 const items=[
  {icon:UsersRound,label:'Responden',value:whole(profiles.length),unit:'ID',note:'ID unik pada filter global'},
  {icon:CalendarDays,label:'Rerata usia',value:age==null?'—':fmt(age,1),unit:age==null?'':'tahun',note:'dari profil yang mengisi usia'},
  {icon:Scale,label:'Rerata BMI',value:bmi==null?'—':fmt(bmi,1),unit:bmi==null?'':'kg/m²',note:'deskriptif, bukan diagnosis'},
  {icon:MapPin,label:'Wilayah',value:<>{places('province')}<small>provinsi</small><span className="stat-sep" aria-hidden="true">·</span>{places('city')}<small>kab/kota</small></>,note:'menurut jawaban formulir'},
 ];
 return <div className="stat-grid">
  {items.map(({icon:Icon,label,value,unit,note})=><div key={label} className="stat-card">
   <div className="stat-label"><Icon size={18} aria-hidden="true"/><span>{label}</span></div>
   <div className="stat-value">{value}{unit&&<small>{unit}</small>}</div>
   <div className="stat-note">{note}</div></div>)}
 </div>;
}
