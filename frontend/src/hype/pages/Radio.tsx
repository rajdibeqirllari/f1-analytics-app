import {useEffect,useRef,useState} from 'react';
import {useSession,useTask} from '../../state';
import {teamColor} from '../../api';
import {PageHead,Choice,Action,JobBar,FileButton,Blank,Note} from '../kit';

function Waveform({url,audio}:{url:string;audio:React.RefObject<HTMLAudioElement|null>}){
 const canvas=useRef<HTMLCanvasElement>(null),[peaks,setPeaks]=useState<number[]|null>(null),[pos,setPos]=useState(0);
 useEffect(()=>{let stopped=false;const ctrl=new AbortController();let ctx:AudioContext|undefined;setPeaks(null);
  (async()=>{try{const bytes=await fetch(url,{signal:ctrl.signal}).then(r=>{if(!r.ok)throw Error();return r.arrayBuffer()});ctx=new AudioContext();const buf=await ctx.decodeAudioData(bytes);if(stopped)return;
   const d=buf.getChannelData(0),n=160,out:number[]=[];for(let i=0;i<n;i++){let p=0;const a=Math.floor(i/n*d.length),b=Math.floor((i+1)/n*d.length);for(let k=a;k<b;k+=8)p=Math.max(p,Math.abs(d[k]));out.push(p)}setPeaks(out)}catch{}finally{ctx?.close()}})();
  return()=>{stopped=true;ctrl.abort()}},[url]);
 useEffect(()=>{const a=audio.current;if(!a)return;const t=()=>setPos(a.duration?a.currentTime/a.duration:0);a.addEventListener('timeupdate',t);return()=>a.removeEventListener('timeupdate',t)},[audio,url]);
 useEffect(()=>{const c=canvas.current;if(!c||!peaks)return;const w=c.clientWidth,h=c.clientHeight,dpr=devicePixelRatio||1;c.width=w*dpr;c.height=h*dpr;const g=c.getContext('2d')!;g.scale(dpr,dpr);
  const bw=w/peaks.length;peaks.forEach((p,i)=>{const bh=Math.max(2,p*h*.92);g.fillStyle=i/peaks.length<pos?'#ff463b':'#3a4a5a';g.fillRect(i*bw+1,(h-bh)/2,Math.max(1,bw-2),bh)})},[peaks,pos]);
 return <div className="rhx-wave" onClick={e=>{const a=audio.current;if(!a||!a.duration)return;const r=e.currentTarget.getBoundingClientRect();a.currentTime=(e.clientX-r.left)/r.width*a.duration}}>
  <canvas ref={canvas} aria-label="Waveform of this recording. Click to jump."/>{!peaks&&<span>Reading the recording…</span>}</div>;
}

export default function Radio(){
 const {selection:s,catalog}=useSession(),task=useTask();const [driver,setDriver]=useState('All'),[active,setActive]=useState(0),[refresh,setRefresh]=useState(false);
 const audio=useRef<HTMLAudioElement>(null);
 useEffect(()=>{task.reset();setActive(0);setDriver('All')},[s.year,s.event,s.session]);
 const clips:any[]=task.result?.clips||[];
 const codes=Array.from(new Set(clips.map(c=>String(c.driver))));
 const shown=clips.filter(c=>driver==='All'||String(c.driver)===driver);const clip=shown.find(c=>c.idx===active)||shown[0];
 const color=(c:any)=>teamColor(catalog?.drivers[c?.driver]?.color);
 return <main className="rhx-page-body">
  <PageHead title="Hear the pressure." lede="Real team radio from the archive. Strategy calls, frustration and celebration from behind the visor.">
   <Action disabled={task.busy||!s.event} sub="Archive recordings" onClick={()=>task.start('radio',s,{refresh})}>{task.result?'Search again':'Find team radio'}</Action>
  </PageHead>
  <label className="rhx-check"><input type="checkbox" checked={refresh} onChange={e=>setRefresh(e.target.checked)}/><span>Refresh from the source archive</span></label>
  <JobBar task={task}/>
  {task.result?<>
   {codes.length>1&&<Choice label="Driver" value={driver} onChange={setDriver} options={[{value:'All',label:'Everyone',hint:String(clips.length)},...codes.map(c=>({value:c,label:c,hint:String(clips.filter(x=>String(x.driver)===c).length)}))]}/>}
   <div className="rhx-radio">
    <ol className="rhx-radio-list">{shown.map(c=><li key={c.idx}><button type="button" className={clip?.idx===c.idx?'on':''} style={{'--team':color(c)} as React.CSSProperties} onClick={()=>setActive(c.idx)}>
     <span className="rhx-radio-lap">{c.lap==null?(c.pre?'Pre':'—'):`L${c.lap}`}</span><span><b>{c.driver_name||c.driver}</b><small>{c.pre?'Pre-race':c.time||'Time not recorded'}</small></span></button></li>)}
     {!shown.length&&<li><Note>The archive has no clips for this filter.</Note></li>}</ol>
    {clip?<div className="rhx-radio-player" style={{'--team':color(clip)} as React.CSSProperties}>
     <span className="rhx-radio-team">{clip.team||'Team radio'}</span><h2>{clip.driver_name||clip.driver}</h2>
     <Waveform key={clip.url} url={clip.url} audio={audio}/>
     <audio ref={audio} key={clip.url+'a'} src={clip.url} controls preload="metadata"/>
     <dl><div><dt>Session time</dt><dd>{clip.pre?'Pre-race':clip.time||'—'}</dd></div><div><dt>Lap / position</dt><dd>{clip.lap??'—'} / {clip.position??'—'}</dd></div><div><dt>Tyre</dt><dd>{clip.compound||'—'}</dd></div></dl>
     <a className="rhx-file" href={clip.url+'?download=true'}><b>Download this recording</b></a>
     <Note>Original archive audio. Coverage depends on the provider and isn't a complete feed.</Note>
    </div>:<Blank title="Pick a transmission."/>}
   </div>
   {task.result.files?.length>0&&<div className="rhx-packs">{task.result.files.map((f:any)=><div key={f.id} className="rhx-pack"><small>Archive export</small><FileButton file={f}/></div>)}</div>}
  </>:!task.busy&&<Blank title="The human side of racing." mark="◉">Find this session's recordings, listen, and save a clip or the whole archive export.</Blank>}
 </main>;
}
