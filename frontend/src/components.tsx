import {useState,type ReactNode} from 'react';
import {ArrowDownToLine,ArrowUpRight,LoaderCircle,X} from 'lucide-react';
import {useSession,useTask} from './state';
import {clock,portrait,teamColor,type Driver,type Output,sessions} from './api';

export function Intro({number,title,accent,children}:{number:string;title:string;accent:string;children:ReactNode}){
 return <header className="page-intro"><span className="eyebrow">{number} / RACE HYPE</span><h1>{title} <em>{accent}</em></h1><p>{children}</p><span className="page-watermark" aria-hidden="true">{number}</span></header>;
}
export function Empty({title='Choose your weekend.',children}:{title?:string;children?:ReactNode}){
 return <div className="empty"><span className="empty-icon">↗</span><h3>{title}</h3><p>{children||'Load a supported session above to reveal its real drivers and available laps.'}</p></div>;
}
export function ErrorBox({message}:{message?:string}){return message?<div className="error" role="alert"><strong>Unable to load this selection</strong><p>{message}</p></div>:null}
export function Field({label,children}:{label:string;children:ReactNode}){return <label className="field"><span>{label}</span>{children}</label>}
export function Button({children,onClick,disabled=false,secondary=false}:{children:ReactNode;onClick?:()=>void;disabled?:boolean;secondary?:boolean}){return <button className={'btn '+(secondary?'btn-outline':'btn-primary')} disabled={disabled} onClick={onClick}>{children}<ArrowUpRight size={15}/></button>}
export function JobStatus({task}:{task:ReturnType<typeof useTask>}){
 const j=task.job;
 return <><ErrorBox message={task.error||j?.error}/>{task.busy&&<div className="job-status" role="status"><LoaderCircle className="spin"/><div><strong>{j?.message||'Connecting to the data engine…'}</strong><progress value={j?.progress||.02} max="1"/></div><button className="icon-button" aria-label="Cancel task" onClick={task.cancel}><X/></button></div>}{j?.status==='cancelled'&&<p className="note">Task cancelled.</p>}</>;
}
export function Download({file,label}:{file:Output;label?:string}){return <a className="download-link" href={file.url+'?download=true'}><ArrowDownToLine size={16}/>{label||file.label||file.name}<small>{(file.size/1024/1024).toFixed(2)} MB</small></a>}
export function DriverCard({code,entry,label}:{code:string;entry:Driver;label:string}){
 const [failed,setFailed]=useState(false);
 return <div className="driver-card" style={{'--driver':teamColor(entry.color)} as React.CSSProperties}><span className="eyebrow soft">{label}</span><strong>{code}</strong><h3>{entry.name}</h3><p>{entry.team}</p><small>{entry.laps?.length||0} timed laps</small><span className="driver-watermark">{code}</span>{entry.portrait&&!failed&&<img key={entry.portrait} src={portrait(entry.portrait)} onError={()=>setFailed(true)} alt={entry.name}/>}</div>;
}
export function DriverControls({pair=true,laps=true}:{pair?:boolean;laps?:boolean}){
 const {selection:s,setSelection,catalog}=useSession();
 if(!catalog)return <Empty/>;
 const entries=Object.entries(catalog.drivers);
 return <>{catalog.notice&&<p className="note" role="status">{catalog.notice} Race timing, replays and engineering charts still require FastF1.</p>}<div className={'driver-grid '+(!pair?'single':'')}>
 {(['driver',...(pair?['driver_b']:[])] as ('driver'|'driver_b')[]).map((key,i)=><div key={key}>
 <Field label={'Driver '+(i?'B':'A')}><select value={s[key]} onChange={e=>setSelection({[key]:e.target.value,[i?'lap_b':'lap']:null})}>{entries.map(([code,d])=><option key={code} value={code}>{code} · {d.name}</option>)}</select></Field>
 {catalog.drivers[s[key]]&&<DriverCard key={s[key]} code={s[key]} entry={catalog.drivers[s[key]]} label={i?'THE RIVAL':'THE CHALLENGER'}/>}</div>)}
 </div>{laps&&<div className="inline-fields"><Field label="Qualifying segment"><select disabled={!['Q','SQ'].includes(s.session)||catalog.qualifying_segments===false} value={s.qualifying_part} onChange={e=>setSelection({qualifying_part:e.target.value,lap:null,lap_b:null})}>{['All','Q1','Q2','Q3'].map(part=><option key={part}>{part}</option>)}</select></Field>{(['driver',...(pair?['driver_b']:[])] as ('driver'|'driver_b')[]).map((key,i)=>{
 const d=catalog.drivers[s[key]];const choices=d?.segments?.[s.qualifying_part]||d?.laps||[];const lapKey=i?'lap_b':'lap';
 return <Field key={key} label={`${s[key]||'Driver'} lap`}><select value={s[lapKey]||''} onChange={e=>setSelection({[lapKey]:e.target.value?Number(e.target.value):null})}><option value="">{catalog.source==='OpenF1'?'Fastest non-deleted timed lap':'Fastest valid lap'}</option>{choices.map(n=><option key={n} value={n}>Lap {n}</option>)}</select></Field>})}</div>}</>;
}
export function DataTable({rows,columns,onRow,selected}:{rows:any[];columns:Array<[string,string,((row:any)=>ReactNode)?]>;onRow?:(row:any)=>void;selected?:string}){
 return <div className="table-wrap"><table className="timing-table"><thead><tr>{columns.map(([key,label]:any)=><th key={key}>{label}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={row.id||row.driver||index} className={selected===row.driver?'selected':''} onClick={()=>onRow?.(row)} tabIndex={onRow?0:undefined} onKeyDown={e=>{if(onRow&&e.key==='Enter')onRow(row)}}>{columns.map(([key,_label,render]:any)=><td key={key}>{render?render(row):row[key]==null?'—':String(row[key])}</td>)}</tr>)}</tbody></table>{!rows.length&&<p className="note">No records are available for this selection.</p>}</div>;
}
export function Stat({label,value,sub}:{label:string;value:ReactNode;sub?:ReactNode}){return <div className="metric"><span>{label}</span><strong>{value}</strong>{sub&&<small>{sub}</small>}</div>}
export function SourceNote(){return <p className="note">Actual source data only. Missing boost, overtake, recharge and active-aero fields remain empty.</p>}
export function AssetNote(){return <details className="accuracy"><summary>About 3D accuracy & asset credits</summary><p>Real lap clocks and telemetry inputs on illustrative telemetry-built circuits. Usable telemetry Z supplies smoothed relative elevation; missing or unreliable heights fall back to flat geometry. This is not surveyed terrain. Track widths, scenery, car spacing and ghost routes are illustrative; they do not establish either driver’s exact racing line. Lighting follows the venue’s usual race setting.</p><p>Generic concept car by <a href="https://sketchfab.com/3d-models/f1-2026-concept-polygon-model-ea3bde709b1e4dc9b0ec8557d106ed42" target="_blank" rel="noreferrer">Qvist_designs</a>, <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>. Modified scale, mesh detail and team-inspired materials. Not an authentic team/year replica.</p></details>}
export {clock,sessions};
