import {useState,useEffect,useRef} from 'react';
import {useResource} from '../../state';
import {type Output} from '../../api';
import {PageHead,Choice,Action,FileButton,Blank,Note} from '../kit';

const kind=(f:Output)=>{const ext=f.name.split('.').pop()?.toLowerCase()||'';return ['mp4','webm','mov'].includes(ext)?'video':['png','jpg','jpeg','webp'].includes(ext)?'image':['mp3','wav','m4a','ogg'].includes(ext)?'audio':'data'};

export default function Library(){
 const {value:files,loading,error,refresh}=useResource<Output[]>('/api/files');
 const [query,setQuery]=useState(''),[category,setCategory]=useState('All'),[open,setOpen]=useState<Output|null>(null),[shown,setShown]=useState(PAGE);
 const dialog=useRef<HTMLElement>(null),opener=useRef<HTMLElement|null>(null);
 useEffect(()=>setShown(PAGE),[query,category]);
 // Dialog: Escape closes, Tab stays inside, the page behind can't be reached, focus goes back to the card.
 useEffect(()=>{if(!open)return;const root=document.querySelector<HTMLElement>('.rhx-library-page');root?.setAttribute('inert','');
  const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();setOpen(null);return}
   if(e.key!=='Tab'||!dialog.current)return;const items=[...dialog.current.querySelectorAll<HTMLElement>('button,a[href],audio,video,[tabindex]:not([tabindex="-1"])')];
   if(!items.length)return;const first=items[0],last=items[items.length-1];
   if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}};
  window.addEventListener('keydown',key);
  return()=>{window.removeEventListener('keydown',key);root?.removeAttribute('inert');opener.current?.focus()}},[open]);
 const cats=Array.from(new Set((files||[]).map(f=>f.category)));
 const list=(files||[]).filter(f=>(category==='All'||f.category===category)&&f.name.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>b.modified-a.modified);
 return <><main className="rhx-page-body rhx-library-page">
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
   <div className="rhx-library">{list.slice(0,shown).map(f=>{const k=kind(f);return <article key={f.id} className={'rhx-card is-'+k}>
    <button type="button" className="rhx-card-view" onClick={e=>{opener.current=e.currentTarget;setOpen(f)}} aria-label={'Open '+f.name}>
     {k==='image'?<img src={f.url} alt="" loading="lazy" decoding="async"/>:k==='video'?<LazyVideo src={f.url}/>:<span className="rhx-card-ext">{f.name.split('.').pop()?.toUpperCase()}</span>}
    </button>
    <div className="rhx-card-info"><h3 title={f.name}>{f.name}</h3><small>{f.category}, {new Date(f.modified*1000).toLocaleDateString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</small><FileButton file={f} label="Download"/></div>
   </article>})}</div>}
  {list.length>shown&&<div className="rhx-row"><button type="button" className="rhx-link" onClick={()=>setShown(n=>n+PAGE)}>Show {Math.min(PAGE,list.length-shown)} more</button><span className="rhx-count">Showing {shown} of {list.length}</span></div>}
  {list.length>0&&<Note>{list.length} files. Only finished outputs are listed; caches, render frames, recordings, commentator voice lines and downloaded team radio stay private.</Note>}
 </main>
  {open&&<div className="rhx-modal" onClick={()=>setOpen(null)}><section ref={dialog} role="dialog" aria-modal="true" aria-label={open.name} onClick={e=>e.stopPropagation()}>
   <button type="button" className="rhx-modal-close" onClick={()=>setOpen(null)} autoFocus aria-label="Close">Close</button>
   <h2>{open.name}</h2>
   {kind(open)==='image'?<img src={open.url} alt={open.name}/>:kind(open)==='video'&&!open.name.endsWith('.mov')?<video src={open.url} controls playsInline autoPlay/>:kind(open)==='audio'?<audio src={open.url} controls/>:<Note>Download this file to open it in your editor.</Note>}
   <FileButton file={open}/>
  </section></div>}
 </>;
}

const PAGE=48;
/** A video thumbnail that only loads when it scrolls into view (hundreds of files must not all start loading). */
function LazyVideo({src}:{src:string}){
 const ref=useRef<HTMLSpanElement>(null),[seen,setSeen]=useState(false);
 useEffect(()=>{const el=ref.current;if(!el||seen)return;if(typeof IntersectionObserver==='undefined'){setSeen(true);return}
  const io=new IntersectionObserver(es=>{if(es.some(e=>e.isIntersecting)){setSeen(true);io.disconnect()}},{rootMargin:'200px'});io.observe(el);return()=>io.disconnect()},[seen]);
 return <span ref={ref} className="rhx-card-lazy">{seen?<video src={src+'#t=0.5'} muted preload="metadata" tabIndex={-1}/>:<span className="rhx-card-ext">VIDEO</span>}</span>;
}
