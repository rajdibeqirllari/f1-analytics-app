import {useEffect,useState} from 'react';
import {request} from '../api';
import {useSession,useTask,useResource} from '../state';
import {Intro,Field,Button,JobStatus,Empty,ErrorBox} from '../components';
export default function Replay(){
 const {selection:s}=useSession(),task=useTask();const [rate,setRate]=useState(3),[refresh,setRefresh]=useState(false),[error,setError]=useState('');
 const cache=useResource<any[]>('/api/replay-cache');
 useEffect(()=>task.reset(),[s.year,s.event,s.session]);
 const supported=['R','Q','S','SQ'].includes(s.session);
 async function clearCache(){setError('');try{await request('/api/replay-cache',{method:'DELETE'});cache.refresh()}catch(e){setError((e as Error).message)}}
 return <section className="workspace"><Intro number="06" title="REWIND." accent="RELIVE.">Follow every car. Replay the moves. Find the moments that mattered.</Intro><div className="action-row"><span className="source-tag">RECORDED POSITIONS · HISTORICAL REPLAY</span><Button disabled={task.busy||!s.event||!supported} onClick={()=>task.start('replay',s,{sample_rate:rate,refresh})}>Load race replay</Button></div>{!supported&&<p className="note">Choose Race, Qualifying, Sprint or Sprint qualifying for the replay.</p>}<details className="advanced"><summary>Sampling & cache</summary><div className="inline-fields"><Field label="Requested samples / second"><select value={rate} onChange={e=>setRate(Number(e.target.value))}>{[1,3,5,10].map(n=><option key={n}>{n}</option>)}</select></Field><label className="check"><input type="checkbox" checked={refresh} onChange={e=>setRefresh(e.target.checked)}/>Rebuild selected replay</label></div><p className="note">Long sessions are capped at 6,000 browser frames by the existing replay engine. Effective sampling is reported in the loaded replay.</p><p>{cache.value?.length||0} cached replay payloads</p><button className="text-button" onClick={clearCache}>Clear regenerable replay cache</button><ErrorBox message={error}/></details><JobStatus task={task}/>
 {task.result?<><iframe className="replay-viewer" src={task.result.viewer} title="Recorded race replay cockpit" allow="fullscreen"/><p className="note">{task.result.technical.frame_count.toLocaleString()} frames · {task.result.technical.driver_count} drivers · {task.result.meta.sample_rate_hz} Hz. Uses available recorded positions; missing data cannot establish an exact racing line.</p></>:<Empty title="THE RACE, AT YOUR PACE.">Real replay payloads. Play, pause, seek, change speed and follow a driver in the cockpit.</Empty>}
 </section>;
}
