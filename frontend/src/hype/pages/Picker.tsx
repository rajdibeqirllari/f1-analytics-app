import {useEffect,useMemo,useRef,useState} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {useSession} from '../../state';
import {TOOLS} from '../nav';
import {Flag} from '../kit';
import LedMap from '../LedMap';
import YearOdometer from '../YearOdometer';
import StartLights from '../StartLights';
import DriverDuel from '../DriverDuel';
import {toRound,preferredSession,fmt,relative,type Round} from '../weekend';
import {arrivedWithWeekend} from '../boot';

export default function Picker(){
 const {selection:s,setSelection,calendar,calendarLoading,calendarError,catalog,loadCatalog,catalogJob}=useSession();
 const location=useLocation();
 const thisYear=new Date().getFullYear();
 const years=useMemo(()=>Array.from({length:thisYear-2017},(_,i)=>2018+i),[thisYear]);
 const rounds=useMemo(()=>calendar.map(r=>toRound(r)).sort((a,b)=>a.round-b.round),[calendar]);
 const pick=rounds.find(r=>r.key===s.event);
 const [hover,setHover]=useState<string|null>(null);
 const wantLatest=useRef(!arrivedWithWeekend);
 const rail=useRef<HTMLDivElement>(null);
 const duel=useRef<HTMLDivElement>(null);
 const awaitingCatalog=useRef(false);

 useEffect(()=>{const t=document.title;document.title='RACE HYPE — Pick your weekend';
  return()=>{document.title=t}},[]);

 // A new season lands on its most recent completed weekend rather than round one.
 useEffect(()=>{
  if(!wantLatest.current||!rounds.length)return;
  const latest=[...rounds].reverse().find(r=>r.done)||rounds[0];
  if(s.event!==latest.key)setSelection({event:latest.key,session:preferredSession(latest,s.session),driver:'',driver_b:'',lap:null,lap_b:null});
  else wantLatest.current=false;
 },[rounds,s.event]);

 // Keep the chosen round in view on the rail.
 useEffect(()=>{const el=rail.current?.querySelector<HTMLElement>('[aria-selected="true"]');
  const box=rail.current;if(!el||!box)return;
  box.scrollTo({left:el.offsetLeft-box.clientWidth/2+el.clientWidth/2,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'})},[s.event,rounds.length]);

 useEffect(()=>{if(catalog&&awaitingCatalog.current){awaitingCatalog.current=false;
  setTimeout(()=>duel.current?.scrollIntoView({behavior:'smooth',block:'start'}),250)}},[catalog]);

 const chooseRound=(r:Round)=>{if(r.key===s.event)return;
  setSelection({event:r.key,session:preferredSession(r,s.session),driver:'',driver_b:'',lap:null,lap_b:null})};
 const chooseYear=(y:number)=>{wantLatest.current=true;setSelection({year:y,event:'',driver:'',driver_b:'',lap:null,lap_b:null})};
 const onRailKey=(e:React.KeyboardEvent)=>{
  if(!pick)return;const i=rounds.indexOf(pick);
  const next={ArrowRight:i+1,ArrowLeft:i-1,Home:0,End:rounds.length-1}[e.key];
  if(next==null)return;e.preventDefault();const r=rounds[Math.max(0,Math.min(rounds.length-1,next))];chooseRound(r);
  requestAnimationFrame(()=>rail.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.focus({preventScroll:true}));
 };

 const session=pick?.sessions.find(x=>x.code===s.session);
 const canLoad=!!pick&&!!session&&(session.done||!session.start);
 const days=useMemo(()=>{const map=new Map<string,any[]>();
  for(const x of pick?.sessions||[]){const k=x.start?fmt.day(x.start)+' '+fmt.date(x.start):'Weekend';map.set(k,[...(map.get(k)||[]),x])}
  return [...map.entries()]},[pick]);
 const done=rounds.filter(r=>r.done).length;
 const search=location.search;

 return <>
  <h1 className="rhx-sr">Pick a race weekend</h1>
  <main>
   <section className="rhx-hero" aria-label={`${s.year} season`}>
    <div className="rhx-mapwrap">
     <LedMap rounds={rounds} selected={s.event} hovered={hover} onHover={setHover} onSelect={k=>{const r=rounds.find(x=>x.key===k);if(r)chooseRound(r)}} season={s.year}/>
     <div className="rhx-legend" aria-hidden="true"><span><i className="run"/>Run</span><span><i className="next"/>Still to come</span></div>
    </div>
    <div className="rhx-hero-copy">
     <YearOdometer year={s.year} years={years} onChange={chooseYear}/>
     <div className="rhx-season-line">{calendarLoading?'Loading the calendar…':rounds.length?`${rounds.length} rounds, ${done} run so far`:''}</div>
     {calendarError&&<p className="rhx-error" role="alert">The {s.year} calendar didn't load: {calendarError}. Check that the Python engine is running, then pick the season again.</p>}
     <div className="rhx-event" aria-live="polite">
      {pick?<>
       <span className="rhx-event-round">Round {pick.round}{pick.sprint&&<em>Sprint weekend</em>}</span>
       <h2 className="rhx-event-name" key={pick.key} data-long={pick.short.length>10||undefined}>{pick.short}</h2>
       <p className="rhx-event-place"><Flag country={pick.country}/>{[pick.location,pick.country].filter((v,i,a)=>v&&a.indexOf(v)===i).join(', ')}
        {pick.date&&<span>{fmt.date(pick.date)}, {relative(pick.date)}</span>}</p>
      </>:<h2 className="rhx-event-name is-empty">{calendarLoading?'…':'No weekend'}</h2>}
     </div>
    </div>
   </section>

   <div className="rhx-rail" ref={rail} role="listbox" aria-label={`${s.year} rounds`} aria-orientation="horizontal" onKeyDown={onRailKey}>
    {rounds.map(r=>{const on=r.key===s.event;
     return <button type="button" key={r.key} role="option" aria-selected={on} tabIndex={on||(!pick&&r===rounds[0])?0:-1}
      className={'rhx-round '+(on?'on ':'')+(r.done?'':'is-future ')+(hover===r.key?'is-hover':'')}
      onMouseEnter={()=>setHover(r.key)} onMouseLeave={()=>setHover(null)} onClick={()=>chooseRound(r)}>
      <span className="rhx-round-no">{String(r.round).padStart(2,'0')}</span>
      <span className="rhx-round-name"><Flag country={r.country}/>{r.short}</span>
      <span className="rhx-round-date">{fmt.date(r.date)}{r.sprint?', sprint':''}</span>
     </button>})}
   </div>

   <section className="rhx-controls" aria-label="Session">
    {pick&&<div className="rhx-weekend" role="radiogroup" aria-label="Session">
     {days.map(([day,list])=><div className="rhx-day" key={day}><span className="rhx-day-name">{day}</span>
      <div className="rhx-day-sessions">{list.map((x:any)=>{const on=x.code===s.session,future=!!x.start&&!x.done;
       return <button type="button" role="radio" aria-checked={on} key={x.code} disabled={future} className={'rhx-session '+(on?'on ':'')+(x.code==='R'?'is-race':'')}
        onClick={()=>setSelection({session:x.code,driver:'',driver_b:'',lap:null,lap_b:null})}
        title={future?`${x.name} hasn't run yet`:x.name}>
        <b>{x.code}</b><span>{x.name}</span><small>{future?'Not run yet':x.start?fmt.time(x.start):''}</small></button>})}</div></div>)}
    </div>}
    <div className="rhx-go">
     <StartLights label={pick&&session?`${pick.short}, ${session.name}`:'Pick a weekend and session'} disabled={!canLoad}
      busy={catalogJob.busy} progress={catalogJob.job?.progress||0} message={catalogJob.job?.message||''} loaded={!!catalog}
      onLaunch={()=>{awaitingCatalog.current=true;loadCatalog()}} onCancel={catalogJob.cancel}/>
     {(catalogJob.error||catalogJob.job?.error)&&<p className="rhx-error" role="alert">{catalogJob.error||catalogJob.job?.error}</p>}
     {catalog&&!catalogJob.busy&&<p className="rhx-loaded">{Object.keys(catalog.drivers).length} drivers ready{catalog.source?` from ${catalog.source}`:''}. <a href="#rhx-duel-title" onClick={e=>{e.preventDefault();duel.current?.scrollIntoView({behavior:'smooth'})}}>Pick the duel</a></p>}
    </div>
   </section>
  </main>

  <div ref={duel}>{catalog?<DriverDuel/>:null}</div>

  {catalog&&<nav className="rhx-tools" aria-label="Open this weekend in a tool">
   <h2>Take it into</h2>
   <div className="rhx-tool-list">{TOOLS.map(([path,Icon,title,copy])=><Link key={path} to={{pathname:'/hype'+path,search}} className="rhx-tool">
    <Icon aria-hidden="true"/><b>{title}</b><span>{copy}</span></Link>)}</div>
  </nav>}


 </>;
}
