import {createContext,useContext,useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {useSearchParams} from 'react-router-dom';
import {post,request,type Selection,type Catalog,type Job} from './api';
import {toRound} from './hype/weekend';

const initial:Selection={year:new Date().getFullYear(),event:'',session:'Q',driver:'',driver_b:'',lap:null,lap_b:null,qualifying_part:'All'};
function stored(){try{return {...initial,...JSON.parse(localStorage.getItem('rh-session-v1')||'{}')}}catch{return initial}}
const saved=stored();
type SessionState={selection:Selection;setSelection:(patch:Partial<Selection>)=>void;calendar:any[];calendarError:string;calendarLoading:boolean;catalog:Catalog|null;loadCatalog:()=>void;catalogJob:ReturnType<typeof useTask>};
const Context=createContext<SessionState>(null!);
export const useSession=()=>useContext(Context);
const responseCache=new Map<string,{time:number;value:any}>();
export function useResource<T=any>(url:string|null){
 const [value,setValue]=useState<T|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const [revision,refresh]=useState(0);
 useEffect(()=>{setError('');setValue(null);if(!url){setLoading(false);return}
  const cached=responseCache.get(url);if(cached&&Date.now()-cached.time<60000&&!revision){setValue(cached.value);setLoading(false);return}
  const ctrl=new AbortController();setLoading(true);
  request<T>(url,{signal:ctrl.signal}).then(data=>{responseCache.set(url,{time:Date.now(),value:data});setValue(data)}).catch(e=>{if(e.name!=='AbortError')setError(e.message)}).finally(()=>{if(!ctrl.signal.aborted)setLoading(false)});
  return()=>ctrl.abort();
 },[url,revision]);
 return {value,error,loading,refresh:()=>refresh(n=>n+1)};
}

const ACTIVE=['queued','running','building','rendering'];
/** A network hiccup (engine busy, Wi-Fi blip) is retried; an answer from the engine (e.g. "task not found") is final. */
const isNetworkError=(e:unknown)=>e instanceof TypeError||(e as Error)?.name==='TypeError';

export function useTask(storageKey?:string){
 const [job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[submitting,setSubmitting]=useState(false),[retrying,setRetrying]=useState(false);
 const [id,setId]=useState<string|null>(()=>storageKey?sessionStorage.getItem(storageKey):null);
 const version=useRef(0);
 useEffect(()=>{if(storageKey){if(id)sessionStorage.setItem(storageKey,id);else sessionStorage.removeItem(storageKey)}},[id,storageKey]);
 useEffect(()=>{
  if(!id)return;let active=true;let timer:ReturnType<typeof setTimeout>;let failures=0;
  const poll=async()=>{try{const data=await request<Job>('/api/jobs/'+id);if(!active)return;failures=0;setRetrying(false);setJob(data);
    if(ACTIVE.includes(data.status))timer=setTimeout(poll,1000);
   }catch(e){if(!active)return;
    if(isNetworkError(e)&&failures<6){failures++;setRetrying(true);timer=setTimeout(poll,Math.min(15000,1000*2**failures));return}
    // A real failure: end in a consistent state so every button works again (no "running" job without an id).
    const message=isNetworkError(e)?'Lost contact with the data engine. Check that it is running, then start again.':(e as Error).message;
    setRetrying(false);setError(message);setJob(j=>j?{...j,status:'failed',error:message}:null);setId(null)}};
  poll();
  return()=>{active=false;clearTimeout(timer)};
 },[id]);
 const start=async(kind:string,selection:Selection,options:Record<string,any>={})=>{
  const generation=++version.current;setSubmitting(true);setError('');setJob(null);setId(null);
  try{const actualSelection=options.source==='Upload CSV'?{...selection,event:selection.event||'Uploaded telemetry'}:selection;
   const data=await post<{id:string}>('/api/jobs',{kind,selection:actualSelection,options});if(version.current===generation)setId(data.id)}
  catch(e){if(version.current===generation)setError((e as Error).message)}finally{if(version.current===generation)setSubmitting(false)};
 };
 const reset=()=>{version.current++;setId(null);setJob(null);setError('');setSubmitting(false);setRetrying(false)};
 const running=!!job&&ACTIVE.includes(job.status);
 return {job,error,start,reset,id,retrying,busy:submitting||!!(id&&!job)||(running&&!!id),
  cancel:async()=>{if(!id){setJob(j=>j&&ACTIVE.includes(j.status)?{...j,status:'cancelled'}:j);return}
   try{await post('/api/jobs/'+id+'/cancel',{})}catch(e){setError((e as Error).message)}},
  result:job?.status==='complete'?job.result:null};
}

/** The round a first visit should land on: a weekend whose sessions are under way or a few days off, else the most
 * recent completed one, else round one. */
export function defaultRound(schedule:any[],now=Date.now()){
 const rounds=schedule.map(r=>toRound(r,now)).sort((a,b)=>a.round-b.round);
 if(!rounds.length)return null;
 const soon=rounds.find(r=>r.sessions.some(s=>s.start&&Math.abs(+s.start-now)<3*86400e3)&&!r.done);
 const done=[...rounds].reverse().find(r=>r.done);
 return soon||done||rounds[0];
}

export function SessionProvider({children}:{children:ReactNode}){
 const [params,setParams]=useSearchParams();
 const selection=useMemo(()=>{const next={...saved};for(const [key,val] of params){if(key in initial)(next as any)[key]=['year','lap','lap_b'].includes(key)?(val?Number(val):null):val;}
  // Q1/Q2/Q3 only exists in qualifying: a value left over from another session never filters this one.
  if(!['Q','SQ'].includes(next.session))next.qualifying_part='All';
  return next as Selection},[params]);
 const setSelection=(patch:Partial<Selection>)=>setParams(previous=>{const next=new URLSearchParams(previous);
  // Changing the weekend or session always starts from "All of qualifying".
  if(('event' in patch||'year' in patch||'session' in patch)&&!('qualifying_part' in patch))next.set('qualifying_part','All');
  for(const [key,value] of Object.entries(patch))next.set(key,value==null?'':String(value));return next},{replace:true});
 useEffect(()=>{localStorage.setItem('rh-session-v1',JSON.stringify(selection))},[selection]);
 const schedule=useResource<any[]>('/api/calendar/'+selection.year);
 const catalogJob=useTask();
 const [catalogs,setCatalogs]=useState<Record<string,Catalog>>({});
 const signature=JSON.stringify([selection.year,selection.event,selection.session]);
 const requested=useRef('');
 useEffect(()=>{if(schedule.value?.length&&!schedule.value.some(r=>r.EventName===selection.event)){
  const r=defaultRound(schedule.value);if(r)setSelection({event:r.key,driver:'',driver_b:'',lap:null,lap_b:null})}},[schedule.value]);
 useEffect(()=>{catalogJob.reset()},[signature]);
 useEffect(()=>{if(catalogJob.result&&requested.current===signature)setCatalogs(old=>({...old,[signature]:catalogJob.result}))},[catalogJob.result]);
 const catalog=catalogs[signature]||null;
 // Reconcile the drivers with whichever catalog is active, fresh from a job or reopened from the cache
 // (A → B → A, browser Back): the picker clears drivers when the weekend changes.
 useEffect(()=>{if(!catalog)return;const codes=Object.keys(catalog.drivers);const patch:Partial<Selection>={};
  if(catalog.qualifying_segments===false&&selection.qualifying_part!=='All')patch.qualifying_part='All';
  if(!codes.includes(selection.driver))patch.driver=codes[0]||'';
  if(!codes.includes(selection.driver_b))patch.driver_b=codes.find(c=>c!==(patch.driver??selection.driver))||codes[0]||'';
  if(Object.keys(patch).length)setSelection(patch)},[catalog,selection.driver,selection.driver_b,selection.qualifying_part]);
 const loadCatalog=()=>{if(!selection.event)return;requested.current=signature;catalogJob.start('catalog',selection)};
 return <Context.Provider value={{selection,setSelection,calendar:schedule.value||[],calendarError:schedule.error,calendarLoading:schedule.loading,catalog,loadCatalog,catalogJob}}>{children}</Context.Provider>;
}
