import {createContext,useContext,useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {useSearchParams} from 'react-router-dom';
import {post,request,type Selection,type Catalog,type Job} from './api';

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

export function useTask(storageKey?:string){
 const [job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[submitting,setSubmitting]=useState(false);
 const [id,setId]=useState<string|null>(()=>storageKey?sessionStorage.getItem(storageKey):null);
 const version=useRef(0);
 useEffect(()=>{if(storageKey){if(id)sessionStorage.setItem(storageKey,id);else sessionStorage.removeItem(storageKey)}},[id,storageKey]);
 useEffect(()=>{
  if(!id)return;let active=true;let timer:ReturnType<typeof setTimeout>;
  const poll=async()=>{try{const data=await request<Job>('/api/jobs/'+id);if(!active)return;setJob(data);
    if(['queued','running','building','rendering'].includes(data.status))timer=setTimeout(poll,1000);
   }catch(e){if(active){setError((e as Error).message);setId(null)}}};poll();
  return()=>{active=false;clearTimeout(timer)};
 },[id]);
 const start=async(kind:string,selection:Selection,options:Record<string,any>={})=>{
  const generation=++version.current;setSubmitting(true);setError('');setJob(null);setId(null);
  try{const actualSelection=options.source==='Upload CSV'?{...selection,event:selection.event||'Uploaded telemetry'}:selection;
   const data=await post<{id:string}>('/api/jobs',{kind,selection:actualSelection,options});if(version.current===generation)setId(data.id)}
  catch(e){if(version.current===generation)setError((e as Error).message)}finally{if(version.current===generation)setSubmitting(false)};
 };
 const reset=()=>{version.current++;setId(null);setJob(null);setError('');setSubmitting(false)};
 return {job,error,start,reset,id,busy:submitting||!!(id&&!job)||!!job&&['queued','running','building','rendering'].includes(job.status),
  cancel:async()=>{if(id)await post('/api/jobs/'+id+'/cancel',{});},result:job?.status==='complete'?job.result:null};
}

export function SessionProvider({children}:{children:ReactNode}){
 const [params,setParams]=useSearchParams();
 const selection=useMemo(()=>{const next={...saved};for(const [key,val] of params){if(key in initial)(next as any)[key]=['year','lap','lap_b'].includes(key)?(val?Number(val):null):val;}return next as Selection},[params]);
 const setSelection=(patch:Partial<Selection>)=>setParams(previous=>{const next=new URLSearchParams(previous);for(const [key,value] of Object.entries(patch))next.set(key,value==null?'':String(value));return next},{replace:true});
 useEffect(()=>{localStorage.setItem('rh-session-v1',JSON.stringify(selection))},[selection]);
 const schedule=useResource<any[]>('/api/calendar/'+selection.year);
 const catalogJob=useTask();
 const [catalogs,setCatalogs]=useState<Record<string,Catalog>>({});
 const signature=JSON.stringify([selection.year,selection.event,selection.session]);
 const requested=useRef('');
 useEffect(()=>{if(schedule.value?.length&&!schedule.value.some(r=>r.EventName===selection.event))setSelection({event:schedule.value[0].EventName,driver:'',driver_b:'',lap:null,lap_b:null})},[schedule.value]);
 useEffect(()=>{catalogJob.reset()},[signature]);
 useEffect(()=>{if(catalogJob.result&&requested.current===signature){setCatalogs(old=>({...old,[signature]:catalogJob.result}));
   const codes=Object.keys(catalogJob.result.drivers);const patch:Partial<Selection>={};
   if(catalogJob.result.qualifying_segments===false)patch.qualifying_part='All';
   if(!codes.includes(selection.driver))patch.driver=codes[0]||'';
   if(!codes.includes(selection.driver_b))patch.driver_b=codes[1]||codes[0]||'';
   if(Object.keys(patch).length)setSelection(patch);
 }},[catalogJob.result]);
 const loadCatalog=()=>{if(!selection.event)return;requested.current=signature;catalogJob.start('catalog',selection)};
 return <Context.Provider value={{selection,setSelection,calendar:schedule.value||[],calendarError:schedule.error,calendarLoading:schedule.loading,catalog:catalogs[signature]||null,loadCatalog,catalogJob}}>{children}</Context.Provider>;
}
