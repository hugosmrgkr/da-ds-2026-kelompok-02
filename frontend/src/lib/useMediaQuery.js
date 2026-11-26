import {useEffect,useState} from 'react';

/* True bila media query cocok. Aman tanpa window (pengujian di Node): kembali ke `fallback`. */
export function useMediaQuery(query,fallback=false){
  const supported=typeof window!=='undefined'&&typeof window.matchMedia==='function';
  const [matches,setMatches]=useState(()=>supported?window.matchMedia(query).matches:fallback);
  useEffect(()=>{
    if(!supported)return;
    const media=window.matchMedia(query),update=()=>setMatches(media.matches);
    update();
    media.addEventListener?.('change',update);
    return ()=>media.removeEventListener?.('change',update);
  },[query,supported]);
  return matches;
}
