import {useEffect,useState} from 'react';
import {ResponsiveContainer,LineChart,Line,XAxis,YAxis,CartesianGrid,Tooltip,Brush} from 'recharts';
import {useSession,useTask,useResource} from '../../state';
import {clock,teamColor} from '../../api';
import {PageHead,NeedSession,Choice,NumberField,Group,Action,JobBar,FileButton,Blank,Note,Shape} from '../kit';
import {DuelBar} from '../DriverDuel';

const CHANNELS=[['speed_kmh','Speed','km/h'],['throttle_pct','Throttle','%'],['brake_active','Brake','on/off'],['gear','Gear',''],['rpm','RPM','']] as const;
const GROUP_NOTE:Record<string,string>={
 'Lap analysis':'Compare inputs, circuit segments and sectors to see where the pair gains or loses time.',
 'Race pace':'Lap distributions, repeatability and changing pace gaps, using the existing clean-lap filters.',
 'Strategy':'Compounds, stint lengths and pace as tyres age. Fuel, traffic and conditions also shape the trend.',
};

export default function Analysis(){
 const {selection:s,catalog}=useSession(),health=useResource('/api/health');
 const chart=useTask(),trace=useTask();
 const [group,setGroup]=useState('Lap analysis'),[name,setName]=useState('Fastest lap map'),[channel,setChannel]=useState('speed_kmh'),[axis,setAxis]=useState('distance_m');
 const [imageFormat,setImageFormat]=useState('16:9 (YouTube)'),[drivers,setDrivers]=useState<string[]>([]),[colorMode,setColorMode]=useState('FastF1 Official');
 const [colorA,setColorA]=useState('#00d2be'),[colorB,setColorB]=useState('#dc0000'),[chartLap,setChartLap]=useState(10);
 const groups:Record<string,string[]>=health.value?.charts||{};
 useEffect(()=>{chart.reset();trace.reset()},[s.year,s.event,s.session,s.driver,s.driver_b,s.lap,s.lap_b,s.qualifying_part]);
 const data:any[]=trace.result||[];
 const merged:Record<string,any>={};
 data.forEach(lap=>lap.points.forEach((p:any)=>{const x=p[axis];if(x==null)return;const key=String(Math.round(x*(axis==='time_sec'?10:1)));merged[key]??={x:axis==='time_sec'?Number(key)/10:Number(key)};merged[key][lap.driver]=channel==='brake_active'?(p[channel]==null?null:Number(p[channel])*100):p[channel]}));
 const chartData=Object.values(merged).sort((a:any,b:any)=>a.x-b.x);
 const colors=data.map(l=>teamColor(l.color));const sameColor=colors.length===2&&colors[0]===colors[1];
 const bestSector=(i:number)=>Math.min(...data.map(l=>l.sectors?.[i]??Infinity));
 const unit=CHANNELS.find(c=>c[0]===channel)?.[2];
 return <main className="rhx-page-body">
  <PageHead title="Hunt the tenths." lede="Lay two laps on top of each other. Find the braking point, read the throttle, see where the time goes."/>
  {!catalog?<NeedSession what="Lap analysis"/>:<>
   <DuelBar/>
   <Group title="The driving trace" aside={<Action disabled={trace.busy} onClick={()=>trace.start('traces',s)}>Compare telemetry</Action>}>
    <div className="rhx-row">
     <Choice label="Channel" value={channel} onChange={setChannel} options={CHANNELS.map(([v,l,u])=>({value:v,label:l,hint:u||undefined}))}/>
     <Choice label="Line up by" value={axis} onChange={setAxis} options={[{value:'distance_m',label:'Track distance'},{value:'time_sec',label:'Lap time'}]}/>
    </div>
    <JobBar task={trace}/>
    {data.length>0?<>
     <div className="rhx-chart"><ResponsiveContainer width="100%" height={380}><LineChart data={chartData} margin={{top:10,right:12,bottom:0,left:-8}}>
      <CartesianGrid stroke="#1f2a35" vertical={false}/>
      <XAxis dataKey="x" type="number" domain={['dataMin','dataMax']} stroke="#5d6b79" tick={{fontSize:11,fill:'#8a98a7'}} tickFormatter={v=>axis==='distance_m'?`${Math.round(v/100)/10}km`:`${v}s`}/>
      <YAxis stroke="#5d6b79" tick={{fontSize:11,fill:'#8a98a7'}} width={48}/>
      <Tooltip contentStyle={{background:'#18212c',border:'1px solid #273441',borderRadius:4,color:'#eef2f5'}} labelStyle={{color:'#8a98a7'}} labelFormatter={v=>`${v} ${axis==='distance_m'?'m':'s'}`} formatter={(v:any)=>[`${typeof v==='number'?Math.round(v*10)/10:v} ${unit}`]}/>
      {data.map((lap,i)=><Line key={lap.driver} dataKey={lap.driver} stroke={i===1&&sameColor?'#eef2f5':colors[i]} strokeDasharray={i===1&&sameColor?'5 4':undefined} dot={false} strokeWidth={1.8} connectNulls isAnimationActive={false}/>)}
      <Brush dataKey="x" height={26} stroke="#3a4a5a" fill="#0f151c" travellerWidth={10}/>
     </LineChart></ResponsiveContainer></div>
     <div className="rhx-sectors">{data.map((lap,i)=><div key={lap.driver} style={{'--team':colors[i]} as React.CSSProperties}>
      <span className="rhx-sectors-who"><b>{lap.driver}</b><small>Lap {lap.lap}</small></span><strong>{clock(lap.lap_time)}</strong>
      {lap.sectors.map((v:number,k:number)=><span key={k} className={v===bestSector(k)?'is-best':''}><small>S{k+1}</small>{clock(v)}</span>)}</div>)}</div>
     <Note>Drag the handles under the chart to zoom into a corner. The tooltip shows the nearest real sample.</Note>
    </>:!trace.busy&&<Blank title="Two laps, one line each." mark="⌁">Compare telemetry to draw both drivers' {CHANNELS.find(c=>c[0]===channel)?.[1].toLowerCase()} over the lap.</Blank>}
   </Group>

   <Group title="The engineering desk">
    {Object.keys(groups).length>0&&<Choice label="Category" value={group} onChange={g=>{setGroup(g);setName(groups[g][0])}} options={Object.keys(groups).map(g=>({value:g,label:g}))}/>}
    <Note>{GROUP_NOTE[group]||'Classification changes, cumulative gaps, team pace and peak speeds across the session.'}</Note>
    <Choice label="Chart" value={name} onChange={setName} variant="cards" className="is-grid" options={(groups[group]||[name]).map(n=>({value:n,label:n}))}/>
    {name==='Telemetry Comparison'&&<NumberField label="Lap number for both drivers" min={1} max={500} value={chartLap} onChange={setChartLap}/>}
    <div className="rhx-row">
     <Choice label="Image shape" value={imageFormat} onChange={setImageFormat} variant="shapes" options={[{value:'16:9 (YouTube)',label:'16:9',hint:'YouTube',visual:<Shape w={16} h={9}/>},{value:'9:16 (TikTok)',label:'9:16',hint:'TikTok',visual:<Shape w={9} h={16}/>},{value:'1:1 (Instagram)',label:'1:1',hint:'Instagram',visual:<Shape w={1} h={1}/>}]}/>
     <Choice label="Colours" value={colorMode} onChange={setColorMode} options={[{value:'FastF1 Official',label:'Team colours'},{value:'Monochrome',label:'Monochrome'},{value:'Custom',label:'Custom'}]}/>
     {colorMode==='Custom'&&<div className="rhx-swatches"><label><input type="color" value={colorA} onChange={e=>setColorA(e.target.value)}/>Driver A</label><label><input type="color" value={colorB} onChange={e=>setColorB(e.target.value)}/>Driver B</label></div>}
    </div>
    <div className="rhx-field"><span className="rhx-label">Drivers for field charts <small>{drivers.length?`${drivers.length} chosen`:'none chosen, uses your pair'}</small></span>
     <div className="rhx-toggles">{Object.entries(catalog.drivers).map(([code,d])=>{const on=drivers.includes(code);
      return <button type="button" key={code} aria-pressed={on} className={on?'on':''} style={{'--team':teamColor(d.color)} as React.CSSProperties} onClick={()=>setDrivers(on?drivers.filter(x=>x!==code):[...drivers,code])}>{code}</button>})}
      {drivers.length>0&&<button type="button" className="is-clear" onClick={()=>setDrivers([])}>Clear</button>}</div></div>
    <Note>Race pace and strategy charts need a race with usable laps and stints.</Note>
    <div className="rhx-row is-end"><Action disabled={chart.busy} sub={name} onClick={()=>chart.start('chart',name==='Telemetry Comparison'?{...s,lap:chartLap}:s,{chart:name,drivers,image_format:imageFormat,color_mode:colorMode,color_a:colorA,color_b:colorB})}>Make the chart</Action></div>
    <JobBar task={chart}/>
    {chart.result?<div className="rhx-chart-image"><img src={chart.result.file.url} alt={chart.result.chart}/><FileButton file={chart.result.file} label="Download this chart"/></div>
     :!chart.busy&&<Blank title="Find the story in the numbers." mark="◩">Every chart uses the existing Python calculations on real session data.</Blank>}
   </Group>
  </>}
 </main>;
}
