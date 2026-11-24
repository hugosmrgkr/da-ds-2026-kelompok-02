import React from 'react';
import {PlotlyChart} from '../Common';

/* Palet tunggal untuk halaman Data Partisipan: satu warna per jenis informasi
   agar pembaca mengenali topik grafik tanpa membaca legenda. */
export const TONE={
 blue:{base:'#2563eb',dark:'#1e3a8a',light:'#bfdbfe'},
 teal:{base:'#0d9488',dark:'#134e4a',light:'#99f6e4'},
 amber:{base:'#d97706',dark:'#92400e',light:'#fde68a'},
 violet:{base:'#7c3aed',dark:'#4c1d95',light:'#ddd6fe'},
 rose:{base:'#e11d48',dark:'#881337',light:'#fecdd3'},
};
export const GENDER_COLORS={'Laki-laki':'#2563eb','Perempuan':'#ec4899'};
const FALLBACK=['#2563eb','#0d9488','#d97706','#7c3aed','#e11d48','#0ea5e9'];
const UNKNOWN='#94a3b8';
const pick=event=>event?.points?.[0];
const mix=(a,b,t)=>{const p=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));const [x,y]=[p(a),p(b)];
 return '#'+x.map((v,i)=>Math.round(v+(y[i]-v)*t).toString(16).padStart(2,'0')).join('')};

/* Batang horizontal berurutan dari terbanyak; warna memudar mengikuti peringkat. */
export function RankBars({rows=[],tone='blue',unit='responden',onSelect,limit=12}){
 const t=TONE[tone]||TONE.blue;
 const sorted=[...rows].filter(r=>Number.isFinite(r.n)).sort((a,b)=>b.n-a.n);
 const shown=sorted.slice(0,limit),hidden=sorted.slice(limit).reduce((s,r)=>s+r.n,0);
 const data=hidden>0?[...shown,{category:`Lainnya (${sorted.length-limit} kategori)`,n:hidden,other:true}]:shown;
 const colors=data.map((r,i)=>r.other||r.category==='Tidak diketahui'?UNKNOWN:mix(t.dark,t.base,shown.length>1?Math.min(1,i/(shown.length-1))*.85:0));
 return <PlotlyChart height={Math.max(280,data.length*34+80)}
  data={[{type:'bar',orientation:'h',x:data.map(r=>r.n),y:data.map(r=>r.category),marker:{color:colors,line:{color:'white',width:1}},
   text:data.map(r=>r.n),textposition:'outside',cliponaxis:false,textfont:{color:'#334155',size:12},
   hovertemplate:'<b>%{y}</b><br>%{x} '+unit+'<extra></extra>'}]}
  onClick={onSelect?e=>{const p=pick(e);if(p?.y&&p.y!=='Tidak diketahui'&&!String(p.y).startsWith('Lainnya'))onSelect(p.y)}:undefined}
  layout={{margin:{l:20,r:44,t:10,b:42},showlegend:false,bargap:.28,
   xaxis:{title:`Jumlah ${unit}`,rangemode:'tozero',zeroline:false,gridcolor:'#eef2f7'},
   yaxis:{autorange:'reversed',automargin:true,tickfont:{size:12,color:'#1e293b'}}}}/>;
}

/* Donut dengan total di tengah; warna tetap per kategori bila disediakan. */
export function ShareDonut({rows=[],unit='responden',colors=GENDER_COLORS,onSelect}){
 const valid=rows.filter(r=>Number.isFinite(r.n)&&r.n>0),total=valid.reduce((s,r)=>s+r.n,0);
 return <PlotlyChart height={320}
  data={[{type:'pie',labels:valid.map(r=>r.category),values:valid.map(r=>r.n),hole:.62,sort:false,direction:'clockwise',
   marker:{colors:valid.map((r,i)=>colors[r.category]||FALLBACK[i%FALLBACK.length]),line:{color:'#ffffff',width:3}},
   textinfo:'percent',textfont:{color:'#fff',size:13},insidetextorientation:'horizontal',
   hovertemplate:'<b>%{label}</b><br>%{value} '+unit+' (%{percent})<extra></extra>'}]}
  onClick={onSelect?e=>{const p=pick(e);if(p?.label&&p.label!=='Tidak diketahui')onSelect(p.label)}:undefined}
  layout={{showlegend:true,legend:{orientation:'h',x:.5,xanchor:'center',y:-.04,font:{size:12}},margin:{l:12,r:12,t:12,b:48},
   annotations:[{text:`<b style="font-size:26px;color:#0f172a">${total.toLocaleString('id-ID')}</b><br><span style="color:#64748b">${unit}</span>`,
    x:.5,y:.5,showarrow:false,font:{size:12}}]}}/>;
}

/* Histogram dengan garis rerata dan median agar bentuk sebaran langsung terbaca. */
export function DistributionHistogram({rows=[],field,label,unit,tone='blue'}){
 const t=TONE[tone]||TONE.blue;
 const values=rows.map(r=>r[field]).filter(Number.isFinite).sort((a,b)=>a-b);
 const mean=values.length?values.reduce((s,v)=>s+v,0)/values.length:null;
 const median=values.length?(values.length%2?values[(values.length-1)/2]:(values[values.length/2-1]+values[values.length/2])/2):null;
 const line=(x,color,dash,text,y)=>({x,text,color,dash,y});
 const marks=mean==null?[]:[line(mean,t.dark,'solid',`Rerata ${mean.toFixed(1)}`,1.0),line(median,'#64748b','dot',`Median ${median.toFixed(1)}`,.88)];
 return <PlotlyChart
  data={[{type:'histogram',x:values,marker:{color:t.base,opacity:.88,line:{color:'white',width:1.5}},
   hovertemplate:label+': %{x}<br>%{y} responden<extra></extra>'}]}
  layout={{showlegend:false,bargap:.06,margin:{l:52,r:24,t:30,b:58},
   xaxis:{title:`${label} (${unit})`,zeroline:false},yaxis:{title:'Jumlah responden',rangemode:'tozero',zeroline:false},
   shapes:marks.map(m=>({type:'line',xref:'x',yref:'paper',x0:m.x,x1:m.x,y0:0,y1:1,line:{color:m.color,width:2,dash:m.dash}})),
   annotations:marks.map(m=>({xref:'x',yref:'paper',x:m.x,y:m.y,text:m.text,showarrow:false,xanchor:'left',xshift:6,font:{size:11,color:m.color},
    bgcolor:'rgba(255,255,255,.85)'}))}}/>;
}

/* Ringkasan angka di bagian atas halaman: hanya dihitung dari profil terfilter. */
export function ProfileStats({profiles=[],groups={}}){
 const mean=field=>{const v=profiles.map(r=>r[field]).filter(Number.isFinite);return v.length?v.reduce((s,x)=>s+x,0)/v.length:null};
 const age=mean('age'),bmi=mean('bmi');
 const places=name=>(groups[name]||[]).filter(r=>r.category&&r.category!=='Tidak diketahui').length;
 const items=[
  ['Responden',profiles.length.toLocaleString('id-ID'),'ID unik pada filter global',TONE.blue.base],
  ['Rerata usia',age==null?'—':age.toFixed(1)+' th','dari profil yang mengisi usia',TONE.violet.base],
  ['Rerata BMI',bmi==null?'—':bmi.toFixed(1),'kg/m² · deskriptif, bukan diagnosis',TONE.teal.base],
  ['Wilayah',`${places('province')} prov · ${places('city')} kab/kota`,'menurut jawaban formulir',TONE.amber.base],
 ];
 return <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(190px,1fr))',gap:16,marginBottom:20}}>
  {items.map(([title,value,note,color])=><div key={title} style={{background:'#fff',border:'1px solid #e1e7ef',borderTop:`4px solid ${color}`,borderRadius:12,padding:'14px 18px'}}>
   <div style={{fontSize:12,fontWeight:600,color:'#64748b',textTransform:'uppercase',letterSpacing:.4}}>{title}</div>
   <div style={{fontSize:26,fontWeight:700,color:'#0f172a',lineHeight:1.25,margin:'4px 0 2px'}}>{value}</div>
   <div style={{fontSize:12,color:'#64748b'}}>{note}</div></div>)}
 </div>;
}
