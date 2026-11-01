import {useEffect,useState} from 'react';
import {useSession,useTask} from '../../state';
import {request} from '../../api';
import {PageHead,NeedSession,Choice,Group,Action,JobBar,FileButton,Blank,Note,SourcePicker} from '../kit';
import {DuelBar} from '../DriverDuel';

const PACKS:Record<string,string>={csv:'Spreadsheets and scripts',tsv:'After Effects keyframes',racerender:'RaceRender data overlay'};
const COLS=['time_sec','speed_kmh','rpm','gear','throttle_pct','brake_active','drs_active','source'];

export default function Telemetry(){
 const {selection:s,setSelection,catalog}=useSession();const task=useTask();
 const [source,setSource]=useState('Auto'),[upload,setUpload]=useState(''),[fps,setFps]=useState(30);
 useEffect(()=>task.reset(),[s.year,s.event,s.session,s.driver,s.lap,source,upload]);
 const r=task.result;const csv=source==='Upload CSV';
 const ready=csv?!!upload:!!catalog&&!!s.event;
 const hint=(f:any)=>{const n=(f.label||f.name).toLowerCase();return n.includes('after')||n.endsWith('.tsv')?PACKS.tsv:n.includes('racerender')?PACKS.racerender:PACKS.csv};
 return <main className="rhx-page-body">
  <PageHead title="Every lap. Every sample." lede="Take the numbers with you: the selected lap, the full source stream, and ready-made files for After Effects and RaceRender."/>
  <SourcePicker {...{source,setSource,upload,setUpload,request}}/>
  {csv?<label className="rhx-field rhx-num"><span className="rhx-label">Driver label</span><span className="rhx-num-box"><input value={s.driver} placeholder="e.g. VER" maxLength={5} onChange={e=>setSelection({driver:e.target.value.toUpperCase()})}/></span></label>
   :!catalog?<NeedSession what="A telemetry export"/>:<DuelBar pair={false}/>}
  {(csv||catalog)&&<Group title="Export" aside={<Action disabled={task.busy||!ready} sub="Four packages" onClick={()=>task.start('telemetry',{...s,event:s.event||'Uploaded telemetry'},{source,upload_id:upload,fps})}>Prepare export</Action>}>
   <Choice label="Frame rate for video tools" value={fps} onChange={setFps} options={[24,25,30,50,60].map(v=>({value:v,label:String(v)}))}/>
   <Note>Actual source data only. Missing boost, overtake, recharge and active-aero fields stay empty.</Note>
   <JobBar task={task}/>
  </Group>}
  {r?<>
   <div className="rhx-weather">{[['Source',r.metadata.source],['Samples',r.rows.toLocaleString()],['Duration',r.duration==null?'—':`${r.duration.toFixed(3)} s`],['Lap',r.metadata.lap_number||'Uploaded stream']].map(([k,v])=><div key={k}><span>{k}</span><b>{v}</b></div>)}</div>
   {r.metadata.fallback&&<Note>FastF1 wasn't available, so Auto used OpenF1. Original error: {r.metadata.fallback}</Note>}
   <div className="rhx-packs">{r.files.map((f:any)=><div key={f.id} className="rhx-pack"><small>{hint(f)}</small><FileButton file={f}/></div>)}</div>
   <Group title="Inspect the samples" aside={<span className="rhx-count">First {r.preview.length} of {r.rows.toLocaleString()}</span>}>
    <div className="rhx-tower-wrap"><table className="rhx-tower is-data"><thead><tr>{COLS.map(c=><th key={c}>{c.replaceAll('_',' ')}</th>)}</tr></thead>
     <tbody>{r.preview.map((row:any,i:number)=><tr key={i}>{COLS.map(c=><td key={c}>{row[c]==null?'—':String(row[c])}</td>)}</tr>)}</tbody></table></div>
    <details className="rhx-details"><summary>All {r.columns.length} fields in the export</summary><p>{r.columns.join(', ')}</p></details>
   </Group>
  </>:!task.busy&&(csv||catalog)&&<Blank title="The raw numbers." mark="⇣">Selected-lap CSV, full-source CSV, After Effects TSV and RaceRender CSV, prepared in one go.</Blank>}
 </main>;
}
