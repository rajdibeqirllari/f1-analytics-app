import {useEffect,useMemo,useRef,useState} from 'react';
import {request,teamColor} from '../../api';
import {useSession,useTask,useResource} from '../../state';
import {PageHead,Choice,Group,Action,JobBar,Blank,Note} from '../kit';

/* Race replay in the Live page's look: timing tower, broadcast map and driver card, driven by the
 * recorded positions the replay engine builds (the same frames the classic viewer plays). */

const BUNDLED=import.meta.glob('../circuits/*.json',{eager:true,import:'default'}) as Record<string,{rotation:number}>;
const slug=(v:string)=>v.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');

type Car={x:number|null;y:number|null;lap:number;speed:number;gear:number;throttle:number;brake:boolean;tyre:string;tyre_age:number;status:string;drs_active:boolean;position:number;gap:string};
type Frame={t:number;lap:number;track_status:string;drivers:Record<string,Car>};
type Payload={meta:{year:number;event:string;round:number;session:string;duration_seconds:number;sample_rate_hz:number};
 track:{centerline:number[][]};drivers:Record<string,{name:string;team:string;number:string;color:string}>;frames:Frame[];
 technical:{frame_count:number;driver_count:number;track_statuses:{start_time:number;end_time:number;label:string}[]}};

const RES=600;
const TYRE:Record<string,string>={SOFT:'S',MEDIUM:'M',HARD:'H',INTERMEDIATE:'I',WET:'W'};
const SESSION:Record<string,string>={R:'Race',Q:'Qualifying',S:'Sprint',SQ:'Sprint qualifying'};
const STATUS:Record<string,[string,string,string]>={ // label -> [map flag class, text, colour]
 GREEN:['green','Green flag','#2bd46b'],YELLOW:['yellow','Yellow flag','#ffd23f'],'SAFETY CAR':['sc','Safety car','#ff9f1c'],
 VSC:['vsc','Virtual safety car','#ff9f1c'],'VSC ENDING':['vsc','VSC ending','#ff9f1c'],RED:['red','Red flag','#ff463b']};
const status=(label:string)=>STATUS[label]||['green',label?label[0]+label.slice(1).toLowerCase():'—','#3a4652'];
const wrap=(d:number)=>((d%1)+1.5)%1-.5;
const hms=(s:number)=>{s=Math.max(0,s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=Math.floor(s%60);return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(x).padStart(2,'0')};

type Geo=ReturnType<typeof prepare>;
/** One pass over every frame: track position (0 = line), race distance and pit-lane flag per car. */
function prepare(pl:Payload){
 const raw=pl.track.centerline.filter(p=>p&&p[0]!=null&&p[1]!=null);
 // Equal-spacing resample so a lap fraction maps evenly onto the outline.
 const len=[0];for(let i=1;i<=raw.length;i++){const a=raw[i-1],b=raw[i%raw.length];len.push(len[i-1]+Math.hypot(b[0]-a[0],b[1]-a[1]))}
 const L=len[len.length-1];const res:number[][]=[];let j=0;
 for(let i=0;i<RES;i++){const d=i/RES*L;while(len[j+1]<d)j++;const a=raw[j],b=raw[(j+1)%raw.length],k=(d-len[j])/((len[j+1]-len[j])||1);res.push([a[0]+(b[0]-a[0])*k,a[1]+(b[1]-a[1])*k])}
 // Orientation: the bundled circuit's when we have one, otherwise the long side horizontal with the line on top.
 let rot=BUNDLED[`../circuits/${slug(pl.meta.event)}.json`]?.rotation;
 if(rot==null){const mx=res.reduce((a,p)=>a+p[0],0)/RES,my=res.reduce((a,p)=>a+p[1],0)/RES;let sxx=0,syy=0,sxy=0;
  for(const p of res){const dx=p[0]-mx,dy=p[1]-my;sxx+=dx*dx;syy+=dy*dy;sxy+=dx*dy}
  rot=-Math.atan2(2*sxy,sxx-syy)/2*180/Math.PI;
  const r=-rot*Math.PI/180;const y0=-(res[0][0]*Math.sin(r)+res[0][1]*Math.cos(r)),yc=-(mx*Math.sin(r)+my*Math.cos(r));if(y0>yc)rot+=180}
 const r=-rot*Math.PI/180,c=Math.cos(r),s=Math.sin(r);
 const tf=(x:number,y:number)=>[x*c-y*s,-(x*s+y*c)];
 const pts=res.map(p=>tf(p[0],p[1]));
 const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);const span=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));
 const off=span/120; // this far off the racing line at pit-limiter speed = pit lane / garage
 const proj=(x:number,y:number,hint:number)=>{let best=1e18,bi=0,bk=0;
  const scan=(from:number,to:number)=>{for(let q=from;q<to;q++){const i=((q%RES)+RES)%RES,a=pts[i],b=pts[(i+1)%RES];const dx=b[0]-a[0],dy=b[1]-a[1];
   const k=Math.max(0,Math.min(1,((x-a[0])*dx+(y-a[1])*dy)/((dx*dx+dy*dy)||1)));const ex=a[0]+dx*k-x,ey=a[1]+dy*k-y,e=ex*ex+ey*ey;if(e<best){best=e;bi=i;bk=k}}};
  if(hint>=0)scan(hint-30,hint+30);if(hint<0||Math.sqrt(best)>off)scan(0,RES);return {p:(bi+bk)/RES,d:Math.sqrt(best),i:bi}};
 const codes=Object.keys(pl.drivers),F=pl.frames.length;const t=new Float64Array(F);pl.frames.forEach((f,k)=>t[k]=f.t);
 const P:Record<string,Float32Array>={},D:Record<string,Float64Array>={},X:Record<string,Float32Array>={},Y:Record<string,Float32Array>={},O:Record<string,Uint8Array>={};
 const laps:Record<string,{end:number;time:number}[]>={};const out:Record<string,number>={};const bins=new Map<number,number[]>();
 for(const code of codes){const p=P[code]=new Float32Array(F),d=D[code]=new Float64Array(F),xx=X[code]=new Float32Array(F),yy=Y[code]=new Float32Array(F),o=O[code]=new Uint8Array(F);
  let hint=-1,started=false,lastMove=0,cross=-1,clean=true;const lap:{end:number;time:number}[]=laps[code]=[];
  for(let k=0;k<F;k++){const car=pl.frames[k].drivers[code];
   if(!car||car.x==null||car.y==null){if(k){p[k]=p[k-1];d[k]=d[k-1];xx[k]=xx[k-1];yy[k]=yy[k-1];o[k]=o[k-1]}continue}
   const [X0,Y0]=tf(car.x,car.y);const q=proj(X0,Y0,hint);hint=q.i;xx[k]=X0;yy[k]=Y0;p[k]=q.p;o[k]=q.d>off&&car.speed<=90?1:0;
   if(o[k]&&car.speed>0){const b=Math.floor(q.p*200);const c=bins.get(b)||[0,0,0];c[0]+=X0;c[1]+=Y0;c[2]++;bins.set(b,c)}
   if(!started){d[k]=(Math.max(1,car.lap)-1)+q.p-(car.lap<=1&&q.p>.5?1:0);started=true}
   else d[k]=d[k-1]+wrap(q.p-p[k-1]); // pit lane runs beside the track, so its projection still counts
   if(car.speed>0)lastMove=k;
   if(o[k])clean=false;
   // Lap times: when race distance passes a whole lap, timed between line crossings with no pit visit.
   if(k&&Math.floor(d[k])>Math.floor(d[k-1])&&d[k]-d[k-1]<.2){const at=t[k-1]+(t[k]-t[k-1])*((Math.floor(d[k])-d[k-1])/((d[k]-d[k-1])||1));
    if(cross>=0&&clean)lap.push({end:at,time:at-cross});cross=at;clean=true}}
  // Race only: a car that never moves again was retired from that point (status always says RUNNING).
  if(['R','S'].includes(pl.meta.session)&&t[F-1]-t[lastMove]>60)out[code]=t[lastMove]}
 const lead=new Float64Array(F);for(let k=0;k<F;k++){let m=-1e9;for(const code of codes)if(!(out[code]<=t[k]))m=Math.max(m,D[code][k]);lead[k]=Math.max(m,k?lead[k-1]:-1e9)}
 // Pit lane line from where cars actually drove at pit speed, joined to the track at both ends.
 let pit:string|null=null;const keys=[...bins.keys()].filter(b=>bins.get(b)![2]>=2).sort((a,b)=>a-b);
 if(keys.length>=4){let gi=0,gap=-1;keys.forEach((b,i)=>{const nx=keys[(i+1)%keys.length]+(i===keys.length-1?200:0);if(nx-b>gap){gap=nx-b;gi=i}});
  const run=[...keys.slice(gi+1),...keys.slice(0,gi+1)];
  if(run.length<120){const at=(p:number)=>{const f=((p%1)+1)%1*RES,i=Math.floor(f)%RES,j=(i+1)%RES,k=f-Math.floor(f);return [pts[i][0]+(pts[j][0]-pts[i][0])*k,pts[i][1]+(pts[j][1]-pts[i][1])*k]};
   const line=[at((run[0]-3)/200),...run.map(b=>{const c=bins.get(b)!;return [c[0]/c[2],c[1]/c[2]]}),at((run[run.length-1]+4)/200)];
   pit='M'+line.map(q=>q[0].toFixed(0)+' '+q[1].toFixed(0)).join('L')}}
 return {lapTimes:laps,pit,pts,tf,span,codes,t,P,D,X,Y,O,out,lead,laps:pl.frames.reduce((a,f)=>Math.max(a,f.lap||0),0)};
}

const frameAt=(t:Float64Array,T:number)=>{let lo=0,hi=t.length-1;if(T<=t[0])return [0,0];if(T>=t[hi])return [hi,0];
 while(hi-lo>1){const m=(lo+hi)>>1;if(t[m]<=T)lo=m;else hi=m}return [lo,(T-t[lo])/((t[lo+1]-t[lo])||1)]};

type MapCar={code:string;color:string;position:number;x:number;y:number;p:number|null;off:boolean;out:boolean};
function ReplayMap({g,cars,flag,focus,onFocus}:{g:Geo;cars:MapCar[];flag:string;focus:string|null;onFocus:(c:string)=>void}){
 const {pts,span}=g;const n=pts.length;
 const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);const minx=Math.min(...xs),miny=Math.min(...ys);const pad=span*.1,w=Math.max(...xs)-minx+pad*2,h=Math.max(...ys)-miny+pad*2;
 const full=useMemo(()=>'M'+pts.map(p=>p[0].toFixed(0)+' '+p[1].toFixed(0)).join('L')+'Z',[pts]);
 const at=(p:number)=>{const f=((p%1)+1)%1*n,i=Math.floor(f)%n,j=(i+1)%n,k=f-Math.floor(f);return [pts[i][0]+(pts[j][0]-pts[i][0])*k,pts[i][1]+(pts[j][1]-pts[i][1])*k]};
 const cx=xs.reduce((a,b)=>a+b,0)/n,cy=ys.reduce((a,b)=>a+b,0)/n;
 const normal=(p:number)=>{const [x1,y1]=at(p-.004),[x2,y2]=at(p+.004);const dx=x2-x1,dy=y2-y1,l=Math.hypot(dx,dy)||1;let ux=-dy/l,uy=dx/l;
  const [px,py]=at(p);if((px-cx)*ux+(py-cy)*uy<0){ux=-ux;uy=-uy}return [ux,uy]};
 const r=span/66,stroke=span/58;
 const placed:{p:number;lvl:number}[]=[],tags=new Map<string,number>();
 [...cars].filter(c=>c.p!=null&&!c.off).sort((a,b)=>a.position-b.position).forEach(c=>{let lvl=0;
  while(placed.some(q=>q.lvl===lvl&&Math.min(Math.abs(q.p-c.p!),1-Math.abs(q.p-c.p!))<.018))lvl++;placed.push({p:c.p!,lvl});tags.set(c.code,lvl)});
 const [lx,ly]=at(0),[nx,ny]=normal(0);
 const checker=[];for(let i=-3;i<3;i++)for(let j=0;j<2;j++)checker.push(<rect key={i+'_'+j} x={lx+nx*stroke*.5*i-stroke*.25} y={ly+ny*stroke*.5*i-stroke*.25} width={stroke*.5} height={stroke*.5}
  transform={`rotate(${Math.atan2(ny,nx)*180/Math.PI} ${lx} ${ly}) translate(${j*stroke*.5-stroke*.25} 0)`} className={(i+j)%2?'chk-w':'chk-b'}/>);
 return <svg className={'rhx-livemap flag-'+flag} viewBox={`${minx-pad} ${miny-pad} ${w} ${h}`} role="img" aria-label="Car positions on the circuit">
  <defs><filter id="rhx-rglow" filterUnits="userSpaceOnUse" x={minx-pad*2} y={miny-pad*2} width={w+pad*2} height={h+pad*2}><feGaussianBlur stdDeviation={stroke*.9}/></filter></defs>
  <path d={full} className="glow" strokeWidth={stroke*2.6} filter="url(#rhx-rglow)"/>
  {g.pit&&<g className="pitlane"><path d={g.pit} className="kerb" strokeWidth={stroke*.95}/><path d={g.pit} className="pit-road" strokeWidth={stroke*.55}/></g>}
  <path d={full} className="kerb" strokeWidth={stroke*1.55}/>
  <path d={full} className="asphalt" strokeWidth={stroke}/>
  {flag==='yellow'&&<g className="hazard"><path d={full} className="hz-glow" strokeWidth={stroke*2.2} filter="url(#rhx-rglow)"/><path d={full} className="hz-base" strokeWidth={stroke*1.05}/>
   <path d={full} className="hz-stripes" strokeWidth={stroke*1.05} strokeDasharray={`${stroke*.7} ${stroke*.7}`} style={{'--hz':`${stroke*1.4}px`} as React.CSSProperties}/></g>}
  <g className="line">{checker}</g>
  {[...cars].sort((a,b)=>b.position-a.position).map(c=>{const on=focus===c.code;const small=c.off||c.out;
   const [ux,uy]=c.p!=null&&!c.off?normal(c.p):[0,-1];const out=stroke*(2.2+(tags.get(c.code)||0)*1.9);const tx=ux*out,ty=uy*out;const showTag=!small||on;
   return <g key={c.code} className={'car'+(small?' in-pit':'')+(on?' is-focus':'')+((focus&&!on)||c.out?' is-dim':'')} style={{transform:`translate(${c.x}px,${c.y}px)`,'--team':teamColor(c.color)} as React.CSSProperties}
    onClick={()=>onFocus(c.code)}><title>{c.code}{c.off?' · pit lane':c.out?' · out':''}</title>
    {showTag&&<><line x1={0} y1={0} x2={tx*.72} y2={ty*.72} className="leader" strokeWidth={stroke*.1}/>
     <g transform={`translate(${tx} ${ty})`} className="tag"><rect x={-r*2.35} y={-r*.95} width={r*4.7} height={r*1.9} rx={r*.35}/>
      <rect x={-r*2.35} y={-r*.95} width={r*.55} height={r*1.9} className="tag-team"/>
      <text x={r*.3} y={r*.05} fontSize={r*1.35}>{c.code}</text></g></>}
    {on&&<circle r={r*(small?1.6:2.4)} className="pulse"/>}
    <circle r={r*(small?.6:c.position===1||on?1.44:1.15)} className="disc"/>
    {!small&&<text y={r*.05} fontSize={r*(c.position===1||on?1.56:1.25)} className="pos">{c.position}</text>}
   </g>})}
 </svg>;
}

function Player({pl,onReload}:{pl:Payload;onReload:()=>void}){
 const g=useMemo(()=>prepare(pl),[pl]);
 const t0=g.t[0],t1=g.t[g.t.length-1];
 const [T,setT]=useState(t0),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState(1),[focus,setFocus]=useState<string|null>(null);
 const live=useRef({playing,speed});live.current={playing,speed};
 useEffect(()=>{let raf=0,last=performance.now();const frame=(now:number)=>{const dt=Math.min(.1,(now-last)/1000);last=now;
  if(live.current.playing)setT(x=>{const nx=Math.min(t1,x+dt*live.current.speed);if(nx>=t1)setPlaying(false);return nx});raf=requestAnimationFrame(frame)};
  raf=requestAnimationFrame(frame);return()=>cancelAnimationFrame(raf)},[t1]);
 useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.code==='Space'&&!(e.target instanceof HTMLInputElement&&e.target.type!=='range')){e.preventDefault();setPlaying(p=>!p)}};
  window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[]);
 const [k,a]=frameAt(g.t,T);const k2=Math.min(k+1,g.t.length-1);const fr=pl.frames[k];
 const race=['R','S'].includes(pl.meta.session);
 const [flag,flagText]=status(fr.track_status);
 // Gap to the leader: how long ago the leader was where this car is now.
 const lead=g.lead[k]+(g.lead[k2]-g.lead[k])*a;
 const leaderTimeAt=(d:number)=>{let lo=0,hi=k2;if(g.lead[0]>=d)return g.t[0];while(hi-lo>1){const m=(lo+hi)>>1;if(g.lead[m]<d)lo=m;else hi=m}
  return g.t[lo]+(g.t[hi]-g.t[lo])*((d-g.lead[lo])/((g.lead[hi]-g.lead[lo])||1))};
 const rows=g.codes.map(code=>{const info=pl.drivers[code],car=fr.drivers[code];const off=!!(g.O[code][k]||g.O[code][k2]);const out=g.out[code]!=null&&T>=g.out[code];
  const d=g.D[code][k]+(g.D[code][k2]-g.D[code][k])*a;
  const p=off?null:(g.P[code][k]+wrap(g.P[code][k2]-g.P[code][k])*a+1)%1;
  const x=g.X[code][k]+(g.X[code][k2]-g.X[code][k])*a,y=g.Y[code][k]+(g.Y[code][k2]-g.Y[code][k])*a;
  let gap:number|string|null=null;if(race&&!out){const behind=lead-d;gap=behind>=1?`+${Math.floor(behind)} lap${behind>=2?'s':''}`:Math.max(0,T-leaderTimeAt(d))}
  let best:number|null=null,last:number|null=null;for(const l of g.lapTimes[code]){if(l.end>T)break;last=l.time;if(best==null||l.time<best)best=l.time}
  return {code,info,car,off,out,d,p,x,y,gap,best,last,position:car?.position||99}});
 // Races: order by distance covered right now (the recorded classification only updates at timing lines).
 if(race){rows.sort((a,b)=>Number(a.out)-Number(b.out)||(a.out?a.position-b.position:b.d-a.d));rows.forEach((r,i)=>r.position=i+1)}
 // Qualifying: classified by best lap so far (the recorded position field isn't a qualifying order).
 else{rows.sort((a,b)=>(a.best??1e9)-(b.best??1e9)||a.position-b.position);rows.forEach((r,i)=>r.position=i+1)}
 const lapStr=(v:number|null)=>v==null?'—':`${Math.floor(v/60)}:${(v%60).toFixed(1).padStart(4,'0')}`;
 const fastest=Math.min(...rows.map(r=>r.best??1e9));
 // Qualifying: gap to the best lap so far (estimated from recorded positions).
 if(!race){rows.forEach(r=>{r.gap=r.best!=null&&fastest<1e9?r.best-fastest:null})}
 const fmtGap=(v:number|string|null)=>v==null?'—':typeof v==='string'?v:(v<0?'':'+')+v.toFixed(1);
 const sel=rows.find(r=>r.code===focus);
 const statuses=pl.technical.track_statuses.filter(s=>s.start_time<=T).slice(-12).reverse();
 const mapCars:MapCar[]=rows.filter(r=>r.car).map(r=>{const [x,y]=r.p!=null?atPoint(g,r.p):[r.x,r.y];return {code:r.code,color:r.info.color,position:r.position,x,y,p:r.p,off:r.off,out:r.out}});
 const seek=(v:number)=>setT(Math.max(t0,Math.min(t1,v)));
 return <main className="rhx-page-body rhx-live-page">
  <section className={'rhx-livebar flag-'+flag}>
   <div className="rhx-livebar-event"><span className={'rhx-livedot '+(playing?'on':'')}/>Replay<b>{pl.meta.event}</b><span>{pl.meta.year} · {SESSION[pl.meta.session]||pl.meta.session}</span></div>
   {race&&<div className="rhx-livelap"><small>Lap</small><b>{Math.min(fr.lap||1,g.laps)}/{g.laps}</b></div>}
   <div className="rhx-liveclock"><small>{race?'Elapsed':'Session'}</small><b>{hms(T-t0)}</b></div>
   <div className="rhx-liveflag"><i/>{flagText}</div>
  </section>

  <div className="rhx-replaybar">
   <button type="button" onClick={()=>{if(T>=t1)setT(t0);setPlaying(!playing)}}>{playing?'Pause':'Play'}</button>
   <input type="range" min={t0} max={t1} step={.5} value={T} onChange={e=>seek(Number(e.target.value))} aria-label="Replay position"/>
   <span>{hms(T-t0)} / {hms(t1-t0)}</span>
   <div className="rhx-seg is-inline">{[1,2,5,10,30].map(v=><button type="button" key={v} className={speed===v?'on':''} onClick={()=>setSpeed(v)}>{v}×</button>)}</div>
  </div>

  <div className="rhx-livegrid">
   <div className="rhx-tower-wrap rhx-livetower">
    <table className="rhx-tower is-live"><thead><tr><th>Pos</th><th>Driver</th><th>Gap</th><th>Int</th><th>Best</th><th>Last</th><th>Lap</th><th>Speed</th><th>Tyre</th></tr></thead>
     <tbody>{rows.map((r,i)=>{const ahead=rows[i-1];const int=i===0||r.gap==null||ahead?.gap==null?null:typeof r.gap==='string'||typeof ahead.gap==='string'?(typeof r.gap==='string'&&r.gap!==ahead.gap?r.gap:null):r.gap-(ahead.gap as number);
      return <tr key={r.code} className={[r.out?'is-out':'',focus===r.code?'on':''].join(' ')} style={{'--team':teamColor(r.info.color)} as React.CSSProperties} onClick={()=>setFocus(focus===r.code?null:r.code)}>
      <td className="rhx-pos">{r.position<99?r.position:'—'}</td>
      <td className="rhx-who"><b>{r.code}</b>{r.out?<em className="pit">OUT</em>:r.off?<em className="pit">PIT</em>:r.car?.drs_active?<em className="out">DRS</em>:null}</td>
      <td>{i===0&&race?'Leader':!race&&r.gap===0?'Fastest':fmtGap(r.gap)}</td><td>{int==null?'':typeof int==='string'?int:'+'+Math.max(0,int).toFixed(1)}</td>
      <td className={r.best!=null&&r.best===fastest?'is-fastest':''}>{lapStr(r.best)}</td><td className={r.last!=null&&r.last===r.best?'is-pb':''}>{lapStr(r.last)}</td>
      <td>{r.car?.lap??'—'}</td><td>{r.car&&!r.out?r.car.speed:'—'}</td>
      <td>{r.car?.tyre&&TYRE[r.car.tyre]?<span className={'rhx-tyre t-'+TYRE[r.car.tyre]} title={`${r.car.tyre}, ${r.car.tyre_age} laps old`}>{TYRE[r.car.tyre]}</span>:'—'}</td>
     </tr>})}</tbody></table>
    <p className="rhx-legend-line"><span className="rhx-fastest-key"/>Fastest <span className="rhx-pb-key"/>Personal best · Gaps and lap times are measured from recorded positions, to about a tenth. Space plays and pauses.</p>
   </div>
   <aside className="rhx-liveside">
    <div className="rhx-livemap-wrap"><ReplayMap g={g} cars={mapCars} flag={flag} focus={focus} onFocus={c=>setFocus(focus===c?null:c)}/>
     {rows.some(r=>r.off&&!r.out)&&<div className="rhx-pitlane"><span>Pit lane</span>{rows.filter(r=>r.off&&!r.out).map(r=>
      <b key={r.code} style={{'--team':teamColor(r.info.color)} as React.CSSProperties}>{r.code}</b>)}</div>}
     <small className="rhx-livemap-note">Recorded positions, {pl.meta.sample_rate_hz} samples a second, smoothed along the track.</small></div>
    {sel&&<div className="rhx-livefocus" style={{'--team':teamColor(sel.info.color)} as React.CSSProperties}><b>{sel.code}</b><span>{sel.info.name}, {sel.info.team}</span>
     <dl><div><dt>Position</dt><dd>{sel.position<99?sel.position:'—'}</dd></div><div><dt>Lap</dt><dd>{sel.car?.lap??'—'}</dd></div>
      <div><dt>Speed</dt><dd>{sel.car?`${sel.car.speed} km/h`:'—'}</dd></div><div><dt>Gear</dt><dd>{sel.car?.gear||'N'}</dd></div>
      <div><dt>Throttle</dt><dd>{sel.car?`${Math.min(100,Math.max(0,sel.car.throttle))}%`:'—'}</dd></div><div><dt>Brake</dt><dd>{sel.car?.brake?'On':'Off'}</dd></div>
      <div><dt>DRS</dt><dd className={sel.car?.drs_active?'is-pb':''}>{sel.car?.drs_active?'Open':'Closed'}</dd></div><div><dt>Tyre</dt><dd>{sel.car?.tyre||'—'}{sel.car?` · ${sel.car.tyre_age}L`:''}</dd></div></dl></div>}
    <div className="rhx-livefeed"><h3>Track status</h3><ol>{statuses.map((s,i)=>{const [,text,col]=status(s.label);return <li key={i}>
     <time>{s.start_time<t0?'Pre':hms(s.start_time-t0)}</time><i style={{background:col}}/><span>{text}</span></li>})}</ol></div>
   </aside>
  </div>
  <div className="rhx-row"><button type="button" className="rhx-link" onClick={onReload}>Replay settings</button>
   <span className="rhx-count">{pl.technical.frame_count.toLocaleString()} frames, {pl.technical.driver_count} drivers</span></div>
 </main>;
}
const atPoint=(g:Geo,p:number)=>{const n=g.pts.length,f=((p%1)+1)%1*n,i=Math.floor(f)%n,j=(i+1)%n,k=f-Math.floor(f);return [g.pts[i][0]+(g.pts[j][0]-g.pts[i][0])*k,g.pts[i][1]+(g.pts[j][1]-g.pts[i][1])*k]};

export default function Replay(){
 const {selection:s}=useSession(),task=useTask();const [rate,setRate]=useState(3),[refresh,setRefresh]=useState(false),[error,setError]=useState('');
 const [data,setData]=useState<Payload|null>(null),[opening,setOpening]=useState(false),[settings,setSettings]=useState(false);
 const cache=useResource<any[]>('/api/replay-cache');
 useEffect(()=>task.reset(),[s.year,s.event,s.session]);
 const supported=['R','Q','S','SQ'].includes(s.session);
 const r=task.result;
 useEffect(()=>{setData(null);if(!r)return;const url=r.data||String(r.viewer).replace(/\/viewer$/,'/data');let alive=true;setOpening(true);setError('');setSettings(false);
  request<Payload>(url).then(d=>{if(alive)setData(d)}).catch(e=>{if(alive)setError((e as Error).message)}).finally(()=>{if(alive)setOpening(false)});return()=>{alive=false}},[r]);
 async function clearCache(){setError('');try{await request('/api/replay-cache',{method:'DELETE'});cache.refresh()}catch(e){setError((e as Error).message)}}
 const load=()=>task.start('replay',s,{sample_rate:rate,refresh});
 if(data&&!settings)return <Player pl={data} onReload={()=>setSettings(true)}/>;
 return <main className="rhx-page-body">
  <PageHead title="Rewind. Relive." lede="Every car on the circuit from recorded positions, on the live timing screen. Play, pause, scrub, change speed and follow one driver.">
   <Action disabled={task.busy||!s.event||!supported} sub={supported?'Recorded positions':'Race, qualifying or sprint only'} onClick={load}>{r?'Reload replay':'Load replay'}</Action>
  </PageHead>
  {!supported&&<p className="rhx-error">Replays work for the race, qualifying, sprint and sprint qualifying. Pick one of those on the weekend page.</p>}
  <JobBar task={task}/>
  {data&&settings?<div className="rhx-row"><button type="button" className="rhx-link" onClick={()=>setSettings(false)}>Back to the replay</button></div>
   :opening?<Blank title="Opening the replay…" mark="◌">Placing every car on the circuit.</Blank>
   :!task.busy&&<Blank title="The race, at your pace." mark="↺">Load the replay to watch the whole field move around the circuit, with the timing tower beside it.</Blank>}
  {error&&<p className="rhx-error" role="alert">{error}{/404|restart/i.test(error)?' Load the replay again.':''}</p>}
  <Group title="Sampling and cache">
   <Choice label="Samples per second" value={rate} onChange={setRate} options={[1,3,5,10].map(v=>({value:v,label:String(v),hint:v===3?'Default':v===10?'Smoothest':undefined}))}/>
   <label className="rhx-check"><input type="checkbox" checked={refresh} onChange={e=>setRefresh(e.target.checked)}/><span>Rebuild this replay from scratch</span></label>
   <Note>Long sessions are capped at 6,000 frames by the replay engine. The loaded replay reports the rate it actually used.</Note>
   <div className="rhx-row"><span className="rhx-count">{cache.value?.length||0} saved replays</span><button type="button" className="rhx-link" onClick={clearCache}>Clear saved replays</button></div>
  </Group>
 </main>;
}
