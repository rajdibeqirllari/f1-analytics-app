import {Suspense,useEffect,useMemo,useRef,useState} from 'react';
import {recoverableLazy} from '../../chunkRecovery';
import {claimRadio,stopRadio} from '../broadcast/audioBus';
import {request,post,teamColor} from '../../api';
import {useSession} from '../../state';
import {Action,Blank,Note} from '../kit';
import {bundledCircuit} from '../circuits';
import {toRound} from '../weekend';

type Row={number:string;code:string;name:string;team:string;color:string;position:number;gap:string|null;interval:string|null;best:string|null;
 last:{value:string|null;personal:boolean;overall:boolean};sectors:{value:string|null;personal:boolean;overall:boolean}[];segments:number[][];
 laps:number|null;in_pit:boolean;pit_out:boolean;retired:boolean;stopped:boolean;knocked_out:boolean;cutoff:boolean;
 tyre:{compound:string|null;new:boolean;laps:number|null};progress:number|null;speed_trap:number|null;fastest?:boolean};
type Snap={feed:null|{mode:'follow'|'replay';file:string;speed:number;paused:boolean;start:number|null;end:number|null;clock:number|null;messages:number;updated:number|null;ended?:boolean;growing?:boolean};
 recorder:{running:boolean;file:string|null;exit_code:number|null;log:string};
 session?:{name:string;type:string;meeting:string;circuit:string;country:string;status:string;part:number|null;qualifying:boolean;remaining:number|null;lap:number|null;laps:number|null;year:number|null};
 flag?:{state:string;text:string};segments?:number[];yellows?:{sector:number;double:boolean}[];marshal_sectors?:number;drivers?:Row[];race_control?:{time:string;category:string;flag:string|null;message:string}[];
 weather?:{air:number|null;track:number|null;rain:boolean;wind:number|null};received?:number|null;commentary?:Commentary};
type Line={id:number;time:string;text:string;kind:string;prio:number;source:'ai'|'template';drivers:string[];radio:null|{code:string;url?:string;transcript?:string};audio:string|null;facts:string[]};
type Commentary={enabled:boolean;language:string;ai:boolean;model:string;error:string;radio:string;lines:Line[];run?:string;
 tts?:{available:boolean;voice:string;voices:Record<string,string>}};
type Track={x:number[];y:number[];rotation:number;source:string;pit?:{entry:number;exit:number}};
type File={folder:string;name:string;size:number;modified:number;growing:boolean;meeting:string;session:string;start:string;title:string;hidden:boolean};

// Three.js only loads when a viewer opens the 3D view.
const Broadcast3D=recoverableLazy(()=>import('../broadcast/Broadcast3D'));
const hasWebGL=()=>{try{const c=document.createElement('canvas');return !!(c.getContext('webgl2')||c.getContext('webgl'))}catch{return false}};
const viewStore={get:()=>{try{return localStorage.getItem('rhx-live-view')==='3d'?'3d':'2d'}catch{return '2d'}},set:(v:string)=>{try{localStorage.setItem('rhx-live-view',v)}catch{}}};

const TYRE:Record<string,string>={SOFT:'S',MEDIUM:'M',HARD:'H',INTERMEDIATE:'I',WET:'W'};
const FLAG:Record<string,string>={GREEN:'#2bd46b',CLEAR:'#2bd46b',YELLOW:'#ffd23f','DOUBLE YELLOW':'#ffd23f',RED:'#ff463b',BLUE:'#3ea7ff',CHEQUERED:'#eef2f5'};
const segColor=(s:number)=>s===2051?'p':s===2049?'g':s===2048?'y':s===2064?'pit':s?'y':'';
const hms=(s:number|null|undefined)=>s==null?'—':`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
// Qualifying elimination: after Q1 the bottom 6 of 22 go out, after Q2 the next 6 (positions 11–16).
const knockFrom=(part:number|null|undefined,count:number)=>part===1?count-5:part===2?count-11:null;

function useLive(){
 const [snap,setSnap]=useState<Snap|null>(null),[err,setErr]=useState(''),[lastOk,setLastOk]=useState(0);
 useEffect(()=>{let alive=true;let t:any;const tick=async()=>{try{const s=await request<Snap>('/api/live/state');if(alive){setSnap(s);setErr('');setLastOk(Date.now())}}
  catch(e){if(alive)setErr((e as Error).message||'No answer')}finally{if(alive)t=setTimeout(tick,1000)}};tick();return()=>{alive=false;clearTimeout(t)}},[]);
 return {snap,err,lastOk};
}

/** Smooth car motion along the lap. The feed only says where each car is about once a second, and its
 * estimate can step backwards; here each car drives forward at its own pace and gently closes the gap to the
 * latest estimate, never reversing. Big disagreements (pit exit, wrong guess) snap instead of crawling. */
function useSmoothProgress(rows:Row[],speed:number,paused:boolean){
 const st=useRef(new Map<string,{p:number;target:number;v:number}>());
 const [,tick]=useState(0);
 useEffect(()=>{const m=st.current;const seen=new Set<string>();
  for(const r of rows){if(r.progress==null||r.knocked_out)continue;seen.add(r.number);
   const lap=clockSec(r.best)||clockSec(r.last.value)||82;const v=1/lap;
   const cur=m.get(r.number);if(!cur){m.set(r.number,{p:r.progress,target:r.progress,v});continue}
   const d=wrap(r.progress-cur.p);
   if(Math.abs(d)>.25)cur.p=r.progress; // too far apart to drive there: jump
   cur.target=r.progress;cur.v=v}
  for(const k of [...m.keys()])if(!seen.has(k))m.delete(k)},[rows]);
 useEffect(()=>{let raf=0,last=performance.now();
  const frame=(now:number)=>{const dt=Math.min(.1,(now-last)/1000);last=now;
   for(const c of st.current.values()){
    const d=wrap(c.target-c.p);
    // Own pace plus a correction that closes the gap in ~1.5 s; clamped so cars never go backwards.
    const rate=paused?Math.max(0,d/1.5):Math.max(0,c.v*speed+d/1.5);
    c.p=(c.p+Math.min(rate,c.v*speed*3+.02)*dt+1)%1}
   tick(t=>t+1);raf=requestAnimationFrame(frame)};
  raf=requestAnimationFrame(frame);return()=>cancelAnimationFrame(raf)},[speed,paused]);
 return st.current;
}
const wrap=(d:number)=>((d%1)+1.5)%1-.5;

/** Cars in the pit lane: q runs 0 (pit entry) to 1 (pit exit) along the pit lane line.
 * A car that pits drives in from the entry to its box; when it leaves (PitOut) it drives to the exit and rejoins the track. */
type PitCar={q:number;target:number;out:boolean};
function usePitMotion(rows:Row[],speed:number,paused:boolean,pitLen:number|null,exitAt:number|null,smooth:Map<string,{p:number;target:number;v:number}>){
 const st=useRef(new Map<string,PitCar>()),seen=useRef(new Map<string,number>());
 const slot=(num:string)=>{const order=[...rows].sort((a,b)=>(a.team||'').localeCompare(b.team||'')||Number(a.number)-Number(b.number));
  const i=order.findIndex(r=>r.number===num);return .18+.64*(order.length>1?i/(order.length-1):.5)};
 useEffect(()=>{if(pitLen==null)return;const m=st.current;
  for(const r of rows){const cur=m.get(r.number);
   if(r.knocked_out){m.delete(r.number);continue}
   if(r.in_pit){const t=slot(r.number);
    if(!cur)m.set(r.number,{q:seen.current.has(r.number)?0:t,target:t,out:false}); // drove in: start at the entry
    else{cur.target=t;cur.out=false}}
   else if(cur&&(r.pit_out||cur.q<1)){cur.target=1;cur.out=true}
   else if(cur)m.delete(r.number);
   if(r.progress!=null&&!r.in_pit)seen.current.set(r.number,r.progress);else if(r.in_pit)seen.current.delete(r.number)}
  for(const k of [...m.keys()])if(!rows.some(r=>r.number===k))m.delete(k)},[rows,pitLen]);
 useEffect(()=>{if(pitLen==null)return;let raf=0,last=performance.now();
  // Pit limiter: roughly a third of an average lap speed, so the lane takes ~pitLen*230 s.
  const rate=1/Math.max(8,pitLen*230);
  const frame=(now:number)=>{const dt=Math.min(.1,(now-last)/1000);last=now;
   for(const [k,c] of st.current){
    if(c.target<c.q&&!c.out){c.q=c.target;continue} // box moved behind (new order): just sit there
    if(!paused)c.q=Math.min(c.target,c.q+rate*speed*dt);
    if(c.out&&c.q>=1){st.current.delete(k);const sm=smooth.get(k);if(sm&&exitAt!=null)sm.p=exitAt}}
   raf=requestAnimationFrame(frame)};
  raf=requestAnimationFrame(frame);return()=>cancelAnimationFrame(raf)},[speed,paused,pitLen,exitAt]);
 return st.current;
}
const clockSec=(v:string|null|undefined)=>{if(!v)return null;const p=v.split(':').map(Number);if(p.some(isNaN))return null;return p.reduce((a,b)=>a*60+b,0)};

type MapProps={track:Track;rows:Row[];segments:number[];flag:string;focus:string|null;onFocus:(n:string)=>void;speed:number;paused:boolean;yellows:{sector:number;double:boolean}[];marshals:number};
/** Broadcast-style tracker: sector-tinted circuit, chequered line, position discs and driver tags. */
function TrackMap({track,rows,segments,flag,focus,onFocus,speed,paused,yellows,marshals}:MapProps){
 const smooth=useSmoothProgress(rows,speed,paused);
 const prog=(c:Row)=>smooth.get(c.number)?.p??c.progress!;
 const pts=useMemo(()=>{const r=-(track.rotation||0)*Math.PI/180,c=Math.cos(r),s=Math.sin(r);
  return track.x.map((x,i)=>[x*c-track.y[i]*s,-(x*s+track.y[i]*c)])},[track]);
 const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);const minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
 const span=Math.max(maxx-minx,maxy-miny),pad=span*.1;const w=maxx-minx+pad*2,h=maxy-miny+pad*2;
 const n=pts.length;
 const path=(a:number,b:number)=>{const out:number[][]=[];for(let i=Math.round(a*n);i<=Math.round(b*n);i++)out.push(pts[i%n]);return 'M'+out.map(p=>p[0].toFixed(0)+' '+p[1].toFixed(0)).join('L')};
 const full='M'+pts.map(p=>p[0].toFixed(0)+' '+p[1].toFixed(0)).join('L')+'Z';
 const at=(p:number)=>{const f=((p%1)+1)%1*n,i=Math.floor(f)%n,j=(i+1)%n,k=f-Math.floor(f);return [pts[i][0]+(pts[j][0]-pts[i][0])*k,pts[i][1]+(pts[j][1]-pts[i][1])*k]};
 const cx=xs.reduce((a,b)=>a+b,0)/n,cy=ys.reduce((a,b)=>a+b,0)/n;
 // Unit normal at a point, flipped to face outward from the circuit's centre (tags out, sector labels in).
 const normal=(p:number)=>{const [x1,y1]=at(p-.004),[x2,y2]=at(p+.004);const dx=x2-x1,dy=y2-y1,l=Math.hypot(dx,dy)||1;let ux=-dy/l,uy=dx/l;
  const [px,py]=at(p);if((px-cx)*ux+(py-cy)*uy<0){ux=-ux;uy=-uy}return [ux,uy]};
 // Sector boundaries from the timing feed's mini-sector counts (approximate: mini-sectors aren't equal length).
 const tot=segments.reduce((a,b)=>a+b,0);
 const sel=rows.find(c=>c.number===focus);
 const bounds=tot&&segments.length===3?[0,segments[0]/tot,(segments[0]+segments[1])/tot,1]:[0,1/3,2/3,1];
 const r=span/66,stroke=span/58;
 const pitLen=track.pit?((track.pit.exit-track.pit.entry)%1+1)%1:null;
 const inPit=usePitMotion(rows,speed,paused,pitLen,track.pit?.exit??null,smooth);
 const cars=rows.filter(c=>c.progress!=null&&!c.knocked_out&&!inPit.has(c.number)).sort((a,b)=>b.position-a.position);
 // Tags: push a car's tag further out when another tag sits close by along the lap.
 const placed:{p:number;lvl:number}[]=[];
 const tags=new Map<string,number>();
 [...cars].sort((a,b)=>a.position-b.position).forEach(c=>{let lvl=0;while(placed.some(q=>q.lvl===lvl&&Math.min(Math.abs(q.p-prog(c)),1-Math.abs(q.p-prog(c)))<.018))lvl++;placed.push({p:prog(c),lvl});tags.set(c.number,lvl)});
 // Pit lane: the racing line offset to the inside, easing out at the entry and back in at the exit.
 const pit=useMemo(()=>{if(!track.pit)return null;const {entry,exit}=track.pit;const len=((exit-entry)%1+1)%1,ramp=Math.min(.018,len/4),d=stroke*1.6;
  const out:number[][]=[];for(let i=0;i<=160;i++){const t=i/160*len,p=entry+t;const e=Math.min(1,t/ramp,(len-t)/ramp),k=e*e*(3-2*e);
   const [x,y]=at(p),[ux,uy]=normal(p);out.push([x-ux*d*k,y-uy*d*k])}
  const mid=out[Math.round(out.length*.55)];const [ux,uy]=normal(entry+len*.55);
  const pat=(q:number)=>{const f=Math.max(0,Math.min(1,q))*(out.length-1),i=Math.min(out.length-2,Math.floor(f)),k=f-i;return [out[i][0]+(out[i+1][0]-out[i][0])*k,out[i][1]+(out[i+1][1]-out[i][1])*k]};
  return {d:'M'+out.map(q=>q[0].toFixed(0)+' '+q[1].toFixed(0)).join('L'),lx:mid[0]-ux*stroke*1.5,ly:mid[1]-uy*stroke*1.5,at:pat,entry,len}},[pts,track.pit]);
 const N=Math.max(marshals,16);const zones:{a:number;b:number;label:string;dbl:boolean}[]=yellows.length
  ?yellows.map(y=>({a:(y.sector-1)/N,b:y.sector/N,label:y.double?'DOUBLE YELLOW':'YELLOW FLAG',dbl:y.double}))
  :flag==='yellow'?[{a:0,b:1,label:'',dbl:false}]:[];
 const [lx,ly]=at(0),[nx,ny]=normal(0);
 const checker=[];for(let i=-3;i<3;i++)for(let j=0;j<2;j++)checker.push(<rect key={i+'_'+j} x={lx+nx*stroke*.5*i-stroke*.25} y={ly+ny*stroke*.5*i-stroke*.25} width={stroke*.5} height={stroke*.5}
  transform={`rotate(${Math.atan2(ny,nx)*180/Math.PI} ${lx} ${ly}) translate(${j*stroke*.5-stroke*.25} 0)`} className={(i+j)%2?'chk-w':'chk-b'}/>);
 return <svg className={'rhx-livemap flag-'+flag} viewBox={`${minx-pad} ${miny-pad} ${w} ${h}`} role="img" aria-label="Approximate car positions on the circuit">
  <defs><filter id="rhx-glow" filterUnits="userSpaceOnUse" x={minx-pad*2} y={miny-pad*2} width={w+pad*2} height={h+pad*2}><feGaussianBlur stdDeviation={stroke*.9}/></filter></defs>
  <path d={full} className="glow" strokeWidth={stroke*2.6} filter="url(#rhx-glow)"/>
  {pit&&<g className="pitlane"><path d={pit.d} className="kerb" strokeWidth={stroke*.95}/><path d={pit.d} className="pit-road" strokeWidth={stroke*.55}/>
   <text x={pit.lx} y={pit.ly} fontSize={stroke*.95} className="pit-label">PIT</text></g>}
  <path d={full} className="kerb" strokeWidth={stroke*1.55}/>
  <path d={full} className="asphalt" strokeWidth={stroke}/>
  {/* Selected driver: each sector they've completed on this lap, in its timing colour (purple overall best, green personal best, yellow otherwise). */}
  {sel&&sel.sectors.slice(0,3).map((x,i)=>{if(!x.value)return null;
   if(sel.progress!=null&&sel.progress<bounds[i+1]-.002)return null; // not completed yet on this lap
   const k=x.overall?'p':x.personal?'g':'y';
   return <path key={i} d={path(bounds[i],bounds[i+1])} className={'mini '+k} strokeWidth={stroke*.62}/>})}
  {[1,2].map(i=>{const [x,y]=at(bounds[i]),[ux,uy]=normal(bounds[i]);return <g key={i} className="sector-mark">
   <line x1={x-ux*stroke*.9} y1={y-uy*stroke*.9} x2={x+ux*stroke*.9} y2={y+uy*stroke*.9} strokeWidth={stroke*.18}/></g>})}
  {[0,1,2].map(i=>{const m=(bounds[i]+bounds[i+1])/2,[x,y]=at(m),[ux,uy]=normal(m);return <text key={i} x={x-ux*stroke*2.4} y={y-uy*stroke*2.4} className="sector-label" fontSize={stroke*1.3}>S{i+1}</text>})}
  {/* Yellow flags: hazard stripes on the flagged part of the track, so they never read as a slower sector.
      Marshal sectors are placed evenly around the lap (approximate); without a sector number the whole track is striped. */}
  {zones.map((z,i)=>{const d=z.b-z.a>=1?full:path(z.a,z.b);
    return <g key={i} className={'hazard'+(z.dbl?' is-double':'')}>
     <path d={d} className="hz-glow" strokeWidth={stroke*2.2} filter="url(#rhx-glow)"/>
     <path d={d} className="hz-base" strokeWidth={stroke*1.05}/>
     <path d={d} className="hz-stripes" strokeWidth={stroke*1.05} strokeDasharray={`${stroke*.7} ${stroke*.7}`} style={{'--hz':`${stroke*1.4}px`} as React.CSSProperties}/>
    </g>})}
  <g className="line">{checker}</g>
  {cars.map(c=>{const [x,y]=at(prog(c)),[ux,uy]=normal(prog(c));const lvl=tags.get(c.number)||0;const out=stroke*(2.2+lvl*1.9);
   const tx=ux*out,ty=uy*out;const on=focus===c.number,lead=c.position===1;const big=on||lead?1.25:1;
   return <g key={c.number} className={'car'+(on?' is-focus':'')+(focus&&!on?' is-dim':'')} style={{transform:`translate(${x}px,${y}px)`,'--team':teamColor(c.color)} as React.CSSProperties}
    onClick={()=>onFocus(c.number)}>
    <line x1={0} y1={0} x2={tx*.72} y2={ty*.72} className="leader" strokeWidth={stroke*.1}/>
    <g transform={`translate(${tx} ${ty})`} className="tag"><rect x={-r*2.35} y={-r*.95} width={r*4.7} height={r*1.9} rx={r*.35}/>
     <rect x={-r*2.35} y={-r*.95} width={r*.55} height={r*1.9} className="tag-team"/>
     <text x={r*.3} y={r*.05} fontSize={r*1.35}>{c.code}</text></g>
    {on&&<circle r={r*2.4} className="pulse"/>}
    <circle r={r*1.15*big} className="disc"/>
    <text y={r*.05} fontSize={r*1.25*big} className="pos">{c.position}</text>
   </g>})}
  {/* Cars in the pit lane: small team discs at their box, driving along the lane on the way in and out. */}
  {pit&&rows.filter(c=>inPit.has(c.number)).map(c=>{const q=inPit.get(c.number)!.q;const [x,y]=pit.at(q);const [ux,uy]=normal(pit.entry+pit.len*q);
   const on=focus===c.number,moving=q>0&&q<1&&Math.abs(q-inPit.get(c.number)!.target)>.001;const tx=-ux*stroke*2.3,ty=-uy*stroke*2.3;
   return <g key={c.number} className={'car in-pit'+(on?' is-focus':'')+(focus&&!on?' is-dim':'')+(moving?' is-moving':'')} style={{transform:`translate(${x}px,${y}px)`,'--team':teamColor(c.color)} as React.CSSProperties}
    onClick={()=>onFocus(c.number)}><title>{c.code} · in the pit lane</title>
    {(on||moving)&&<><line x1={0} y1={0} x2={tx*.72} y2={ty*.72} className="leader" strokeWidth={stroke*.1}/>
     <g transform={`translate(${tx} ${ty})`} className="tag"><rect x={-r*2.35} y={-r*.95} width={r*4.7} height={r*1.9} rx={r*.35}/>
      <rect x={-r*2.35} y={-r*.95} width={r*.55} height={r*1.9} className="tag-team"/>
      <text x={r*.3} y={r*.05} fontSize={r*1.35}>{c.code}</text></g></>}
    {on&&<circle r={r*1.6} className="pulse"/>}
    <circle r={r*(moving||on?.8:.55)} className="disc"/>
   </g>})}
  {/* Flag labels sit above the cars so a tag never hides them. */}
  {zones.map((z,i)=>{if(!z.label)return null;const m=(z.a+z.b)/2,[x,y]=at(m),[ux,uy]=normal(m);
   return <g key={i} transform={`translate(${x-ux*stroke*3.2} ${y-uy*stroke*3.2})`} className={'hz-flag'+(z.dbl?' is-double':'')}>
    <rect x={-stroke*(z.label.length*.36+.9)} y={-stroke*.85} width={stroke*(z.label.length*.72+1.8)} height={stroke*1.7} rx={stroke*.3}/>
    <text fontSize={stroke*1.05}>{z.label}</text></g>})}
 </svg>;
}

const store={get:(k:string,d:string)=>{try{return localStorage.getItem('rhx-comm-'+k)??d}catch{return d}},set:(k:string,v:string)=>{try{localStorage.setItem('rhx-comm-'+k,v)}catch{}}};

/** One audio channel for the whole commentary panel: the voice queue, real radio before a line, and the ▶ Radio button
 * all go through it, so clips never overlap and every switch (Voice off, Stream safe, leaving the page) stops it. */
function useAudioChannel(){
 const el=useRef<HTMLAudioElement|null>(null),kind=useRef<'voice'|'radio'|null>(null);
 const stop=()=>{const a=el.current;if(a){a.onended=null;a.onerror=null;a.pause();a.removeAttribute('src');a.load()}el.current=null;kind.current=null;
  if(typeof speechSynthesis!=='undefined')speechSynthesis.cancel()};
 const play=(url:string,k:'voice'|'radio',onEnd:()=>void,onFail:()=>void,manual=false)=>{
  // Team radio has one owner on the page (audioBus): a clip the 3D broadcast card already played is not played again
  // automatically (the ▶ Radio button still replays it on request).
  if(k==='radio'){if(!manual&&!claimRadio(url)){onEnd();return}stopRadio()}
  stop();const a=new Audio(url);el.current=a;kind.current=k;
  a.onended=()=>{if(el.current===a){el.current=null;kind.current=null;onEnd()}};a.onerror=()=>{if(el.current===a){el.current=null;kind.current=null;onFail()}};
  a.play().catch(()=>{if(el.current===a){el.current=null;kind.current=null;onFail()}})};
 useEffect(()=>()=>stop(),[]);
 return {stop,play,kind};
}
type Channel=ReturnType<typeof useAudioChannel>;

/** Reads new commentary lines aloud: the engine's Kokoro voice when the line has audio, otherwise the browser's voice.
 * Lines already on screen when the page opens are not read. When the engine restarts, or the recording changes or is
 * seeked, the panel's speech starts over (the engine's `run` changes), so an OBS page open for hours keeps talking.
 * Stream safe (default): team radio is only summarized. Real radio mode plays the clip first (not stream safe). */
function useVoice(lines:Line[],on:boolean,voiceName:string,realRadio:boolean,textOnly:boolean,run:string|undefined,ch:Channel){
 const spoken=useRef(-1),queue=useRef<Line[]>([]),busy=useRef(false),current=useRef<Line|null>(null),lastRun=useRef(run);
 const opts=useRef({voiceName,realRadio,textOnly});opts.current={voiceName,realRadio,textOnly};
 const stop=()=>{ch.stop();busy.current=false;current.current=null};
 const pump=()=>{if(busy.current||!queue.current.length)return;const item=queue.current.shift()!;busy.current=true;current.current=item;
  const done=()=>{if(current.current!==item)return;busy.current=false;current.current=null;pump()};
  const browser=()=>{if(current.current!==item)return;
   // No voice for this language: text only, as the panel says. Never read Albanian in an English voice.
   const v=typeof speechSynthesis==='undefined'?undefined:speechSynthesis.getVoices().find(v=>v.name===opts.current.voiceName);
   if(opts.current.textOnly||!v){done();return}
   const u=new SpeechSynthesisUtterance(item.text);u.voice=v;u.lang=v.lang;u.rate=1.07;u.onend=done;u.onerror=done;speechSynthesis.speak(u)};
  const say=()=>{if(current.current!==item)return;if(item.audio)ch.play(item.audio,'voice',done,browser);else browser()};
  if(opts.current.realRadio&&item.radio?.url)ch.play(item.radio.url,'radio',say,say);else say()};
 useEffect(()=>{
  if(lastRun.current!==run){const had=lastRun.current;lastRun.current=run;
   if(had!==undefined){stop();queue.current=[];spoken.current=0}}   // a new engine run or timeline: ids start again
  const max=Math.max(spoken.current,...lines.map(l=>l.id));
  if(spoken.current<0){spoken.current=max;return}
  const fresh=lines.filter(l=>l.id>spoken.current).sort((a,b)=>a.id-b.id);spoken.current=max;
  if(!on||!fresh.length)return;
  // Live, not a playlist: only the newest line waits (an urgent one wins), and an urgent line cuts off a calmer one.
  const next=[...fresh].reverse().find(l=>l.prio>=5)||fresh[fresh.length-1];
  queue.current=[next];
  if(busy.current&&next.prio>=5&&(current.current?.prio??0)<5)stop();
  pump()},[lines,on,run]);
 useEffect(()=>{if(!on){queue.current=[];stop()}},[on]);
 // Stream safe means no F1 audio at all, immediately: cut a real radio clip that is already playing.
 useEffect(()=>{if(!realRadio&&ch.kind.current==='radio'){stop();pump()}},[realRadio]);
}

function useVoices(lang:string){
 const [voices,setVoices]=useState<SpeechSynthesisVoice[]>([]);
 useEffect(()=>{if(typeof speechSynthesis==='undefined')return;const load=()=>setVoices(speechSynthesis.getVoices());load();
  speechSynthesis.addEventListener('voiceschanged',load);return()=>speechSynthesis.removeEventListener('voiceschanged',load)},[]);
 const mine=voices.filter(v=>v.lang.toLowerCase().startsWith(lang));
 // Neural voices ("Natural"/"Online", Edge) sound far better than the old desktop ones; then Google's.
 const rank=(v:SpeechSynthesisVoice)=>/natural|online/i.test(v.name)?0:/google/i.test(v.name)?1:2;
 return [...mine].sort((a,b)=>rank(a)-rank(b)||a.name.localeCompare(b.name));
}

function Commentator({c,rows}:{c:Commentary;rows:Row[]}){
 const [voiceOn,setVoiceOn]=useState(false);
 const voices=useVoices(c.language==='sq'?'sq':'en');
 const [voiceName,setVoiceName]=useState(store.get('voice',''));
 const voice=voices.find(v=>v.name===voiceName)?.name||voices[0]?.name||'';
 const kokoro=!!c.tts?.available&&c.language==='en';
 const textOnly=!kokoro&&!voices.length;
 // Per viewer and remembered, but always starts in the safe mode unless chosen: real radio audio belongs to F1.
 const [realRadio,setRealRadio]=useState(store.get('radio-mode','safe')==='real');
 const pickRadio=(real:boolean)=>{setRealRadio(real);store.set('radio-mode',real?'real':'safe')};
 const ch=useAudioChannel();
 useVoice(c.lines,voiceOn&&c.enabled,voice,realRadio,textOnly,c.run,ch);
 const play=(url:string)=>ch.play(url,'radio',()=>{},()=>setErr('That radio clip could not be played.'),true);
 const color=(code:string)=>teamColor(rows.find(r=>r.code===code)?.color);
 const [pending,setPending]=useState(''),[err,setErr]=useState('');
 const set=async(body:any,what:string)=>{setPending(what);setErr('');try{await post('/api/live/commentary',body)}catch(e){setErr(`Couldn't change that: ${(e as Error).message}`)}finally{setPending('')}};
 return <div className="rhx-comm">
  <div className="rhx-comm-head"><h3>AI Commentator</h3>
   <a href="/design/race-host/index.html" target="_blank" rel="noreferrer" title="Optional experiment: start the platform with -WithRaceHost first">OBS avatar (optional)</a>
   <span className={'rhx-comm-dot'+(c.enabled?' on':'')}/>
   <div className="rhx-seg is-inline" role="group" aria-label="Commentator (applies to the stream)">
    <button type="button" className={c.enabled?'on':''} disabled={!!pending} aria-pressed={c.enabled} onClick={()=>set({enabled:!c.enabled},'enabled')}>{c.enabled?'On':'Off'}</button>
    {['en','sq'].map(l=><button type="button" key={l} disabled={!!pending} aria-pressed={c.language===l} className={c.language===l?'on':''} onClick={()=>set({language:l},'language')}>{l.toUpperCase()}</button>)}
   </div>
   <div className="rhx-seg is-inline" role="group" aria-label="Voice in this browser">
    <button type="button" className={voiceOn?'on':''} aria-pressed={voiceOn} onClick={()=>setVoiceOn(!voiceOn)}>Voice</button>
   </div></div>
  <p className="rhx-comm-scope"><b>On/Off, language and the Kokoro voice apply to the stream</b> (every browser and OBS). Voice and Team radio are only for this browser.</p>
  <div className="rhx-comm-mode"><span>Team radio</span>
   <div className="rhx-seg is-inline">
    <button type="button" className={!realRadio?'on':''} aria-pressed={!realRadio} onClick={()=>pickRadio(false)} aria-label="Stream safe" title="AI summaries only. Safe for TikTok / YouTube.">Stream safe</button>
    <button type="button" className={realRadio?'on is-warn':''} aria-pressed={realRadio} onClick={()=>pickRadio(true)} aria-label="Real radio" title="Plays the real clips and shows what was said. The audio belongs to F1: don't stream it.">Real radio</button>
   </div>
   {realRadio&&<small className="rhx-comm-warn">Not stream safe: real clips belong to F1.</small>}</div>
  {voiceOn&&kokoro&&<label className="rhx-comm-voice">Voice (applies to the stream) <select value={c.tts!.voice} disabled={!!pending} onChange={e=>set({voice:e.target.value},'voice')}>
   {Object.entries(c.tts!.voices).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>}
  {voiceOn&&!kokoro&&voices.length>0&&<label className="rhx-comm-voice">Browser voice <select value={voice} onChange={e=>{setVoiceName(e.target.value);store.set('voice',e.target.value)}}>
   {voices.map(v=><option key={v.name} value={v.name}>{v.name.replace(/^Microsoft /,'').replace(/ - .*$/,'')}</option>)}</select></label>}
  {voiceOn&&textOnly&&<p className="rhx-comm-note">This browser has no {c.language==='sq'?'Albanian':'English'} voice, so lines show as text only (nothing is read aloud).</p>}
  {err&&<p className="rhx-error" role="alert">{err}</p>}
  {c.lines.length?<ol>{c.lines.slice(0,14).map((l,i)=><li key={l.id} className={(i===0?'is-new ':'')+(l.prio>=4?'is-big':'')}>
    <time>{l.time}</time>
    <div><p>{l.text}</p>
     {(l.drivers.length>0||l.radio)&&<div className="rhx-comm-tags">{l.drivers.map(d=><b key={d} style={{'--team':color(d)} as React.CSSProperties}>{d}</b>)}
      {l.radio&&(realRadio&&l.radio.url?<button type="button" onClick={()=>play(l.radio!.url!)}>▶ Radio {l.radio.code}</button>:<em>Radio summary</em>)}</div>}
     {realRadio&&l.radio?.transcript&&<small className="rhx-comm-radio">“{l.radio.transcript}”</small>}</div></li>)}</ol>
   :<p className="rhx-comm-empty">{c.enabled?'Listening to the feed. Lines appear as things happen: flags, race control, improvements, overtakes, pit stops and team radio.':'Commentary is off.'}</p>}
  <p className="rhx-comm-note">{c.ai?`AI lines by ${c.model}.`:'Plain lines from the data. Start Ollama (free, on your PC) for AI commentary.'}
   {kokoro?' Voice: Kokoro (local).':''} {realRadio?'Real radio: clips play before the comment.':'Stream safe: team radio is summarized, never played.'}
   {c.radio&&<> {c.radio}</>}{c.error&&<span className="rhx-error"> {c.error}</span>}</p>
 </div>;
}

const recTitle=(f:File)=>f.title||(f.meeting?`${f.meeting.replace(/ Grand Prix$/,' GP')} · ${f.session||'Session'}`:f.name);
// When the recording started: from its name (live_2026-11-08_1804[ss].txt), else when it was last written.
const recWhen=(f:File)=>{const m=/(\d{4})-(\d\d)-(\d\d)_(\d\d)(\d\d)/.exec(f.name);
 const d=m?new Date(+m[1],+m[2]-1,+m[3],+m[4],+m[5]):new Date(f.modified*1000);return Number.isNaN(+d)?'':d.toLocaleString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})};

function Sources({files,filesErr,showHidden,setShowHidden,onOpen,onRecord,onLabel,recorder,busy,session}:{files:File[]|null;filesErr:string;showHidden:boolean;setShowHidden:(v:boolean)=>void;
 onOpen:(f:File,mode:'follow'|'replay')=>void;onRecord:()=>void;onLabel:(f:File,patch:{title?:string;hidden?:boolean})=>Promise<void>;recorder:Snap['recorder']|undefined;busy:boolean;session?:string}){
 const [editing,setEditing]=useState(''),[draft,setDraft]=useState('');
 return <div className="rhx-live-sources">
  <div className="rhx-live-start">
   <h2>{session?`Watch ${session} live`:'Watch a session live'}</h2>
   <p>Your engine connects to F1's free live timing: positions, gaps, sectors, tyres, flags and race control. Car positions on the map are estimated from mini-sectors, since exact GPS needs an F1 TV login.</p>
   <Action disabled={busy||recorder?.running} sub={recorder?.running?`Recording to ${recorder.file}`:'Starts recording and opens it live'} onClick={onRecord}>{recorder?.running?'Recording':'Go live'}</Action>
   {recorder&&!recorder.running&&recorder.exit_code!=null&&<p className="rhx-error">The recorder stopped (exit {recorder.exit_code}). {recorder.log.split('\n').filter(Boolean).slice(-2).join(' ')}</p>}
  </div>
  <div className="rhx-live-files"><div className="rhx-row"><h3>Recordings</h3>
    <label className="rhx-check"><input type="checkbox" checked={showHidden} onChange={e=>setShowHidden(e.target.checked)}/><span>Show hidden</span></label></div>
   {filesErr&&<p className="rhx-error" role="alert">The recordings list didn't load: {filesErr}</p>}
   {files==null?(!filesErr&&<Note>Loading your recordings…</Note>)
   :files.length?<ul>{files.map(f=>{const key=f.folder+'/'+f.name;return <li key={key} className={f.hidden?'is-hidden':''}>
    {editing===key?<form className="rhx-rec-edit" onSubmit={async e=>{e.preventDefault();await onLabel(f,{title:draft});setEditing('')}}>
      <input aria-label={`Name for ${f.name}`} value={draft} maxLength={80} autoFocus onChange={e=>setDraft(e.target.value)} placeholder={recTitle({...f,title:''})}/>
      <button type="submit" className="on">Save</button><button type="button" onClick={()=>setEditing('')}>Cancel</button></form>
     :<span><b>{recTitle(f)}</b><small>{f.growing?'Recording now':recWhen(f)}, {(f.size/1e6).toFixed(1)} MB · {f.name}</small></span>}
    {f.growing&&<button type="button" className="on" onClick={()=>onOpen(f,'follow')}>Follow live</button>}
    <button type="button" onClick={()=>onOpen(f,'replay')}>Replay</button>
    <button type="button" className="rhx-link" onClick={()=>{setEditing(key);setDraft(f.title)}}>Rename</button>
    <button type="button" className="rhx-link" onClick={()=>onLabel(f,{hidden:!f.hidden})}>{f.hidden?'Unhide':'Hide'}</button></li>})}</ul>
   :<Note>No recordings yet. Files from scripts\record_live.py in the tmp folder appear here too.</Note>}
   <Note>Rename and Hide only change how a recording is listed. The files stay on disk.</Note>
  </div>
 </div>;
}

export default function Live(){
 const {snap,err,lastOk}=useLive();
 const {calendar}=useSession();
 const [files,setFiles]=useState<File[]|null>(null),[filesErr,setFilesErr]=useState(''),[showHidden,setShowHidden]=useState(false);
 const [busy,setBusy]=useState(false),[actionErr,setActionErr]=useState('');
 const [track,setTrack]=useState<Track|null>(null),[trackErr,setTrackErr]=useState(''),[trackTry,setTrackTry]=useState(0);
 const [focus,setFocus]=useState<string|null>(null);
 // 2D map or 3D broadcast: this viewer's own choice, like the selected driver and camera.
 const [view,setView]=useState<'2d'|'3d'>(viewStore.get);
 const pickView=(v:'2d'|'3d')=>{setView(v);viewStore.set(v)};
 const webgl=useMemo(hasWebGL,[]);
 const loadFiles=()=>request<File[]>('/api/live/files'+(showHidden?'?hidden=true':'')).then(f=>{setFiles(f);setFilesErr('')}).catch(e=>setFilesErr((e as Error).message));
 useEffect(()=>{loadFiles();const t=setInterval(loadFiles,5000);return()=>clearInterval(t)},[showHidden]);
 const s=snap?.session,rows=snap?.drivers||[],feed=snap?.feed;
 const trackKey=s?.meeting?`${s.meeting}|${s.year||''}`:'';
 // The circuit for the session on screen. A slow answer for an earlier circuit is ignored, and a failure can be retried.
 useEffect(()=>{if(!trackKey)return;setTrack(null);setTrackErr('');
  const meeting=s!.meeting,year=s!.year;const local=bundledCircuit(meeting);if(local){setTrack(local);return}
  const ctrl=new AbortController();let current=true;const timer=setTimeout(()=>ctrl.abort(),45000);
  request<Track>(`/api/live/track?event=${encodeURIComponent(meeting)}${year?'&year='+year:''}`,{signal:ctrl.signal})
   .then(t=>{if(current)setTrack(t)})
   .catch(e=>{if(current)setTrackErr(ctrl.signal.aborted?'Building the circuit took too long.':(e as Error).message)}).finally(()=>clearTimeout(timer));
  return()=>{current=false;ctrl.abort();clearTimeout(timer)}},[trackKey,trackTry]);
 const act=async(what:string,fn:()=>Promise<unknown>)=>{setBusy(true);setActionErr('');try{await fn()}catch(e){setActionErr(`${what} didn't work: ${(e as Error).message}`)}finally{setBusy(false)}};
 const open=(f:File,mode:'follow'|'replay')=>act('Opening the recording',()=>post('/api/live/open',{folder:f.folder,name:f.name,mode,speed:1}));
 const record=()=>act('Going live',async()=>{await post('/api/live/record',{});loadFiles()});
 const label=(f:File,patch:{title?:string;hidden?:boolean})=>act('Saving that',async()=>{await post('/api/live/files/label',{folder:f.folder,name:f.name,...patch});await loadFiles()});
 const control=(body:any)=>act('That control',()=>post('/api/live/control',body));
 // Title for the start screen: the session running now or next, from the calendar; otherwise neutral.
 const nextSession=useMemo(()=>{const now=Date.now();let best:{name:string;t:number}|null=null;
  for(const r of calendar){const round=toRound(r,now);for(const x of round.sessions){if(!x.start)continue;const t=+x.start;
   if(t+3*3600e3>now&&t-4*86400e3<now&&(!best||t<best.t))best={name:`${round.short} ${x.name.toLowerCase()}`,t}}}
  return best?.name},[calendar]);
 const cut=knockFrom(s?.part,rows.length);
 const stale=feed?.mode==='follow'&&feed.updated&&Date.now()/1000-feed.updated>20;
 const offline=!!err&&!!snap;   // the engine stopped answering: what is on screen is old
 const sel=rows.find(r=>r.number===focus);

 if(!feed)return <main className="rhx-page-body"><header className="rhx-head"><div><h1 className="rhx-head-title">Live.</h1><p className="rhx-head-lede">The timing screen, your way. Follow a session as it happens or replay a recording at any speed.</p></div></header>
  {err&&<p className="rhx-error" role="alert">The engine isn't answering: {err}. Check that it is running; this page retries every second.</p>}
  {actionErr&&<p className="rhx-error" role="alert">{actionErr}</p>}
  {busy&&<p className="rhx-note" role="status">Working…</p>}
  <Sources files={files} filesErr={filesErr} showHidden={showHidden} setShowHidden={setShowHidden} onOpen={open} onRecord={record} onLabel={label} recorder={snap?.recorder} busy={busy} session={nextSession}/></main>;

 const mapEl=track?<TrackMap track={track} rows={rows} segments={snap?.segments||[]} flag={snap?.flag?.state||'green'} focus={focus} onFocus={n=>setFocus(focus===n?null:n)} speed={feed.mode==='replay'?feed.speed:1} paused={offline||(feed.mode==='replay'?feed.paused:!!stale)} yellows={snap?.yellows||[]} marshals={snap?.marshal_sectors||0}/>
  :<Blank title={trackErr?'No circuit outline':'Loading circuit…'} mark="◌">{trackErr?<>The map needs a past session at this circuit. The timing tower still works. <button type="button" className="rhx-link" onClick={()=>setTrackTry(n=>n+1)}>Try again</button></>:undefined}</Blank>;

 return <main className="rhx-page-body rhx-live-page">
  {offline&&<p className="rhx-error rhx-live-stale" role="alert">Lost contact with the engine{lastOk?` ${Math.round((Date.now()-lastOk)/1000)} s ago`:''}. The screen below is frozen and not current. Retrying every second… ({err})</p>}
  {actionErr&&<p className="rhx-error" role="alert">{actionErr}</p>}
  <section className={'rhx-livebar flag-'+(snap?.flag?.state||'green')+(offline?' is-stale':'')}>
   <div className="rhx-livebar-event"><span className={'rhx-livedot '+(feed.mode==='follow'&&!stale&&!offline?'on':'')}/>{offline?'Disconnected':feed.mode==='follow'?(stale?'Waiting for data':'Live'):feed.ended?'Replay ended':'Replay'}
    <b>{s?.meeting||'Session'}</b><span>{s?.name}</span></div>
   {s?.qualifying&&<div className="rhx-phases">{[1,2,3].map(p=><span key={p} className={s.part===p?'on':s.part&&p<s.part?'done':''}>Q{p}</span>)}</div>}
   {s?.laps&&<div className="rhx-livelap"><small>Lap</small><b>{s.lap??'—'}/{s.laps}</b></div>}
   <div className="rhx-liveclock"><small>Remaining</small><b>{hms(s?.remaining)}</b></div>
   <div className="rhx-liveflag"><i/>{snap?.yellows?.length?`${snap.yellows.some(y=>y.double)?'Double yellow':'Yellow'} · marshal sector ${snap.yellows.map(y=>y.sector).join(', ')}`:snap?.flag?.text}</div>
   {snap?.weather?.air!=null&&<div className="rhx-liveweather"><span>Air <b>{snap.weather.air}°</b></span><span>Track <b>{snap.weather.track}°</b></span>{snap.weather.rain&&<span className="rain">Rain</span>}</div>}
  </section>

  {feed.mode==='replay'&&feed.start&&feed.end&&<div className="rhx-replaybar">
   <button type="button" disabled={busy||offline} onClick={()=>control({paused:!feed.paused})}>{feed.ended?'Play again':feed.paused?'Play':'Pause'}</button>
   <input type="range" min={0} max={Math.round(feed.end-feed.start)} value={Math.round((feed.clock||feed.start)-feed.start)} disabled={offline} onChange={e=>control({seek:Number(e.target.value)})} aria-label="Replay position"/>
   <span>{hms((feed.clock||feed.start)-feed.start)} / {hms(feed.end-feed.start)}</span>
   <div className="rhx-seg is-inline">{[1,2,5,10,30].map(v=><button type="button" key={v} disabled={offline} aria-pressed={feed.speed===v} className={feed.speed===v?'on':''} onClick={()=>control({speed:v})}>{v}×</button>)}</div>
  </div>}
  {feed.ended&&<p className="rhx-note" role="status">End of the recording. Play starts it again from the beginning.</p>}

  <div className="rhx-viewswitch"><div className="rhx-seg is-inline" role="group" aria-label="Circuit view">
    <button type="button" className={view==='2d'?'on':''} aria-pressed={view==='2d'} onClick={()=>pickView('2d')}>2D Map</button>
    <button type="button" className={view==='3d'?'on':''} aria-pressed={view==='3d'} onClick={()=>pickView('3d')}>3D Broadcast</button></div>
   <small>{view==='3d'?'Click a driver in the timing tower to ride with them. Camera and driver only change your screen.':'Positions on the map are estimated from mini-sectors.'}</small></div>
  {view==='3d'&&(webgl?<Suspense fallback={<p className="rhx-note" role="status">Loading the 3D view…</p>}>
    <Broadcast3D feed={feed} focus={focus} onFocus={setFocus} rows={rows} fallback={mapEl} mapRotation={track?.rotation||0} radioUrl="/api/live/radio-events"
     tower={{title:`${(s?.meeting||'Session').replace(/ Grand Prix$/,' GP')} · ${s?.name||''}`,lap:s?.lap??null,total:s?.laps??null,
      rows:rows.filter(r=>!r.knocked_out).map(r=>({id:r.number,code:r.code,color:teamColor(r.color),pos:r.position<99?r.position:null,interval:r.position===1?null:r.interval,
       lapped:/L/i.test(r.interval||'')?r.interval:null,tyre:r.tyre?.compound||null,pit:!!(r.in_pit||r.pit_out),out:!!(r.retired||r.stopped)}))}}/></Suspense>
   :<div className="rhx-b3d-nogl"><p className="rhx-note">This browser has no WebGL, so the 3D view can't run here. The 2D map shows the same positions.</p>{mapEl}</div>)}
  <div className="rhx-livegrid">
   <div className="rhx-tower-wrap rhx-livetower">
    <table className="rhx-tower is-live"><thead><tr><th>Pos</th><th>Driver</th><th>Gap</th><th>Int</th><th>Best</th><th>Last</th><th>Mini-sectors</th><th>Tyre</th></tr></thead>
     <tbody>{rows.map((r,i)=><tr key={r.number} className={[r.knocked_out?'is-out':'',cut&&r.position>=cut&&!r.knocked_out?'is-danger':'',cut&&r.position===cut?'is-cutline':'',focus===r.number?'on':''].join(' ')}
      style={{'--team':teamColor(r.color)} as React.CSSProperties} onClick={()=>setFocus(focus===r.number?null:r.number)}>
      <td className="rhx-pos">{r.position<99?r.position:'—'}</td>
      <td className="rhx-who"><b>{r.code}</b>{r.in_pit?<em className="pit">PIT</em>:r.pit_out?<em className="out">OUT</em>:r.retired||r.stopped?<em className="pit">STOP</em>:null}</td>
      <td>{i===0?(r.best||'—'):(r.gap||'—')}</td><td>{i===0?'':r.interval||''}</td>
      <td className={r.fastest?'is-fastest':''}>{r.best||'—'}</td>
      <td className={r.last.overall?'is-fastest':r.last.personal?'is-pb':''}>{r.last.value||'—'}</td>
      <td><span className="rhx-minis">{r.segments.map((sec,si)=><span key={si}>{sec.map((g,gi)=><i key={gi} className={segColor(g)}/>)}</span>)}</span></td>
      <td>{r.tyre.compound?<span className={'rhx-tyre t-'+(TYRE[r.tyre.compound]||'x')} title={`${r.tyre.compound}${r.tyre.new?', new':''}`}>{TYRE[r.tyre.compound]||'?'}</span>:'—'}</td>
     </tr>)}</tbody></table>
    <p className="rhx-legend-line"><span className="rhx-fastest-key"/>Fastest in the field <span className="rhx-pb-key"/>Personal best {cut&&<><span className="rhx-danger-key"/>Elimination zone</>}</p>
   </div>
   <aside className="rhx-liveside">
    <div className="rhx-livemap-wrap">{mapEl}
     {rows.some(r=>r.in_pit&&!r.knocked_out)&&<div className="rhx-pitlane"><span>Pit lane</span>{rows.filter(r=>r.in_pit&&!r.knocked_out).map(r=>
      <b key={r.number} style={{'--team':teamColor(r.color)} as React.CSSProperties}>{r.code}</b>)}</div>}
     {track&&<small className="rhx-livemap-note">Unofficial fan view, not affiliated with Formula 1. Positions estimated from mini-sectors. Circuit from {track.source}.</small>}</div>
    {sel&&<div className="rhx-livefocus" style={{'--team':teamColor(sel.color)} as React.CSSProperties}><b>{sel.code}</b><span>{sel.name}, {sel.team}</span>
     <dl><div><dt>Best</dt><dd>{sel.best||'—'}</dd></div><div><dt>Laps</dt><dd>{sel.laps??'—'}</dd></div><div><dt>Tyre</dt><dd>{sel.tyre.compound||'—'}{sel.tyre.laps!=null?` · ${sel.tyre.laps}L`:''}</dd></div><div><dt>Speed trap</dt><dd>{sel.speed_trap?`${Math.round(sel.speed_trap)} km/h`:'—'}</dd></div>
      {sel.sectors.map((x,i)=><div key={i}><dt>S{i+1}</dt><dd className={x.overall?'is-fastest':x.personal?'is-pb':''}>{x.value||'—'}</dd></div>)}</dl></div>}
    {snap?.commentary&&<Commentator c={snap.commentary} rows={rows}/>}
    <div className="rhx-livefeed"><h3>Race control</h3><ol>{(snap?.race_control||[]).slice(0,12).map((m,i)=><li key={i}>
     <time>{(m.time||'').slice(11,19)}</time><i style={{background:FLAG[String(m.flag||'').toUpperCase()]||'#3a4652'}}/><span>{m.message}</span></li>)}</ol></div>
   </aside>
  </div>
  <div className="rhx-row"><button type="button" className="rhx-link" disabled={busy} onClick={()=>act('Closing the recording',()=>post('/api/live/close',{}))}>Choose another recording</button>
   {snap?.recorder?.running&&<button type="button" className="rhx-link" disabled={busy} onClick={()=>act('Stopping the recording',()=>post('/api/live/stop-recording',{}))}>Stop recording</button>}
   <span className="rhx-count">{feed.file}, {feed.messages.toLocaleString()} messages</span></div>
 </main>;
}
