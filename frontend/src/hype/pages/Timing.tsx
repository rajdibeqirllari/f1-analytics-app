import {useEffect,useState} from 'react';
import {useSession,useTask} from '../../state';
import {clock,teamColor} from '../../api';
import {PageHead,Action,JobBar,Blank,Note} from '../kit';

const TYRE:Record<string,string>={SOFT:'S',MEDIUM:'M',HARD:'H',INTERMEDIATE:'I',WET:'W'};
const FLAG:Record<string,string>={GREEN:'#2bd46b',CLEAR:'#2bd46b',YELLOW:'#ffd23f','DOUBLE YELLOW':'#ffd23f',RED:'#ff463b',BLUE:'#3ea7ff',CHEQUERED:'#eef2f5',BLACK:'#000','BLACK AND WHITE':'#8a98a7'};

export default function Timing(){
 const {selection:s}=useSession();const task=useTask(),[selected,setSelected]=useState('');
 useEffect(()=>task.reset(),[s.year,s.event,s.session]);
 const r=task.result;const rows:any[]=r?.rows||[];
 const driver=rows.find(x=>x.driver===selected)||rows[0];
 const best=(k:string)=>Math.min(...rows.map(x=>x[k]??Infinity));
 const track:number[][]=r?.track||[];const xs=track.map(p=>p[0]),ys=track.map(p=>p[1]);
 const minx=Math.min(...xs),miny=Math.min(...ys),w=Math.max(...xs)-minx,h=Math.max(...ys)-miny;
 const cell=(row:any,k:string)=><td className={row[k]!=null&&row[k]===best(k)?'is-fastest':''}>{clock(row[k])}</td>;
 return <main className="rhx-page-body">
  <PageHead title="The timing tower." lede="The whole field at a glance. Tap a driver to see their best lap, speed trap and tyre.">
   <Action disabled={!s.event||task.busy} sub="Historical, not a live feed" onClick={()=>task.start('timing',s)}>{r?'Reload timing':'Load timing'}</Action>
  </PageHead>
  <JobBar task={task}/>
  {!r?!task.busy&&<Blank title="Every lap leaves a trace." mark="⏱">Load timing to see the classification, sectors and race control for this session.</Blank>:<>
   <p className="rhx-note"><b>Source: {r.source||'FastF1'}.</b> {r.mode} Intervals aren't inferred from the final classification.</p>
   <div className="rhx-timing">
    <div className="rhx-tower-wrap"><table className="rhx-tower">
     <thead><tr><th>Pos</th><th>Driver</th><th>Gap</th><th>Tyre</th><th>Best</th><th>Last</th><th>S1</th><th>S2</th><th>S3</th></tr></thead>
     <tbody>{rows.map(row=><tr key={row.driver} className={driver?.driver===row.driver?'on':''} tabIndex={0} onClick={()=>setSelected(row.driver)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(row.driver)}}}
      style={{'--team':teamColor(row.color)} as React.CSSProperties}>
      <td className="rhx-pos">{row.position??'—'}</td>
      <td className="rhx-who"><b>{row.driver}</b><small>{row.team}</small></td>
      <td>{row.time!=null?`${row.position===1?'':'+'}${clock(row.time)}`:row.gap?String(row.gap):row.status&&row.status!=='Finished'?row.status:'—'}</td>
      <td>{row.compound?<span className={'rhx-tyre t-'+(TYRE[String(row.compound).toUpperCase()]||'x')} title={row.compound}>{TYRE[String(row.compound).toUpperCase()]||'?'}</span>:'—'}</td>
      {cell(row,'best')}{cell(row,'last')}{cell(row,'s1')}{cell(row,'s2')}{cell(row,'s3')}
     </tr>)}</tbody></table>
     <p className="rhx-legend-line"><span className="rhx-fastest-key"/>Fastest in the session</p></div>
    {driver&&<aside className="rhx-tower-detail" style={{'--team':teamColor(driver.color)} as React.CSSProperties}>
     <span className="rhx-detail-pos">P{driver.position??'—'}</span>
     <h2>{driver.name||driver.driver}</h2><p>{driver.team}</p>
     <dl><div><dt>Best lap</dt><dd>{clock(driver.best)}</dd></div><div><dt>Speed trap</dt><dd>{driver.speed==null?'—':`${Math.round(driver.speed)} km/h`}</dd></div>
      <div><dt>Tyre</dt><dd>{driver.compound||'—'}</dd></div><div><dt>Status</dt><dd>{driver.status||'—'}</dd></div></dl>
     {track.length>1&&<svg className="rhx-track" viewBox={`${minx-w*.06} ${miny-h*.06} ${w*1.12} ${h*1.12}`} aria-label="Circuit outline from recorded telemetry" style={{transform:'scaleY(-1)'}}>
      <polyline points={track.map(p=>p.join(',')).join(' ')} fill="none" strokeWidth={Math.max(w,h)/70} stroke="#243443" strokeLinejoin="round"/>
      <polyline points={track.map(p=>p.join(',')).join(' ')} fill="none" strokeWidth={Math.max(w,h)/220} stroke="var(--team)" strokeLinejoin="round"/></svg>}
    </aside>}
   </div>
   {r.weather&&<div className="rhx-weather">{[['Air',r.weather.AirTemp==null?'—':`${r.weather.AirTemp}°C`],['Track',r.weather.TrackTemp==null?'—':`${r.weather.TrackTemp}°C`],['Wind',r.weather.WindSpeed==null?'—':`${r.weather.WindSpeed} m/s`],['Rain',r.weather.Rainfall==null?'—':r.weather.Rainfall?'Recorded':'None']].map(([k,v])=>
    <div key={k}><span>{k}</span><b>{v}</b></div>)}</div>}
   <section className="rhx-group"><div className="rhx-group-head"><h3>Race control</h3><span className="rhx-count">{r.messages?.length||0} messages</span></div>
    <ol className="rhx-rc">{(r.messages||[]).map((m:any,i:number)=><li key={i}><time>{String(m.Time||'').slice(11,19)||m.Time}</time>
     <i style={{background:FLAG[String(m.Flag||'').toUpperCase()]||'transparent',borderColor:FLAG[String(m.Flag||'').toUpperCase()]?'transparent':'#3a4652'}} title={m.Flag||m.Category}/>
     <span><small>{[m.Category,m.Flag].filter(Boolean).join(', ')}</small>{m.Message}</span></li>)}</ol>
    {!r.messages?.length&&<Note>No race control messages were recorded.</Note>}
   </section>
  </>}
 </main>;
}
