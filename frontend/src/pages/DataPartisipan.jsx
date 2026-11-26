import React,{useState} from 'react';
import {MousePointerClick} from 'lucide-react';
import {Card,Notice,MiniTable,Empty} from '../components/Common';
import {RankBars,ShareDonut,DistributionHistogram,ProfileStats,rankSlots,rankHeight} from '../components/data-readiness/ParticipantCharts';
import {useMediaQuery} from '../lib/useMediaQuery';
import {fmt,whole} from '../lib/api';
import {ChartCard,Explainer} from '../components/page-shared/Analysis';

export default function DataPartisipan({data,onFilter}){
 const [search,setSearch]=useState('');
 const stacked=useMediaQuery('(max-width:1100px)');
 const profiles=data?.participants||[],groups=data?.demographics||{};
 /* Dua kolom: kedua grafik pada satu baris memakai tinggi yang sama. Satu kolom: tiap grafik memakai tinggi sendiri. */
 const pair=(a,b)=>stacked?[rankHeight(rankSlots(a)),rankHeight(rankSlots(b))]:Array(2).fill(rankHeight(rankSlots(a),rankSlots(b)));
 const [eduH,occH]=pair(groups.education,groups.occupation),[provH,cityH]=pair(groups.province,groups.city);
 const ageGroupH=rankHeight(rankSlots(groups.age_group));
 const rows=profiles.filter(row=>[row.respondent_id,row.city,row.occupation,row.province,row.education].join(' ').toLowerCase().includes(search.toLowerCase()));
 if(!data)return <Empty/>;
 if(!profiles.length)return <Empty message={data.message}/>;
 return <div className="participant-page"><Notice>Profil dihitung satu kali per ID, bukan per sesi. Grafik mengikuti filter global; pencarian di bawah hanya menyaring tabel. Nama, kontak, dan identitas langsung tidak ditampilkan.</Notice>
 <p className="interaction-hint"><MousePointerClick size={20} aria-hidden="true"/><span>Klik jenis kelamin, pendidikan, pekerjaan atau wilayah untuk menyaring semua analitik. Wilayah dapat diperinci dari provinsi ke kabupaten/kota.</span></p>
 <ProfileStats profiles={profiles} groups={groups}/>
 <div className="participant-grid">
 <ChartCard className="participant-card" title="Distribusi usia responden" sample={`${whole(profiles.filter(row=>Number.isFinite(row.age)).length)} profil dengan usia`} description="Usia dalam tahun pada Form Awal. Setiap profil menyumbang satu observasi; nilai kosong tidak digambar."><DistributionHistogram rows={profiles} field="age" label="Usia" unit="tahun" tone="blue"/></ChartCard>
 <ChartCard className="participant-card" title="Komposisi jenis kelamin" sample={`${whole(profiles.length)} profil pada pilihan global`} description="Proporsi profil pada jawaban formulir; bukan proporsi sesi pengukuran."><ShareDonut rows={groups.gender} unit="responden" onSelect={onFilter?value=>onFilter({gender:value}):undefined}/></ChartCard>
 <ChartCard className="participant-card" title="Pendidikan responden" sample={`${whole(profiles.length)} profil`} description="Jumlah ID per tingkat pendidikan. Klik kategori untuk memeriksa pola pengukuran kelompok tersebut."><RankBars tone="blue" height={eduH} rows={groups.education} onSelect={onFilter?value=>onFilter({education:value}):undefined}/></ChartCard>
 <ChartCard className="participant-card" title="Pekerjaan responden" sample={`${whole(profiles.length)} profil`} description="Pekerjaan berasal dari Form Awal. Kelompok kecil harus dibaca bersama jumlah sampelnya."><RankBars tone="amber" height={occH} rows={groups.occupation} onSelect={onFilter?value=>onFilter({occupation:value}):undefined}/></ChartCard>
 <ChartCard className="participant-card" title="Sebaran responden menurut provinsi" sample={`${whole(profiles.length)} profil`} description="Klik provinsi, lalu perinci pada grafik kabupaten/kota. Sebaran ini tidak mewakili cakupan populasi wilayah."><RankBars tone="teal" height={provH} rows={groups.province} onSelect={onFilter?value=>onFilter({province:value,city:''}):undefined}/></ChartCard>
 <ChartCard className="participant-card" title="Sebaran responden menurut kabupaten/kota" sample={`${whole(profiles.length)} profil`} description="Lokasi sesuai jawaban formulir, tanpa koordinat atau alamat pribadi."><RankBars tone="teal" height={cityH} rows={groups.city} onSelect={onFilter?value=>onFilter({city:value}):undefined}/></ChartCard>
 <ChartCard className="participant-card" title="Distribusi BMI responden" sample={`${whole(profiles.filter(row=>Number.isFinite(row.bmi)).length)} profil dengan BMI`} description="BMI = berat badan (kg) / tinggi (m) kuadrat. Grafik deskriptif ini tidak memberikan kategori atau diagnosis klinis."><DistributionHistogram rows={profiles} field="bmi" label="BMI" unit="kg/m²" tone="teal" height={ageGroupH}/></ChartCard>
 <ChartCard className="participant-card" title="Kelompok usia responden" sample={`${whole(profiles.length)} profil`} description="Kelompok usia mengikuti definisi API. Klik kelompok untuk menyaring KPI, faktor gaya hidup dan tren."><RankBars tone="blue" height={ageGroupH} rows={groups.age_group} onSelect={onFilter?value=>onFilter({age_group:value}):undefined}/></ChartCard>
 </div>
 <Card title="Profil responden anonim" action={<span className="hint-inline">{whole(rows.length)} dari {whole(profiles.length)} profil</span>}><div className="table-toolbar"><label className="field"><span>Cari ID, lokasi, pendidikan, atau pekerjaan</span><input value={search} onChange={event=>setSearch(event.target.value)} placeholder="Cari pada tabel terfilter"/></label></div>
 <MiniTable rows={rows.map(row=>({...row,bmi:fmt(row.bmi,1),days:whole(row.days),drill:onFilter?<button className="link-button" onClick={()=>onFilter({respondent_id:row.respondent_id})} aria-label={'Telusuri '+row.respondent_id}>Telusuri ID</button>:null}))} columns={[["respondent_id","ID"],["age","Usia (tahun)"],["gender","Jenis kelamin"],["education","Pendidikan"],["occupation","Pekerjaan"],["province","Provinsi"],["city","Kab/Kota"],["bmi","BMI (kg/m2)"],["active_days_week","Hari aktif/minggu"],["days","Hari tercatat"],["drill","Perinci"]]}/><Explainer>Hari tercatat adalah tanggal unik pada filter aktif. Profil tidak digandakan untuk sesi pagi dan malam. Data profil kosong tetap ditampilkan sebagai tanda kosong.</Explainer></Card></div>;
}
