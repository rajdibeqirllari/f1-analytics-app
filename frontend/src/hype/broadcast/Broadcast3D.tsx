/** 3D Broadcast view for the Live and Replay pages (lazy-loaded with Three.js). Camera, driver and position-source
 * choices are this viewer's own (localStorage); nothing here changes the engine's playback. On Replay the page passes
 * its own clock (feed.exact), its scene endpoints (api) and its classification at the displayed instant (timing). */
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {BroadcastEngine,type CameraMode,type Hud} from './engine';
import type {FeedInfo,SceneInfo,TimingRow} from './data';
import './broadcast.css';

type Row={number:string;code:string;position:number;color:string;knocked_out:boolean};
const store={get:(k:string,d:string)=>{try{return localStorage.getItem('rhx-b3d-'+k)??d}catch{return d}},set:(k:string,v:string)=>{try{localStorage.setItem('rhx-b3d-'+k,v)}catch{}}};
const CAMS:[CameraMode,string,string][]=[['pod','TV Pod','Above the airbox, looking over the halo'],['broadcast','Broadcast','Fixed trackside cameras that pan and cut'],['cockpit','Cockpit','Driver\'s eye, inside the halo']];
const hms=(s:number|null)=>s==null||!Number.isFinite(s)?'—':`${Math.floor(s/3600)?Math.floor(s/3600)+':':''}${String(Math.floor(s%3600/60)).padStart(Math.floor(s/3600)?2:1,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;
const utc=(t:number|null)=>t==null?'':new Date(t*1000).toISOString().slice(11,19)+' UTC';
const metres=(m:number)=>m<1000?`${Math.round(m)} m`:`${(m/1000).toFixed(2)} km`;

const LIVE_API={scene:'/api/live/scene',samples:'/api/live/scene/samples'};

export default function Broadcast3D({feed,focus,onFocus,rows,fallback,api=LIVE_API,timing=null}:{feed:FeedInfo;focus:string|null;onFocus:(n:string|null)=>void;rows:Row[];fallback:ReactNode;
 api?:{scene:string;samples:string};timing?:Record<string,TimingRow>|null}){
 const host=useRef<HTMLDivElement>(null),eng=useRef<BroadcastEngine|null>(null);
 const [glErr,setGlErr]=useState('');
 const [mode,setMode]=useState<CameraMode>(()=>(store.get('camera','pod') as CameraMode));
 const [pref,setPref]=useState(()=>store.get('source','auto'));
 const [info,setInfo]=useState<SceneInfo|null>(null),[sceneErr,setSceneErr]=useState(''),[retry,setRetry]=useState(0);
 const [hud,setHud]=useState<Hud|null>(null);

 useEffect(()=>{if(!host.current)return;let e:BroadcastEngine;
  try{e=new BroadcastEngine(host.current,h=>setHud(h))}catch(x){setGlErr('This browser could not start WebGL, so the 3D view is off. The 2D map below still works.');return}
  e.samplesBase=api.samples;eng.current=e;return()=>{e.dispose();eng.current=null}},[]);
 useEffect(()=>{if(eng.current)eng.current.samplesBase=api.samples},[api.samples]);
 useEffect(()=>{eng.current?.setTiming(timing)},[timing]);

 // The scene for this recording and source. Recorded positions load in the background on the engine; poll until ready.
 const fileKey=feed.file+'|'+feed.mode;
 useEffect(()=>{let alive=true,t:any;setSceneErr('');
  const load=async()=>{try{const r=await fetch(`${api.scene}?source=${pref==='estimated'?'estimated':'auto'}`);
    if(!r.ok){let d='';try{d=(await r.json()).detail}catch{d=r.statusText}throw new Error(d)}
    const s:SceneInfo=await r.json();if(!alive)return;
    setInfo(prev=>prev&&prev.key===s.key&&prev.ok===s.ok&&prev.recorded.status===s.recorded.status&&prev.recorded.progress===s.recorded.progress?prev:s);
    if(s.recorded.status==='loading'||s.loading)t=setTimeout(load,1500)}
   catch(e){if(alive){setSceneErr((e as Error).message);t=setTimeout(load,5000)}}};
  load();return()=>{alive=false;clearTimeout(t)}},[fileKey,pref,retry,api.scene]);

 const builtKey=useRef('');
 useEffect(()=>{const e=eng.current;if(!e||!info)return;const k=info.ok?info.key:info.loading?'loading':'none|'+info.error;if(builtKey.current!==k){builtKey.current=k;e.setScene(info,pref==='estimated'?'estimated':'auto')}},[info,pref]);
 useEffect(()=>{eng.current?.setFeed(feed)},[feed]);
 useEffect(()=>{eng.current?.setFocus(focus)},[focus]);
 useEffect(()=>{eng.current?.setMode(mode);store.set('camera',mode)},[mode]);

 const unavailable=glErr||(info&&!info.ok&&!info.loading?(info.error||'No circuit geometry for this session.'):'');
 const t=hud?.timing;const lap=t?(hud!.totalLaps?`${Math.min(hud!.totalLaps,t.laps+1)}/${hud!.totalLaps}`:`${t.laps}`):'—';
 const status=!info||info.loading?'Building the circuit…':hud?.error?hud.error:hud?.buffering?'Loading positions…':
  hud&&hud.flag==='none'&&hud.num?(t?.inPit?`${hud.code} is in the pit lane. ${info.source==='estimated'?'The timing feed has no pit-lane positions, so the car is not drawn.':''}`:t?.retired?`${hud.code} has retired.`:`No position for ${hud.code} at this moment.`):'';
 const recBusy=info?.recorded?.status==='loading';
 const drivers=[...rows].filter(r=>!r.knocked_out).sort((a,b)=>a.position-b.position);

 return <section className="rhx-b3d" aria-label="3D broadcast view">
  <div className={'rhx-b3d-stage'+(unavailable?' is-off':'')}>
   <div ref={host} className="rhx-b3d-canvas"/>
   {unavailable?<div className="rhx-b3d-fallback"><p className="rhx-note">{unavailable} Showing the 2D map instead.
     {info&&!info.ok&&<> <button type="button" className="rhx-link" onClick={()=>setRetry(n=>n+1)}>Try again</button></>}</p>{fallback}</div>
   :<>
    {hud?.num&&<div className="rhx-b3d-card" style={{'--team':hud.color} as React.CSSProperties}>
     <div className="rhx-b3d-who"><b className="pos">{t?.pos?`P${t.pos}`:'—'}</b><b className="code">{hud.code}</b><span>{hud.name}<small>{hud.team}{hud.auto?' · leader (pick a driver in the tower)':''}</small></span></div>
     <dl><div><dt>Lap</dt><dd>{lap}</dd></div><div><dt>Interval</dt><dd>{t?.pos===1?'Leader':t?.interval||'—'}</dd></div><div><dt>Gap</dt><dd>{t?.pos===1?'—':t?.gap||'—'}</dd></div></dl>
     <p className="rhx-b3d-near">{hud.ahead&&<span><i style={{background:hud.ahead.color}}/>Ahead on track <b>{hud.ahead.code}</b> {metres(hud.ahead.m)}</span>}
      {hud.behind&&<span><i style={{background:hud.behind.color}}/>Behind <b>{hud.behind.code}</b> {metres(hud.behind.m)}</span>}</p>
     {hud.flag==='extrapolated'&&info?.source==='recorded'&&<p className="rhx-b3d-warn">Waiting for the next timing update: position projected for a few seconds.</p>}
     {hud.ghosted&&<p className="rhx-b3d-warn">Within a car length of another car: estimated positions can't tell who is where side by side, so the cars are drawn see-through.</p>}
     {hud.flag==='stale'&&<p className="rhx-b3d-warn is-bad">Position is stale: no new {info?.source==='recorded'?'samples':'crossings'} for this car.</p>}
    </div>}
    <div className={'rhx-b3d-source is-'+(info?.source||'none')} title={info?.detail}>
     <b>{info?.label||'3D Broadcast'}</b><small>{info?.session?`${info.session.year||''} ${info.session.meeting} · ${info.session.name}`:''}</small>
     <small className="clock">{hud?.elapsed!=null?feed.exact?`${hms(hud.elapsed)} into the session`:`${hms(hud.elapsed)} into the recording · ${utc(hud.utc)}`:''}</small>
     {recBusy&&<small>Loading recorded positions… {Math.round((info!.recorded.progress||0)*100)}%</small>}
    </div>
    {hud?.cam&&<div className="rhx-b3d-camtag">{hud.cam}{hud.battle&&<> · battle with {hud.battle}</>}</div>}
    {status&&<p className="rhx-b3d-status" role="status">{status}</p>}
    <p className="rhx-b3d-legal">Unofficial fan view, not affiliated with Formula 1. Generic car model.</p>
   </>}
  </div>
  <div className="rhx-b3d-bar">
   <div className="rhx-seg is-inline" role="group" aria-label="Camera">
    {CAMS.map(([k,l,d])=><button type="button" key={k} className={mode===k?'on':''} aria-pressed={mode===k} title={d} disabled={!!unavailable} onClick={()=>setMode(k)}>{l}</button>)}
   </div>
   <label className="rhx-b3d-pick">Driver <select value={focus||''} onChange={e=>onFocus(e.target.value||null)}>
    <option value="">Leader (auto)</option>{drivers.map(r=><option key={r.number} value={r.number}>{r.position<99?`P${r.position} `:''}{r.code}</option>)}</select></label>
   {info?.recorded?.status==='ready'&&<div className="rhx-seg is-inline" role="group" aria-label="Positions">
    {[['auto','Recorded'],['estimated','Estimated']].map(([k,l])=><button type="button" key={k} className={pref===k?'on':''} aria-pressed={pref===k} onClick={()=>{setPref(k);store.set('source',k)}}>{l}</button>)}
   </div>}
   <small className="rhx-b3d-detail">{info?.ok?<>{info.detail}. Circuit: {info.track.source}.</>:sceneErr?`Scene: ${sceneErr}`:''}
    {info?.recorded?.status==='unavailable'&&info.recorded.reason?<> {info.recorded.reason}</>:null}</small>
  </div>
 </section>;
}
