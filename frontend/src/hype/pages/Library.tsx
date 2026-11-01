import {useState,useEffect} from 'react';
import {useResource} from '../../state';
import {type Output} from '../../api';
import {PageHead,Choice,Action,FileButton,Blank,Note} from '../kit';

const kind=(f:Output)=>{const ext=f.name.split('.').pop()?.toLowerCase()||'';return ['mp4','webm','mov'].includes(ext)?'video':['png','jpg','jpeg','webp'].includes(ext)?'image':['mp3','wav','m4a','ogg'].includes(ext)?'audio':'data'};

export default function Library(){
 const {value:files,loading,error,refresh}=useResource<Output[]>('/api/files');
 const [query,setQuery]=useState(''),[category,setCategory]=useState('All'),[open,setOpen]=useState<Output|null>(null);
 useEffect(()=>{if(!open)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(null)};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[open]);
 const cats=Array.from(new Set((files||[]).map(f=>f.category)));
 const list=(files||[]).filter(f=>(category==='All'||f.category===category)&&f.name.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>b.modified-a.modified);
 return <main className="rhx-page-body">
  <PageHead title="Your work." lede="Every clip, chart, overlay and data file you've made, newest first.">
   <Action quiet disabled={loading} onClick={refresh}>Refresh</Action>
  </PageHead>
  <div className="rhx-row">
   <label className="rhx-field rhx-search"><span className="rhx-label">Find a file</span><input type="search" value={query} placeholder="Driver, track or file name" onChange={e=>setQuery(e.target.value)}/></label>
   {cats.length>0&&<Choice label="Type" value={category} onChange={setCategory} options={[{value:'All',label:'Everything',hint:String(files?.length||0)},...cats.map(c=>({value:c,label:c,hint:String((files||[]).filter(f=>f.category===c).length)}))]}/>}
  </div>
  {error&&<p className="rhx-error" role="alert">{error}</p>}
  {loading&&<div className="rhx-loading" aria-label="Loading your files"/>}
  {!loading&&!list.length?<Blank title="The next one is yours." mark="◫">Finished videos, charts, telemetry packages, radio and overlays land here.</Blank>:
   <div className="rhx-library">{list.map(f=>{const k=kind(f);return <article key={f.id} className={'rhx-card is-'+k}>
    <button type="button" className="rhx-card-view" onClick={()=>setOpen(f)} aria-label={'Open '+f.name}>
     {k==='image'?<img src={f.url} alt="" loading="lazy"/>:k==='video'?<video src={f.url+'#t=0.5'} muted preload="metadata"/>:<span className="rhx-card-ext">{f.name.split('.').pop()?.toUpperCase()}</span>}
    </button>
    <div className="rhx-card-info"><h3 title={f.name}>{f.name}</h3><small>{f.category}, {new Date(f.modified*1000).toLocaleDateString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</small><FileButton file={f} label="Download"/></div>
   </article>})}</div>}
  {list.length>0&&<Note>{list.length} files. Only generated outputs are listed; source models and caches stay private.</Note>}
  {open&&<div className="rhx-modal" onClick={()=>setOpen(null)}><section role="dialog" aria-modal="true" aria-label={open.name} onClick={e=>e.stopPropagation()}>
   <button type="button" className="rhx-modal-close" onClick={()=>setOpen(null)} autoFocus aria-label="Close">Close</button>
   <h2>{open.name}</h2>
   {kind(open)==='image'?<img src={open.url} alt={open.name}/>:kind(open)==='video'&&!open.name.endsWith('.mov')?<video src={open.url} controls playsInline autoPlay/>:kind(open)==='audio'?<audio src={open.url} controls/>:<Note>Download this file to open it in your editor.</Note>}
   <FileButton file={open}/>
  </section></div>}
 </main>;
}
