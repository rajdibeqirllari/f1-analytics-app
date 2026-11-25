/** 3D Broadcast view for the Live and Replay pages (lazy-loaded with Three.js). Camera, driver and position-source
 * choices are this viewer's own (localStorage); nothing here changes the engine's playback. On Replay the page passes
 * its own clock (feed.exact), its scene endpoints (api) and its classification at the displayed instant (timing).
 *
 * Fullscreen broadcast: the whole section (canvas + overlays + controls) goes fullscreen, so the renderer, camera,
 * selected driver and clock are untouched. A fixed full-viewport layout is the fallback when the Fullscreen API is not
 * available. In fullscreen: standings tower on the left (with the watched driver folded into it), a transparent live
 * circuit map bottom right, and a team radio card above the map when a clip reaches the displayed race clock. */
import {useCallback,useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {BroadcastEngine,type CameraMode,type Hud} from './engine';
import type {FeedInfo,SceneInfo,TimingRow} from './data';
import {claimRadio,pauseRadio,playRadio,radioPlaying,stopRadio} from './audioBus';
import './broadcast.css';

type Row={number:string;code:string;position:number;color:string;knocked_out:boolean};
/** One row of the broadcast tower as the page knows it (the engine's timing at the displayed instant overrides
 * position / interval / pit / out where it has them). `id` = the engine's driver key (Live: number, Replay: code). */
export type TowerRow={id:string;code:string;color:string;pos:number|null;interval:string|null;tyre:string|null;pit:boolean;out:boolean;lapped?:string|null};
export type TowerInfo={title:string;lap:number|null;total:number|null;rows:TowerRow[];estimated?:boolean};
type RadioEvent={id:string;t:number;num:string;code:string;color:string;url:string|null;transcript:string};

const store={get:(k:string,d:string)=>{try{return localStorage.getItem('rhx-b3d-'+k)??d}catch{return d}},set:(k:string,v:string)=>{try{localStorage.setItem('rhx-b3d-'+k,v)}catch{}}};
const radioMode=()=>{try{return localStorage.getItem('rhx-comm-radio-mode')==='real'?'real':'safe'}catch{return 'safe'}};
const CAMS:[CameraMode,string,string][]=[['pod','TV Pod','Above the airbox, looking over the halo'],['broadcast','Broadcast','Fixed trackside cameras that pan and cut'],['cockpit','Cockpit','Driver\'s eye, inside the halo']];
const hms=(s:number|null)=>s==null||!Number.isFinite(s)?'—':`${Math.floor(s/3600)?Math.floor(s/3600)+':':''}${String(Math.floor(s%3600/60)).padStart(Math.floor(s/3600)?2:1,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;
const utc=(t:number|null)=>t==null?'':new Date(t*1000).toISOString().slice(11,19)+' UTC';
const metres=(m:number)=>m<1000?`${Math.round(m)} m`:`${(m/1000).toFixed(2)} km`;
const TYRE_LETTER:Record<string,string>={SOFT:'S',MEDIUM:'M',HARD:'H',INTERMEDIATE:'I',WET:'W',S:'S',M:'M',H:'H',I:'I',W:'W'};
const tyreOf=(c:string|null)=>c?TYRE_LETTER[c.toUpperCase()]||'?':null;

const LIVE_API={scene:'/api/live/scene',samples:'/api/live/scene/samples'};

export default function Broadcast3D({feed,focus,onFocus,rows,fallback,api=LIVE_API,timing=null,tower=null,mapRotation=0,radioUrl}:{feed:FeedInfo;focus:string|null;onFocus:(n:string|null)=>void;rows:Row[];fallback:ReactNode;
 api?:{scene:string;samples:string};timing?:Record<string,TimingRow>|null;tower?:TowerInfo|null;mapRotation?:number;radioUrl?:string}){
 const host=useRef<HTMLDivElement>(null),eng=useRef<BroadcastEngine|null>(null),section=useRef<HTMLElement>(null),mapCanvas=useRef<HTMLCanvasElement>(null);
 const [glErr,setGlErr]=useState('');
 const [mode,setMode]=useState<CameraMode>(()=>(store.get('camera','pod') as CameraMode));
 const [pref,setPref]=useState(()=>store.get('source','auto'));
 const [info,setInfo]=useState<SceneInfo|null>(null),[sceneErr,setSceneErr]=useState(''),[retry,setRetry]=useState(0);
 const [hud,setHud]=useState<Hud|null>(null);
 const [preview,setPreview]=useState(()=>store.get('preview-models','0')==='1');
 const [lines,setLines]=useState<'recon'|'raw'>(()=>store.get('lines','recon')==='raw'?'raw':'recon');
 const [fs,setFs]=useState<'off'|'native'|'fallback'>('off');
 const [active,setActive]=useState(true);
 const [field,setField]=useState<Record<string,TimingRow>>({});

 useEffect(()=>{if(!host.current)return;let e:BroadcastEngine;
  try{e=new BroadcastEngine(host.current,h=>{setHud(h);setField(e.fieldTiming())})}catch(x){setGlErr('This browser could not start WebGL, so the 3D view is off. The 2D map below still works.');return}
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
 useEffect(()=>{eng.current?.setPreview(preview);store.set('preview-models',preview?'1':'0')},[preview]);
 useEffect(()=>{eng.current?.setLines(lines);store.set('lines',lines)},[lines]);

 // ---------------------------------------------------------------- fullscreen
 const isFs=fs!=='off';
 useEffect(()=>{const on=()=>{const el=document.fullscreenElement;setFs(f=>el===section.current?'native':f==='native'?'off':f)};
  document.addEventListener('fullscreenchange',on);return()=>document.removeEventListener('fullscreenchange',on)},[]);
 const enterFs=useCallback(async()=>{const el=section.current;if(!el)return;
  // Some embedded browsers never settle the request (or refuse it): confirm within 1.2 s, else use the fallback layout.
  try{if(el.requestFullscreen&&document.fullscreenEnabled!==false){
   await Promise.race([el.requestFullscreen({navigationUI:'hide'} as FullscreenOptions).catch(()=>{}),new Promise(r=>setTimeout(r,1200))]);
   if(document.fullscreenElement===el){setFs('native');return}}}catch{/* fall back below */}
  setFs('fallback')},[]);
 const exitFs=useCallback(()=>{if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});setFs('off')},[]);
 useEffect(()=>{if(fs!=='fallback')return;const k=(e:KeyboardEvent)=>{if(e.key==='Escape')exitFs()};window.addEventListener('keydown',k);
  document.documentElement.classList.add('rhx-b3d-fs-lock');return()=>{window.removeEventListener('keydown',k);document.documentElement.classList.remove('rhx-b3d-fs-lock')}},[fs,exitFs]);
 // controls fade while watching, come back on pointer movement or keyboard focus
 const idle=useRef<any>(0);
 const wake=useCallback(()=>{setActive(true);clearTimeout(idle.current);idle.current=setTimeout(()=>setActive(false),2600)},[]);
 useEffect(()=>{if(isFs)wake();else{setActive(true);clearTimeout(idle.current)}return()=>clearTimeout(idle.current)},[isFs,wake]);
 // map canvas only drawn in fullscreen
 useEffect(()=>{eng.current?.setMap(isFs?mapCanvas.current:null,mapRotation)},[isFs,mapRotation,info]);

 // ---------------------------------------------------------------- tower (classification at the displayed instant)
 const towerRows=useMemo(()=>{if(!tower)return [];
  return tower.rows.map(r=>{const t=field[r.id];
   const pos=t?.pos??r.pos,pit=t?(t.inPit||r.pit):r.pit,out=t?(t.retired||t.out||r.out):r.out;
   let interval=r.interval;if(t&&t.interval!=null&&!feed.exact)interval=t.interval;   // Live: the feed's own interval at this instant
   return {...r,pos,pit,out,interval}}).sort((a,b)=>Number(a.out)-Number(b.out)||(a.pos??99)-(b.pos??99))},[tower,field,feed.exact]);
 const lapNow=useMemo(()=>{if(!tower)return null;if(tower.lap!=null&&feed.exact)return tower.lap;
  const lead=Object.values(field).find(t=>t.pos===1);return lead?Math.min(tower.total||999,lead.laps+1):tower.lap},[tower,field,feed.exact]);

 // ---------------------------------------------------------------- team radio card (displayed race clock)
 const [events,setEvents]=useState<RadioEvent[]>([]);
 useEffect(()=>{setEvents([]);if(!radioUrl)return;let alive=true,tm:any;
  const load=async()=>{try{const r=await fetch(radioUrl);if(r.ok){const d=await r.json();if(alive){setEvents(d.events||[]);if(d.loading)tm=setTimeout(load,3000)}}}catch{/* quiet: no radio */}
   if(alive&&!feed.exact)tm=setTimeout(load,1000)};   // Live (follow or replay of a recording): the feed only knows clips it has passed
  load();return()=>{alive=false;clearTimeout(tm)}},[radioUrl,fileKey]);
 const clockNow=hud?.utc??null;
 const card=useMemo(()=>{if(clockNow==null||!events.length)return null;let cur:RadioEvent|null=null;
  for(const e of events){if(e.t>clockNow)break;const read=Math.min(14,6+(e.transcript?e.transcript.split(/\s+/).length/3:0));if(clockNow-e.t<read)cur=e}
  return cur},[events,clockNow]);
 const playedFor=useRef('');
 useEffect(()=>{   // one play per event, only when it is fresh at normal speed, never while paused or after a seek past it
  if(!card){if(radioPlaying())stopRadio();return}
  if(radioMode()!=='real'||!card.url||feed.paused||(feed.speed||1)>2.01)return;
  if(playedFor.current===card.id)return;
  if(clockNow!=null&&clockNow-card.t>2)return;
  playedFor.current=card.id;if(claimRadio(card.url))playRadio(card.url)},[card,feed.paused,feed.speed,clockNow]);
 useEffect(()=>{pauseRadio(!!feed.paused)},[feed.paused]);
 useEffect(()=>()=>stopRadio(),[fileKey]);
 const mates=useMemo(()=>Object.fromEntries((tower?.rows||[]).map(r=>[r.code,r])),[tower]);

 const unavailable=glErr||(info&&!info.ok&&!info.loading?(info.error||'No circuit geometry for this session.'):'');
 const t=hud?.timing;const lap=t?(hud!.totalLaps?`${Math.min(hud!.totalLaps,t.laps+1)}/${hud!.totalLaps}`:`${t.laps}`):'—';
 const status=!info||info.loading?'Building the circuit…':hud?.error?hud.error:hud?.buffering?'Loading positions…':
  hud&&hud.flag==='none'&&hud.num?(t?.inPit?`${hud.code} is in the pit lane. ${info.source==='estimated'?'The timing feed has no pit-lane positions, so the car is not drawn.':''}`:t?.retired?`${hud.code} has retired.`:`No position for ${hud.code} at this moment.`):'';
 const recBusy=info?.recorded?.status==='loading';
 const drivers=[...rows].filter(r=>!r.knocked_out).sort((a,b)=>a.position-b.position);
 const showPreview=!!(hud?.models.preview&&hud.models.previewUsed>0);
 const watched=hud?.num||null;

 return <section ref={section} className={'rhx-b3d'+(isFs?' is-fs':'')+(fs==='fallback'?' is-fs-fallback':'')+(isFs&&!active?' is-idle':'')} aria-label="3D broadcast view"
   onPointerMove={isFs?wake:undefined} onKeyDown={isFs?wake:undefined} onFocus={isFs?wake:undefined}>
  <div className={'rhx-b3d-stage'+(unavailable?' is-off':'')}>
   <div ref={host} className="rhx-b3d-canvas"/>
   {unavailable?<div className="rhx-b3d-fallback"><p className="rhx-note">{unavailable} Showing the 2D map instead.
     {info&&!info.ok&&<> <button type="button" className="rhx-link" onClick={()=>setRetry(n=>n+1)}>Try again</button></>}</p>{fallback}</div>
   :<>
    {!isFs&&hud?.num&&<div className="rhx-b3d-card" style={{'--team':hud.color} as React.CSSProperties}>
     <div className="rhx-b3d-who"><b className="pos">{t?.pos?`P${t.pos}`:'—'}</b><b className="code">{hud.code}</b><span>{hud.name}<small>{hud.team}{hud.auto?' · leader (pick a driver in the tower)':''}</small></span></div>
     <dl><div><dt>Lap</dt><dd>{lap}</dd></div><div><dt>Interval</dt><dd>{t?.pos===1?'Leader':t?.interval||'—'}</dd></div><div><dt>Gap</dt><dd>{t?.pos===1?'—':t?.gap||'—'}</dd></div></dl>
     <p className="rhx-b3d-near">{hud.ahead&&<span><i style={{background:hud.ahead.color}}/>Ahead on track <b>{hud.ahead.code}</b> {metres(hud.ahead.m)}</span>}
      {hud.behind&&<span><i style={{background:hud.behind.color}}/>Behind <b>{hud.behind.code}</b> {metres(hud.behind.m)}</span>}</p>
     {hud.flag==='extrapolated'&&info?.source==='recorded'&&<p className="rhx-b3d-warn">Waiting for the next timing update: position projected for a few seconds.</p>}
     {hud.lines.mode==='recon'&&hud.lines.selected==='recon'&&<p className="rhx-b3d-note">{hud.lines.grid?'Grid slot reconstructed from the starting order.':'Side-by-side placement reconstructed; order, gaps and timing are recorded.'}</p>}
     {hud.lines.mode==='recon'&&hud.lines.uncertain&&<p className="rhx-b3d-warn">Too little road width here to separate these cars: their order and gaps are recorded, the overlap is not.</p>}
     {hud.ghosted&&<p className="rhx-b3d-warn">Within a car length of another car: estimated positions can't tell who is where side by side, so the cars are drawn see-through.</p>}
     {hud.flag==='stale'&&<p className="rhx-b3d-warn is-bad">Position is stale: no new {info?.source==='recorded'?'samples':'crossings'} for this car.</p>}
    </div>}
    {isFs&&tower&&<aside className="rhx-bt" aria-label="Standings">
     <header><b>{tower.title}</b><span>{lapNow!=null?<>LAP <em>{lapNow}</em>{tower.total?<>/{tower.total}</>:null}</>:null}</span></header>
     <ol>{towerRows.map(r=>{const on=r.id===watched;const tl=tyreOf(r.tyre);
      const int=r.out?'OUT':r.pit?'PIT':r.pos===1?'LEADER':r.lapped||r.interval||'—';
      return <li key={r.id} className={(on?'on ':'')+(r.out?'is-out ':'')+(r.pit?'is-pit':'')} style={{'--team':r.color} as React.CSSProperties}>
       <button type="button" onClick={()=>onFocus(r.id)} aria-pressed={on} title={`Ride with ${r.code}`}>
        <span className="p">{r.pos??'–'}</span><i/><b>{r.code}</b><span className="int">{int}</span>
        <span className={'ty t-'+(tl||'x')} title={r.tyre||'Tyre unknown'}>{tl||'–'}</span></button>
       {on&&hud&&<div className="more"><span>{hud.name}</span><small>{hud.team}{t?.gap&&t.pos!==1?` · gap ${t.gap}`:''}{hud.ahead?` · ${hud.ahead.code} ${metres(hud.ahead.m)} ahead`:''}</small></div>}
      </li>})}</ol>
     {tower.estimated&&<footer>Intervals estimated from positions</footer>}
    </aside>}
    {isFs&&<canvas ref={mapCanvas} className="rhx-bmap" aria-label="Live circuit map"/>}
    {isFs&&card&&<div className="rhx-bradio" role="status" style={{'--team':card.color||mates[card.code]?.color||'#888'} as React.CSSProperties} key={card.id}>
     <header>TEAM RADIO</header><div className="who"><i/><b>{card.code}</b><span>{(info?.drivers?.[card.num]||info?.drivers?.[card.code])?.name||''}</span></div>
     <p>{radioMode()==='real'&&card.transcript?`“${card.transcript}”`:`${card.code} on the radio to the team`}{radioMode()==='real'&&radioPlaying(card.url||undefined)?' ▶':''}</p>
    </div>}
    <div className={'rhx-b3d-source is-'+(info?.source||'none')} title={info?.detail}>
     <b>{info?.label||'3D Broadcast'}</b>{!isFs&&<small>{info?.session?`${info.session.year||''} ${info.session.meeting} · ${info.session.name}`:''}</small>}
     {hud?.lines.available&&<small className="lines">{hud.lines.mode==='recon'?<>Timing &amp; order: {info?.source==='recorded'?'recorded':'timing feed'} · side-by-side: <b>reconstructed</b>{hud.lines.uncertainNow?` · ${hud.lines.uncertainNow} uncertain`:''}</>:'Raw positions (no reconstruction)'}</small>}
     {!isFs&&<small className="clock">{hud?.elapsed!=null?feed.exact?`${hms(hud.elapsed)} into the session`:`${hms(hud.elapsed)} into the recording · ${utc(hud.utc)}`:''}</small>}
     {recBusy&&<small>Loading recorded positions… {Math.round((info!.recorded.progress||0)*100)}%</small>}
    </div>
    {showPreview&&<div className="rhx-b3d-preview-tag" role="note">
     Preview · {hud!.models.season} chassis &amp; liveries for {hud!.models.constructors} constructors on {info?.session?.year||'this'} session data
     {hud!.models.mapped.length?<> · {hud!.models.mapped.join(', ')}</>:null}{hud!.models.generic.length?<> · generic: {hud!.models.generic.join(', ')}</>:null} · numbers from this session</div>}
    {hud?.cam&&<div className="rhx-b3d-camtag">{hud.cam}{hud.battle&&<> · battle with {hud.battle}</>}</div>}
    {status&&<p className="rhx-b3d-status" role="status">{status}</p>}
    <p className="rhx-b3d-legal">Unofficial fan view, not affiliated with Formula 1. {hud?.models.count?`Cars modelled from public photos and launch material; sponsor names shown as wordmarks, official logos not reproduced.${hud.models.generic.length?' Teams without a model use the generic car.':''}`:'Generic car model.'}
     {hud?.venue?.status==='ready'?' Circuit modelled from OpenStreetMap (© OpenStreetMap contributors) and FIA data.':''}</p>
    {!unavailable&&(isFs?<button type="button" className="rhx-b3d-fsbtn is-exit" onClick={exitFs} aria-label="Exit fullscreen broadcast" title="Exit fullscreen (Esc)">✕ Exit fullscreen</button>
     :<button type="button" className="rhx-b3d-fsbtn" onClick={enterFs} aria-label="Fullscreen broadcast" title="Fullscreen broadcast: tower, live map and team radio over the picture">⛶ Fullscreen broadcast</button>)}
   </>}
  </div>
  <div className="rhx-b3d-bar">
   <div className="rhx-seg is-inline" role="group" aria-label="Camera">
    {CAMS.map(([k,l,d])=><button type="button" key={k} className={mode===k?'on':''} aria-pressed={mode===k} title={d} disabled={!!unavailable} onClick={()=>setMode(k)}>{l}</button>)}
   </div>
   <label className="rhx-b3d-pick">Driver <select value={focus||''} onChange={e=>onFocus(e.target.value||null)}>
    <option value="">Leader (auto)</option>{drivers.map(r=><option key={r.number} value={r.number}>{r.position<99?`P${r.position} `:''}{r.code}</option>)}</select></label>
   {!isFs&&info?.recorded?.status==='ready'&&<div className="rhx-seg is-inline" role="group" aria-label="Positions">
    {[['auto','Recorded'],['estimated','Estimated']].map(([k,l])=><button type="button" key={k} className={pref===k?'on':''} aria-pressed={pref===k} onClick={()=>{setPref(k);store.set('source',k)}}>{l}</button>)}
   </div>}
   <div className="rhx-seg is-inline" role="group" aria-label="Car placement">
    {([['recon','Reconstructed racing lines','Separates cars the feed puts on one line (lateral placement only; timing, order and gaps unchanged)'],['raw','Raw positions','Exactly what the position source says']] as const).map(([k,l,d])=>
     <button type="button" key={k} className={lines===k?'on':''} aria-pressed={lines===k} title={d} onClick={()=>setLines(k)}>{isFs?(k==='recon'?'Reconstructed':'Raw'):l}</button>)}
   </div>
   {!isFs&&hud?.models.previewAvailable&&<button type="button" className={'rhx-b3d-previewbtn'+(preview?' on':'')} aria-pressed={preview} onClick={()=>setPreview(v=>!v)}
    title="Show the 2026 chassis and liveries of every constructor on this session's cars (renamed teams mapped, e.g. Kick Sauber to Audi), labelled as a preview">Preview 2026 cars</button>}
   {!isFs&&<small className="rhx-b3d-detail">{info?.ok?<>{info.detail}. Circuit: {info.track.source}.</>:sceneErr?`Scene: ${sceneErr}`:''}
    {hud?.venue&&<> Venue: {hud.venue.status==='loading'?'loading the circuit model…':hud.venue.status==='ready'&&hud.venue.align?`${hud.venue.name} model, ${hud.venue.align.mode==='exact'?'placed from the session frame':'fitted to the session'} (median ${hud.venue.align.median.toFixed(1)} m to this lap)`:hud.venue.why}.</>}
    {info?.recorded?.status==='unavailable'&&info.recorded.reason?<> {info.recorded.reason}</>:null}</small>}
  </div>
 </section>;
}
