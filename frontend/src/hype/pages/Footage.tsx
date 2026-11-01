import {useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {useSession,useTask} from '../../state';
import {clock} from '../../api';
import {Group,Action,JobBar,FileButton,Note,NumberField} from '../kit';
import Stage,{footagePlace} from '../Stage';

type Clip={id:string;name:string;width:number;height:number;fps:number;duration:number;has_audio:boolean;size:number;poster:string;video:string};
type Sync={lap_start_in_clip:number;coarse_lap_start_in_clip:number;score:number;level:'strong'|'check'|'weak';correlation:number;runner_up:number;lap_length:number;
 shifts:{matched:number;heard:number;in_data:number;spread_ms:number|null};curve:{t:number[];pitch:number[];clarity:number[];rpm:(number|null)[]};audio_shifts:number[];
 telemetry:{t_from_lap_start:number[];speed:number[];rpm:number[];gear:number[];throttle:number[];brake:number[]};source:string;lap_number?:number};

const mmss=(s:number)=>`${s<0?'−':''}${Math.floor(Math.abs(s)/60)}:${(Math.abs(s)%60).toFixed(2).padStart(5,'0')}`;
const LEVEL={strong:['Strong match','The engine note and the RPM data line up clearly.'],check:['Check it','Probably right. Play the clip below and listen to a few gear changes.'],
 weak:['Weak match',"The sound didn't line up well with this lap. Make sure the clip is this driver's selected lap, or set the start by hand."]} as const;

function upload(file:File,onProgress:(p:number)=>void):Promise<Clip>{
 return new Promise((resolve,reject)=>{const x=new XMLHttpRequest();const data=new FormData();data.append('file',file);
  x.upload.onprogress=e=>{if(e.lengthComputable)onProgress(e.loaded/e.total)};
  x.onload=()=>{let body:any={};try{body=JSON.parse(x.responseText)}catch{}
   x.status<300?resolve(body):reject(new Error(typeof body.detail==='string'?body.detail:`Upload failed (${x.status})`))};
  x.onerror=()=>reject(new Error('The upload was interrupted. Check that the engine is running and try again.'));
  x.open('POST','/api/footage');x.send(data)});
}

/** Look up telemetry at a clip time, given where the lap starts in the clip. */
function sampleAt(sync:Sync,lapInClip:number,clipT:number){
 const tl=sync.telemetry,rel=clipT-lapInClip,ts=tl.t_from_lap_start;
 if(!ts.length||rel<ts[0]||rel>ts[ts.length-1])return null;
 let lo=0,hi=ts.length-1;while(hi-lo>1){const m=(lo+hi)>>1;if(ts[m]<=rel)lo=m;else hi=m}
 const k=ts[hi]===ts[lo]?0:(rel-ts[lo])/(ts[hi]-ts[lo]);const lerp=(a:number[])=>a[lo]+(a[hi]-a[lo])*k;
 return {rel,speed:lerp(tl.speed),rpm:lerp(tl.rpm),gear:tl.gear[lo],throttle:lerp(tl.throttle),brake:tl.brake[lo]};
}

/** Engine pitch heard in the clip against RPM from the data, both scaled to the same shape. */
function SyncChart({sync,lapInClip,duration}:{sync:Sync;lapInClip:number;duration:number}){
 const W=1000,H=180;const c=sync.curve;
 const z=(v:number[])=>{const l=v.map(Math.log);const ok=l.filter(Number.isFinite);const m=ok.reduce((a,b)=>a+b,0)/ok.length;const sd=Math.sqrt(ok.reduce((a,b)=>a+(b-m)**2,0)/ok.length)||1;return l.map(x=>(x-m)/sd)};
 const pitch=z(c.pitch);
 const rpm=c.t.map(t=>sampleAt(sync,lapInClip,t)?.rpm??NaN);const rz=z(rpm.map(v=>Number.isFinite(v)&&v>1500?v:NaN));
 const X=(t:number)=>t/duration*W,Y=(v:number)=>H/2-v*H/6.5;
 const line=(v:number[],skip=(i:number)=>false)=>{let d='',pen=false;v.forEach((y,i)=>{if(!Number.isFinite(y)||skip(i)){pen=false;return}d+=(pen?'L':'M')+X(c.t[i]).toFixed(1)+' '+Y(Math.max(-3,Math.min(3,y))).toFixed(1);pen=true});return d};
 return <figure className="rhx-syncchart">
  <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Engine pitch from your clip compared with RPM from the data">
   <rect x={X(lapInClip)} y="0" width={Math.max(0,X(lapInClip+sync.lap_length)-X(lapInClip))} height={H} className="lap"/>
   {sync.audio_shifts.map((t,i)=><line key={i} x1={X(t)} x2={X(t)} y1={H-10} y2={H} className="tick"/>)}
   <path d={line(pitch,i=>c.clarity[i]<.12)} className="heard"/>
   <path d={line(rz)} className="data"/>
  </svg>
  <figcaption><span><i className="heard"/>Engine pitch in your clip</span><span><i className="data"/>RPM from the data</span><span><i className="lap"/>The selected lap</span><span><i className="tick"/>Gear changes heard</span></figcaption>
 </figure>;
}

/** Your clip, playing, with the telemetry readout on top so you can hear and see whether shifts line up. */
function LiveCheck({clip,sync,lapInClip}:{clip:Clip;sync:Sync;lapInClip:number}){
 const v=useRef<HTMLVideoElement>(null);const [now,setNow]=useState(0);
 useEffect(()=>{let raf=0;const tick=()=>{if(v.current)setNow(v.current.currentTime);raf=requestAnimationFrame(tick)};raf=requestAnimationFrame(tick);return()=>cancelAnimationFrame(raf)},[]);
 const s=sampleAt(sync,lapInClip,now);
 return <div className="rhx-live">
  <div className="rhx-live-frame" style={{aspectRatio:`${clip.width}/${clip.height}`,maxWidth:`calc(58vh * ${clip.width/clip.height})`}}>
   <video ref={v} src={clip.video} controls playsInline preload="metadata"/>
   <div className="rhx-live-read" aria-live="off">{s?<>
    <b key={s.gear} className="rhx-live-gear">{s.gear}</b>
    <span><strong>{Math.round(s.speed)}</strong> km/h</span><span><strong>{Math.round(s.rpm).toLocaleString()}</strong> rpm</span>
    <span className="rhx-live-bars"><i style={{width:s.throttle+'%'}} className="thr"/><i style={{width:s.brake+'%'}} className="brk"/></span>
    <small>{s.rel<0?`Lap starts in ${(-s.rel).toFixed(1)} s`:`Lap ${clock(s.rel)}`}</small></>:<small>No telemetry at this point of the clip</small>}</div>
  </div>
  <Note>Play it with sound. The gear number should change exactly when you hear each shift. If it's early or late, nudge the start above.</Note>
 </div>;
}

export function FootageStudio({hudWidth,position,x,y,onMove,source,hudControls}:{hudWidth:number;position:string;x:number;y:number;onMove:(x:number,y:number)=>void;source:string;hudControls:ReactNode}){
 const {selection:s}=useSession();
 const [clip,setClip]=useState<Clip|null>(null),[pct,setPct]=useState<number|null>(null),[err,setErr]=useState('');
 const sync=useTask(),render=useTask('rh-footage-render');
 const [lapInClip,setLapInClip]=useState<number|null>(null);
 const result:Sync|null=sync.result;
 useEffect(()=>{if(result)setLapInClip(result.lap_start_in_clip)},[result]);
 useEffect(()=>{sync.reset();setLapInClip(null)},[clip?.id,s.year,s.event,s.session,s.driver,s.lap,source]);
 const choose=async(file?:File)=>{if(!file)return;setErr('');setPct(0);
  try{const c=await upload(file,setPct);setClip(c);render.reset()}catch(e){setErr((e as Error).message)}finally{setPct(null)}};
 const nudge=(d:number)=>setLapInClip(v=>v==null?v:Math.round((v+d)*1000)/1000);
 const ready=!!clip&&lapInClip!=null;
 const lvl=result?LEVEL[result.level]:null;
 const fileInfo=useMemo(()=>clip?[`${clip.width} × ${clip.height}`,`${Math.round(clip.fps*100)/100} fps`,mmss(clip.duration).replace(/\.\d+$/,''),clip.has_audio?'Sound':'No sound',`${(clip.size/1024/1024).toFixed(0)} MB`]:[],[clip]);
 return <div className="rhx-studio">
  <div className="rhx-studio-controls">
   <Group title="Your clip">
    <label className={'rhx-drop is-big '+(clip?'is-done':'')} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();choose(e.dataTransfer.files?.[0])}}>
     <input type="file" accept="video/*,.mkv" disabled={pct!=null} onChange={e=>choose(e.target.files?.[0]||undefined)}/>
     {pct!=null?<><b>Uploading {Math.round(pct*100)}%</b><span className="rhx-upbar"><i style={{width:pct*100+'%'}}/></span></>
      :clip?<><b>{clip.name}</b><small>{fileInfo.join(', ')}. Drop another clip to replace it.</small></>
      :<><b>Drop your onboard clip here</b><small>MP4, MOV, MKV or WebM, up to 8 GB. A clip with clean engine sound syncs best.</small></>}
    </label>
    {err&&<p className="rhx-error" role="alert">{err}</p>}
    {clip&&!clip.has_audio&&<Note>This clip has no sound, so set where the lap starts by hand below.</Note>}
   </Group>

   {clip&&<Group title="Sync" aside={clip.has_audio&&<Action quiet={!!result} disabled={sync.busy} sub={`${s.driver} ${s.lap?'lap '+s.lap:'fastest lap'}`} onClick={()=>sync.start('footage_sync',s,{footage_id:clip.id,source})}>{result?'Find it again':'Find the lap'}</Action>}>
    <JobBar task={sync} idle={!result&&clip.has_audio?'Listens to the engine in your clip and lines up its gear changes with the real RPM data for this lap.':undefined}/>
    {result&&lvl&&<div className={'rhx-syncread is-'+result.level}>
     <div><span className="rhx-label">The lap starts at</span><strong>{mmss(lapInClip??result.lap_start_in_clip)}</strong><small>into your clip{lapInClip!=null&&Math.abs(lapInClip-result.lap_start_in_clip)>.0005?`, ${lapInClip>result.lap_start_in_clip?'+':'−'}${Math.abs(lapInClip-result.lap_start_in_clip).toFixed(3)} s from the automatic result`:''}</small></div>
     <div className="rhx-syncbadge"><b>{lvl[0]}</b><small>{lvl[1]}</small><small>{result.shifts.matched} of {result.shifts.in_data} gear changes matched{result.shifts.spread_ms!=null?`, within ±${result.shifts.spread_ms} ms`:''}.</small></div>
    </div>}
    {result&&clip&&lapInClip!=null&&<SyncChart sync={result} lapInClip={lapInClip} duration={clip.duration}/>}
    {(result||(clip&&!clip.has_audio))&&<div className="rhx-nudge">
     <NumberField label="Lap start in your clip" suffix="s" step={.01} value={lapInClip??0} onChange={v=>setLapInClip(v)}/>
     <div className="rhx-nudge-btns" role="group" aria-label="Nudge the lap start">{[-.1,-.01,.01,.1].map(d=><button type="button" key={d} onClick={()=>{if(lapInClip==null)setLapInClip(0);nudge(d)}}>{d>0?'+':'−'}{Math.abs(d)} s</button>)}
      {result&&<button type="button" className="is-reset" onClick={()=>setLapInClip(result.lap_start_in_clip)}>Back to automatic</button>}</div>
    </div>}
    {result&&clip&&lapInClip!=null&&<LiveCheck clip={clip} sync={result} lapInClip={lapInClip}/>}
   </Group>}
   {clip&&hudControls}
  </div>

  <aside className="rhx-monitor">
   {clip?<Stage width={clip.width} height={clip.height} hud={hudWidth} position={position} x={x} y={y} onMove={onMove} place={footagePlace}
     backdrop={render.result?undefined:clip.poster} video={render.result?.file.url}/>
    :<div className="rhx-screen-idle is-static"><span className="rhx-screen-duel"><b>{s.driver||'—'}</b></span><span>Your clip appears here with the HUD on top</span></div>}
   <JobBar task={render}/>
   <Action disabled={!ready||render.busy||sync.busy} sub={ready?`HUD synced at ${mmss(lapInClip!)}, original sound kept`:clip?'Find the lap first':'Upload a clip first'}
    onClick={()=>clip&&lapInClip!=null&&render.start('footage_render',s,{footage_id:clip.id,lap_start_in_clip:lapInClip,hud_width:hudWidth,position,x,y,source})}>Render video</Action>
   {render.result&&<div className="rhx-result"><FileButton file={render.result.file} label="Download the finished video"/>
    <Note>{render.result.frames.toLocaleString()} frames. HUD from {render.result.source}{render.result.lap_number?`, lap ${render.result.lap_number}`:''}. It shows real data wherever the clip has telemetry, including before and after the lap.</Note>
    <button type="button" className="rhx-link" onClick={()=>render.reset()}>Back to placing the HUD</button></div>}
   <Note>Footage from broadcasts or F1 TV belongs to Formula 1. Combining it here is fine; posting it publicly can get claimed.</Note>
  </aside>
 </div>;
}
