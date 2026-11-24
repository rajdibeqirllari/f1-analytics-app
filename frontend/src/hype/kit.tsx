import {useId,useRef,useState,type ReactNode} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {ArrowDownToLine} from 'lucide-react';
import {countryFlags,teamColor,type Output} from '../api';
import type {useTask} from '../state';
import {useWeekend} from './useWeekend';
import StartLights from './StartLights';

type Task=ReturnType<typeof useTask>;

export function Flag({country}:{country:string}){
 const code=countryFlags[country];const [bad,setBad]=useState(false);
 if(!code||bad)return null;
 return <img className="rhx-flag" src={`/art/flags/${code}.png`} alt="" onError={()=>setBad(true)}/>;
}

/** Page title in the same voice as the weekend picker headline. */
export function PageHead({title,lede,children}:{title:string;lede:ReactNode;children?:ReactNode}){
 return <header className="rhx-head"><div><h1 className="rhx-head-title">{title}</h1><p className="rhx-head-lede">{lede}</p></div>{children&&<div className="rhx-head-aside">{children}</div>}</header>;
}

/** The weekend that follows you between pages. */
export function WeekendBar(){
 const {selection:s,pick,session,catalog}=useWeekend();const loc=useLocation();
 const a=catalog?.drivers[s.driver],b=catalog?.drivers[s.driver_b];
 return <div className="rhx-wbar">
  <Link to={{pathname:'/hype',search:loc.search}} className="rhx-wbar-event" title="Change the weekend">
   {pick&&<Flag country={pick.country}/>}<b>{s.year} {pick?.short||'No weekend'}</b><span>{session?.name||s.session}</span>
  </Link>
  {catalog?<span className="rhx-wbar-duel">
   {a&&<i style={{'--team':teamColor(a.color)} as React.CSSProperties}>{s.driver}</i>}{b&&<><em>vs</em><i style={{'--team':teamColor(b.color)} as React.CSSProperties}>{s.driver_b}</i></>}
  </span>:<span className="rhx-wbar-state">Not loaded</span>}
  <Link to={{pathname:'/hype',search:loc.search}} className="rhx-wbar-change">Change</Link>
 </div>;
}

/** Shown in place of a tool when the chosen session hasn't been loaded yet. */
export function NeedSession({what}:{what:string}){
 const {pick,session,canLoad,catalogJob,loadCatalog,catalog}=useWeekend();const loc=useLocation();
 return <div className="rhx-need">
  <div><h2>Load the weekend first</h2><p>{what} uses the drivers and laps of the session you picked. Load it here, or <Link to={{pathname:'/hype',search:loc.search}}>choose another weekend</Link>.</p></div>
  <StartLights label={pick&&session?`${pick.short}, ${session.name}`:'Pick a weekend on the map'} disabled={!canLoad} busy={catalogJob.busy}
   progress={catalogJob.job?.progress||0} message={catalogJob.job?.message||''} loaded={!!catalog} onLaunch={loadCatalog} onCancel={catalogJob.cancel}/>
  {(catalogJob.error||catalogJob.job?.error)&&<p className="rhx-error" role="alert">{catalogJob.error||catalogJob.job?.error}</p>}
 </div>;
}

export type Opt<T>={value:T;label:ReactNode;hint?:ReactNode;visual?:ReactNode;disabled?:boolean};
/** Replaces every dropdown: all options visible, one tap to choose. */
export function Choice<T extends string|number>({label,value,options,onChange,variant='chips',className=''}:{label:string;value:T;options:Opt<T>[];onChange:(v:T)=>void;variant?:'chips'|'cards'|'shapes';className?:string}){
 const box=useRef<HTMLDivElement>(null);const id=useId();
 const live=options.filter(o=>!o.disabled);
 // Roving tab stop: the chosen option, or the first enabled one when nothing is chosen.
 const stop=live.some(o=>o.value===value)?value:live[0]?.value;
 const move=(e:React.KeyboardEvent)=>{const d={ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1}[e.key];if(!d)return;e.preventDefault();
  if(!live.length)return;const i=live.findIndex(o=>o.value===value);
  const next=i<0?(d>0?live[0]:live[live.length-1]):live[(i+d+live.length)%live.length];
  onChange(next.value);requestAnimationFrame(()=>box.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus())};
 return <div className={'rhx-field '+className}><span className="rhx-label" id={id}>{label}</span>
  <div ref={box} className={'rhx-choice is-'+variant} role="radiogroup" aria-labelledby={id} onKeyDown={move}>
   {options.map(o=>{const on=o.value===value;return <button type="button" role="radio" aria-checked={on} tabIndex={o.value===stop&&!o.disabled?0:-1} key={String(o.value)} disabled={o.disabled}
    className={on?'on':''} onClick={()=>onChange(o.value)}>{o.visual}<b>{o.label}</b>{o.hint&&<small>{o.hint}</small>}</button>})}
  </div></div>;
}

export function Slider({label,value,min,max,step=1,format=(v:number)=>String(v),onChange}:{label:string;value:number;min:number;max:number;step?:number;format?:(v:number)=>string;onChange:(v:number)=>void}){
 const pct=(value-min)/(max-min)*100;
 return <label className="rhx-field rhx-slider"><span className="rhx-label">{label}<output>{format(value)}</output></span>
  <input type="range" min={min} max={max} step={step} value={value} style={{'--pct':pct+'%'} as React.CSSProperties} onChange={e=>onChange(Number(e.target.value))}/></label>;
}

export function NumberField({label,value,onChange,min,max,step=1,suffix}:{label:string;value:number;onChange:(v:number)=>void;min?:number;max?:number;step?:number;suffix?:string}){
 return <label className="rhx-field rhx-num"><span className="rhx-label">{label}</span><span className="rhx-num-box">
  <input type="number" value={value} min={min} max={max} step={step} onChange={e=>onChange(Number(e.target.value))}/>{suffix&&<em>{suffix}</em>}</span></label>;
}

export function Group({title,children,aside}:{title:string;children:ReactNode;aside?:ReactNode}){
 return <section className="rhx-group"><div className="rhx-group-head"><h3>{title}</h3>{aside}</div><div className="rhx-group-body">{children}</div></section>;
}

/** Primary action, same shape as "Load session". */
export function Action({children,sub,onClick,disabled,quiet}:{children:ReactNode;sub?:ReactNode;onClick?:()=>void;disabled?:boolean;quiet?:boolean}){
 return <button type="button" className={'rhx-action '+(quiet?'is-quiet':'')} disabled={disabled} onClick={onClick}><span>{children}</span>{sub&&<small>{sub}</small>}</button>;
}

/** Job progress as five pods, like the start lights filling in blue. */
export function JobBar({task,idle}:{task:Task;idle?:string}){
 const j=task.job;const err=task.error||j?.error;
 if(err)return <p className="rhx-error" role="alert">{err}</p>;
 if(j?.status==='cancelled')return <p className="rhx-note" role="status">Stopped. Nothing was saved from that run.</p>;
 if(!task.busy)return idle?<p className="rhx-note">{idle}</p>:null;
 const p=Math.min(1,Math.max(.02,j?.progress||0));
 return <div className="rhx-job" role="status"><span className="rhx-job-pods" aria-hidden="true">{[1,2,3,4,5].map(i=><i key={i} className={p*5>=i-.001?'on':''}/>)}</span>
  <span className="rhx-job-text"><b>{j?.message||'Contacting the data engine'}</b><small>{Math.round(p*100)}%</small></span>
  <button type="button" onClick={task.cancel}>Cancel</button></div>;
}

export function FileButton({file,label}:{file:Output;label?:string}){
 return <a className="rhx-file" href={file.url+'?download=true'}><ArrowDownToLine aria-hidden="true"/><span><b>{label||file.label||file.name}</b><small>{(file.size/1024/1024).toFixed(2)} MB</small></span></a>;
}

export function Blank({title,children,mark}:{title:string;children?:ReactNode;mark?:ReactNode}){
 return <div className="rhx-blank">{mark&&<span className="rhx-blank-mark" aria-hidden="true">{mark}</span>}<h3>{title}</h3>{children&&<p>{children}</p>}</div>;
}
export function Note({children}:{children:ReactNode}){return <p className="rhx-note">{children}</p>}

/** Shared source selector for Overlays and Telemetry, including CSV upload. */
export function SourcePicker({source,setSource,upload,setUpload,request}:{source:string;setSource:(v:string)=>void;upload:string;setUpload:(v:string)=>void;request:(url:string,init?:RequestInit)=>Promise<any>}){
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[name,setName]=useState('');
 return <div className="rhx-source">
  <Choice label="Data source" value={source} onChange={setSource} variant="cards" options={[
   {value:'Auto',label:'Auto',hint:'FastF1 first, OpenF1 if it fails'},{value:'FastF1',label:'FastF1',hint:'Official timing archive'},
   {value:'OpenF1',label:'OpenF1',hint:'Finished sessions from 2023'},{value:'Upload CSV',label:'Your CSV',hint:'Up to 10 MB'}]}/>
  {source==='Upload CSV'&&<label className={'rhx-drop '+(upload?'is-done':'')}>
   <input type="file" accept=".csv,text/csv" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;setBusy(true);setError('');setUpload('');setName(file.name);
    const data=new FormData();data.append('file',file);try{const r=await request('/api/uploads',{method:'POST',body:data});setUpload(r.id)}catch(err){setError((err as Error).message)}finally{setBusy(false)}}}/>
   <b>{busy?'Uploading…':upload?`${name} is ready`:'Drop a telemetry CSV here or click to browse'}</b><small>{upload?'Choose another file to replace it':'Maximum 10 MB'}</small>
  </label>}
  {error&&<p className="rhx-error" role="alert">{error}</p>}
 </div>;
}

/** A small outline of an aspect ratio, used in frame and canvas choices. */
export function Shape({w,h}:{w:number;h:number}){
 const k=28/Math.max(w,h),rw=w*k,rh=h*k;
 return <svg viewBox="0 0 40 40" className="rhx-shape" aria-hidden="true"><rect x={20-rw/2} y={20-rh/2} width={rw} height={rh} rx="2"/></svg>;
}
