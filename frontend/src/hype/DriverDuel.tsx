import {useState} from 'react';
import {useSession} from '../state';
import {teamColor,type Driver} from '../api';

type Slot='driver'|'driver_b';
/** A plain single-seater silhouette in the team colour: no liveries, sponsor logos, F1 renders or driver photos
 * (those belong to F1 and the teams, and were hotlinked from formula1.com). Safe for streams. */
function Silhouette(){
 return <svg className="rhx-side-livery" viewBox="0 0 400 110" aria-hidden="true" focusable="false">
  <path fill="currentColor" d="M18 70h40l16-14h70l26-18h70l28 18h56l40 10v10l-30 4H310a26 26 0 0 0-50 0H150a26 26 0 0 0-50 0H40l-22-6z"/>
  <path fill="currentColor" opacity=".55" d="M6 54h46v10H6zM348 66h44v14h-44z"/>
  <circle cx="125" cy="90" r="20" fill="#0b1015"/><circle cx="285" cy="90" r="20" fill="#0b1015"/>
  <circle cx="125" cy="90" r="9" fill="currentColor" opacity=".4"/><circle cx="285" cy="90" r="9" fill="currentColor" opacity=".4"/></svg>;
}

function Side({slot,code,entry,active,onActivate}:{slot:Slot;code:string;entry?:Driver;active:boolean;onActivate:()=>void;year:number}){
 const {selection:s,setSelection,catalog}=useSession();
 const lapKey=slot==='driver'?'lap':'lap_b';
 const laps=entry?(entry.segments?.[s.qualifying_part]||entry.laps||[]):[];
 return <div className={'rhx-side '+(slot==='driver'?'is-a ':'is-b ')+(active?'is-active':'')} style={{'--team':teamColor(entry?.color)} as React.CSSProperties}>
  <button type="button" className="rhx-side-pick" onClick={onActivate} aria-pressed={active}>
   <span className="rhx-side-slot">{slot==='driver'?'Left side':'Right side'}{active?' · choosing':''}</span>
   <strong className="rhx-side-code">{code||'—'}</strong>
   <span className="rhx-side-name">{entry?.name||'Choose a driver below'}</span>
   <span className="rhx-side-team">{entry?.team}</span>
  </button>
  {entry&&<Silhouette/>}
  {entry&&<div className="rhx-laps" role="radiogroup" aria-label={`${code} lap`}>
   <button type="button" role="radio" aria-checked={!s[lapKey]} className={!s[lapKey]?'on':''} onClick={()=>setSelection({[lapKey]:null})}>
    {catalog?.source==='OpenF1'?'Fastest timed':'Fastest'}</button>
   {laps.map(n=><button type="button" role="radio" aria-checked={s[lapKey]===n} key={n} className={s[lapKey]===n?'on':''} onClick={()=>setSelection({[lapKey]:n})}>L{n}</button>)}
  </div>}
 </div>;
}

export default function DriverDuel(){
 const {selection:s,setSelection,catalog}=useSession();
 const [active,setActive]=useState<Slot>('driver');
 if(!catalog)return null;
 const drivers=Object.entries(catalog.drivers);
 // Team-mates sit together, like the grid order on a timing screen.
 const teams=new Map<string,[string,Driver][]>();
 for(const d of drivers){const t=d[1].team||'Other';teams.set(t,[...(teams.get(t)||[]),d])}
 const choose=(code:string)=>{
  const other:Slot=active==='driver'?'driver_b':'driver';
  const patch:any={[active]:code,[active==='driver'?'lap':'lap_b']:null};
  if(s[other]===code){patch[other]=s[active];patch[other==='driver'?'lap':'lap_b']=null}
  setSelection(patch);setActive(other);
 };
 const segments=['Q','SQ'].includes(s.session)&&catalog.qualifying_segments!==false;
 return <section className="rhx-duel" aria-labelledby="rhx-duel-title">
  <div className="rhx-duel-head">
   <h2 id="rhx-duel-title">Pick the duel</h2>
   <p>Tap a driver for the {active==='driver'?'left':'right'} side. Every tool you open next uses this pair.</p>
   {segments&&<div className="rhx-seg" role="radiogroup" aria-label="Qualifying segment">{['All','Q1','Q2','Q3'].map(p=>
    <button type="button" key={p} role="radio" aria-checked={s.qualifying_part===p} className={s.qualifying_part===p?'on':''} onClick={()=>setSelection({qualifying_part:p,lap:null,lap_b:null})}>{p==='All'?'All of qualifying':p}</button>)}</div>}
  </div>
  {catalog.notice&&<p className="rhx-notice">{catalog.notice} Timing, replays and engineering charts still need FastF1.</p>}
  <div className="rhx-vs">
   <Side slot="driver" code={s.driver} entry={catalog.drivers[s.driver]} active={active==='driver'} onActivate={()=>setActive('driver')} year={s.year}/>
   <div className="rhx-vs-mark" aria-hidden="true">VS</div>
   <Side slot="driver_b" code={s.driver_b} entry={catalog.drivers[s.driver_b]} active={active==='driver_b'} onActivate={()=>setActive('driver_b')} year={s.year}/>
  </div>
  <div className="rhx-grid" role="list">
   {[...teams.entries()].map(([team,list])=><div className="rhx-team" role="listitem" key={team} style={{'--team':teamColor(list[0][1].color)} as React.CSSProperties}>
    <span className="rhx-team-name">{team}</span>
    {list.map(([code,d])=>{const side=s.driver===code?'A':s.driver_b===code?'B':'';
     const none=!d.laps?.length;
     return <button type="button" key={code} disabled={none} title={none?`${d.name} has no timed lap in this session${d.status?` (${d.status})`:''}`:undefined} className={'rhx-tile '+(side?'is-'+side.toLowerCase():'')+(none?' is-none':'')} onClick={()=>choose(code)} aria-label={`${d.name}, ${d.team}${none?', no timed lap':''}${side?`, on the ${side==='A'?'left':'right'} side`:''}`}>
      <b>{code}</b><span>{none?(d.status||'No lap'):d.name.split(' ').slice(-1)[0]}</span>{side&&<i>{side==='A'?'L':'R'}</i>}
     </button>})}
   </div>)}
  </div>
 </section>;
}

/** Compact driver picker for tool pages: one or two side cards, laps, and the grid on demand. */
export function DuelBar({pair=true,laps=true}:{pair?:boolean;laps?:boolean}){
 const {selection:s,setSelection,catalog}=useSession();
 const [open,setOpen]=useState<Slot|null>(null);
 if(!catalog)return null;
 const slots:Slot[]=pair?['driver','driver_b']:['driver'];
 const choose=(code:string)=>{if(!open)return;const other:Slot=open==='driver'?'driver_b':'driver';
  const patch:any={[open]:code,[open==='driver'?'lap':'lap_b']:null};
  if(pair&&s[other]===code){patch[other]=s[open];patch[other==='driver'?'lap':'lap_b']=null}
  setSelection(patch);setOpen(pair&&open==='driver'&&!s.driver_b?'driver_b':null)};
 const segments=laps&&['Q','SQ'].includes(s.session)&&catalog.qualifying_segments!==false;
 const teams=new Map<string,[string,Driver][]>();
 for(const d of Object.entries(catalog.drivers)){const t=d[1].team||'Other';teams.set(t,[...(teams.get(t)||[]),d])}
 return <div className="rhx-duelbar">
  {segments&&<div className="rhx-seg is-inline" role="radiogroup" aria-label="Qualifying segment">{['All','Q1','Q2','Q3'].map(p=>
   <button type="button" key={p} role="radio" aria-checked={s.qualifying_part===p} className={s.qualifying_part===p?'on':''} onClick={()=>setSelection({qualifying_part:p,lap:null,lap_b:null})}>{p==='All'?'All of qualifying':p}</button>)}</div>}
  <div className={'rhx-duelbar-sides '+(pair?'':'is-single')}>
   {slots.map((slot,i)=>{const code=s[slot],d=catalog.drivers[code];const lapKey=slot==='driver'?'lap':'lap_b';
    const list=d?(d.segments?.[s.qualifying_part]||d.laps||[]):[];
    return <div key={slot} className={'rhx-mini '+(open===slot?'is-open':'')} style={{'--team':teamColor(d?.color)} as React.CSSProperties}>
     <button type="button" className="rhx-mini-pick" aria-expanded={open===slot} onClick={()=>setOpen(open===slot?null:slot)}>
      <strong>{code||'—'}</strong><span><b>{d?.name||'Choose a driver'}</b><small>{d?.team}</small></span><em>{open===slot?'Close':'Change'}</em>
     </button>
     {laps&&d&&<div className="rhx-laps is-mini" role="radiogroup" aria-label={`${code} lap`}>
      <button type="button" role="radio" aria-checked={!s[lapKey]} className={!s[lapKey]?'on':''} onClick={()=>setSelection({[lapKey]:null})}>{catalog.source==='OpenF1'?'Fastest timed':'Fastest'}</button>
      {list.map(n=><button type="button" role="radio" aria-checked={s[lapKey]===n} key={n} className={s[lapKey]===n?'on':''} onClick={()=>setSelection({[lapKey]:n})}>L{n}</button>)}
     </div>}
     {pair&&i===0&&<span className="rhx-mini-vs" aria-hidden="true">VS</span>}
    </div>})}
  </div>
  {open&&<div className="rhx-grid is-drawer">{[...teams.entries()].map(([team,list])=><div className="rhx-team" key={team} style={{'--team':teamColor(list[0][1].color)} as React.CSSProperties}>
   <span className="rhx-team-name">{team}</span>
   {list.map(([code,d])=>{const side=s.driver===code?'A':pair&&s.driver_b===code?'B':'';
    const none=!d.laps?.length;
    return <button type="button" key={code} disabled={none} className={'rhx-tile '+(side?'is-'+side.toLowerCase():'')+(none?' is-none':'')} onClick={()=>choose(code)}>
     <b>{code}</b><span>{none?(d.status||'No lap'):d.name.split(' ').slice(-1)[0]}</span>{side&&<i>{side==='A'?'L':'R'}</i>}</button>})}
  </div>)}</div>}
  {catalog.notice&&<p className="rhx-notice">{catalog.notice}</p>}
 </div>;
}
