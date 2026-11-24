/** 3D Broadcast data layer: the shared clock, the short sample buffer and car poses as pure functions of time.
 * Nothing here depends on React: the render loop reads it every frame. A car's place at instant D depends only on
 * D and the samples, so every camera sees the same cars in the same place at the same timestamp. */

/** `exact`: the clock is the page's own playback time, sent every frame (Replay page), not a once-a-second poll. */
export type FeedInfo={mode:'follow'|'replay';file:string;speed:number;paused:boolean;clock:number|null;start:number|null;end:number|null;ended?:boolean;growing?:boolean;exact?:boolean};
export type SceneTrack={x:number[];y:number[];z:number[];length:number;source:string;pit:number[][]|null;pit_frac:{entry:number;exit:number}|null;speed:number[];line?:number[]};
export type DriverMeta={code:string;name:string;team:string;color:string};
export type SceneInfo={ok:boolean;error?:string;loading?:boolean;file:string;mode:string;source:'recorded'|'estimated';label:string;detail:string;key:string;
 session:{meeting:string;name:string;year:number|null;type:string;start:string};total_laps:number|null;track:SceneTrack;drivers:Record<string,DriverMeta>;
 recorded:{status:string;reason?:string;progress?:number;driver?:string;provider?:string;rate?:number}};
type RawSamples={key:string;t0:number;t1:number;frontier:number;source:'recorded'|'estimated';step:number|null;
 cars:Record<string,{t:number[];x:number[];y:number[];z:number[]}|{s:(number|null)[];f:number[]}>;timing:Record<string,(number|string|null)[][]>};

/** In follow (live) mode the picture runs this far behind the newest data, so cars move between real crossings. */
export const LIVE_DELAY=5;

/** Display clock in recording seconds, driven by the engine's feed clock (polled once a second) and run locally
 * in between. Small disagreements are blended out; a jump (seek, new file, speed change) resets the buffer. */
export class Clock{
 key='';base=0;at=0;speed=1;paused=true;offset=0;offsetAt=0;valid=false;
 update(f:FeedInfo,now:number):'reset'|'seek'|'ok'{
  if(f.clock==null){this.valid=false;return 'ok'}
  const key=f.file+'|'+f.mode,target=f.clock-(f.mode==='follow'?LIVE_DELAY:0);
  const speed=f.mode==='replay'?f.speed:1,paused=f.mode==='replay'&&f.paused;
  if(key!==this.key||!this.valid){Object.assign(this,{key,base:target,at:now,speed,paused,offset:0,valid:true});return 'reset'}
  const predicted=this.now(now),err=target-predicted;
  if(f.exact){const jump=Math.abs(err)>Math.max(2.5,speed*2.2);Object.assign(this,{base:target,at:now,speed,paused,offset:0});return jump?'seek':'ok'}
  if(paused!==this.paused||speed!==this.speed){const jump=Math.abs(err)>Math.max(2,speed*1.5);
   Object.assign(this,{base:target,at:now,speed,paused,offset:0});return jump?'seek':'ok'}
  if(Math.abs(err)>Math.max(2.5,speed*2.2)){Object.assign(this,{base:target,at:now,offset:0});return 'seek'}
  if(!paused){this.offset=predicted-target;this.offsetAt=now}
  this.base=target;this.at=now;return 'ok'}
 now(t:number){if(!this.valid)return NaN;const raw=this.paused?this.base:this.base+(t-this.at)/1000*this.speed;
  const k=this.paused?0:Math.max(0,1-(t-this.offsetAt)/700);return raw+this.offset*k}
}

/** The circuit as a smooth closed curve at ~2 m spacing (track plane: x east, y north, z elevation). */
export class TrackCurve{
 n:number;x:Float64Array;y:Float64Array;z:Float64Array;s:Float64Array;tx:Float64Array;ty:Float64Array;speed:Float64Array;length:number;serverLength:number;
 /** Typical racing line (estimated cars drive on it): points and unit tangents. Equals the centreline when absent. */
 rx:Float64Array;ry:Float64Array;rtx:Float64Array;rty:Float64Array;
 constructor(t:SceneTrack){
  const m=t.x.length;const P=(i:number)=>{i=((i%m)+m)%m;return [t.x[i],t.y[i],t.z[i]]};
  // Centripetal-ish Catmull-Rom through the server points, then resampled evenly.
  const dense:number[][]=[];const sp:number[]=[];const ln:number[]=[];
  for(let i=0;i<m;i++){const p0=P(i-1),p1=P(i),p2=P(i+1),p3=P(i+2);
   for(let k=0;k<4;k++){const u=k/4,u2=u*u,u3=u2*u;
    dense.push([0,1,2].map(j=>.5*((2*p1[j])+(-p0[j]+p2[j])*u+(2*p0[j]-5*p1[j]+4*p2[j]-p3[j])*u2+(-p0[j]+3*p1[j]-3*p2[j]+p3[j])*u3)));
    sp.push(t.speed[i]+(t.speed[(i+1)%m]-t.speed[i])*u);ln.push(t.line?t.line[i]+(t.line[(i+1)%m]-t.line[i])*u:0)}}
  const cum=[0];for(let i=1;i<=dense.length;i++){const a=dense[i-1],b=dense[i%dense.length];cum.push(cum[i-1]+Math.hypot(b[0]-a[0],b[1]-a[1]))}
  const L=cum[cum.length-1];const n=Math.max(64,Math.round(L/2));
  this.n=n;this.length=L;this.serverLength=t.length;
  this.x=new Float64Array(n);this.y=new Float64Array(n);this.z=new Float64Array(n);this.s=new Float64Array(n);this.speed=new Float64Array(n);const off=new Float64Array(n);
  let j=0;for(let i=0;i<n;i++){const d=i*L/n;while(cum[j+1]<d)j++;const k=(d-cum[j])/Math.max(1e-9,cum[j+1]-cum[j]),a=dense[j],b=dense[(j+1)%dense.length];
   this.x[i]=a[0]+(b[0]-a[0])*k;this.y[i]=a[1]+(b[1]-a[1])*k;this.z[i]=a[2]+(b[2]-a[2])*k;this.s[i]=d;this.speed[i]=sp[j]+(sp[(j+1)%sp.length]-sp[j])*k;off[i]=ln[j]+(ln[(j+1)%ln.length]-ln[j])*k}
  this.tx=new Float64Array(n);this.ty=new Float64Array(n);
  for(let i=0;i<n;i++){const a=(i-3+n)%n,b=(i+3)%n;const dx=this.x[b]-this.x[a],dy=this.y[b]-this.y[a],l=Math.hypot(dx,dy)||1;this.tx[i]=dx/l;this.ty[i]=dy/l}
  this.rx=new Float64Array(n);this.ry=new Float64Array(n);this.rtx=new Float64Array(n);this.rty=new Float64Array(n);
  for(let i=0;i<n;i++){this.rx[i]=this.x[i]-this.ty[i]*off[i];this.ry[i]=this.y[i]+this.tx[i]*off[i]}
  for(let i=0;i<n;i++){const a=(i-3+n)%n,b=(i+3)%n;const dx=this.rx[b]-this.rx[a],dy=this.ry[b]-this.ry[a],l=Math.hypot(dx,dy)||1;this.rtx[i]=dx/l;this.rty[i]=dy/l}
 }
 /** Point and heading on the racing line at centreline distance d. */
 atLine(d:number){const n=this.n,f=(((d/this.length)%1)+1)%1*n,i=Math.floor(f)%n,j=(i+1)%n,k=f-Math.floor(f);
  const tx=this.rtx[i]+(this.rtx[j]-this.rtx[i])*k,ty=this.rty[i]+(this.rty[j]-this.rty[i])*k;
  return {x:this.rx[i]+(this.rx[j]-this.rx[i])*k,y:this.ry[i]+(this.ry[j]-this.ry[i])*k,z:this.z[i]+(this.z[j]-this.z[i])*k,h:Math.atan2(ty,tx)}}
 /** Point, heading and elevation at lap distance d (metres on this curve, wraps). */
 at(d:number){const n=this.n,f=(((d/this.length)%1)+1)%1*n,i=Math.floor(f)%n,j=(i+1)%n,k=f-Math.floor(f);
  const tx=this.tx[i]+(this.tx[j]-this.tx[i])*k,ty=this.ty[i]+(this.ty[j]-this.ty[i])*k;
  return {x:this.x[i]+(this.x[j]-this.x[i])*k,y:this.y[i]+(this.y[j]-this.y[i])*k,z:this.z[i]+(this.z[j]-this.z[i])*k,h:Math.atan2(ty,tx)}}
 /** Nearest centreline point to (x, y): searched around a hint first, the whole lap when that is far off. */
 nearest(x:number,y:number,hint=-1){const n=this.n;let best=-1,bd=Infinity;
  const scan=(a:number,b:number)=>{for(let q=a;q<=b;q++){const i=((q%n)+n)%n,d=(this.x[i]-x)**2+(this.y[i]-y)**2;if(d<bd){bd=d;best=i}}};
  if(hint>=0)scan(hint-90,hint+90);if(hint<0||bd>30*30)scan(0,n-1);
  return {i:best,dist:Math.sqrt(bd),d:this.s[best]}}
}

export type Pose={num:string;x:number;y:number;z:number;h:number;d:number;lapFrac:number;offTrack:boolean;flag:'ok'|'extrapolated'|'stale';speed:number};
export type TimingRow={pos:number|null;laps:number;interval:string|null;gap:string|null;inPit:boolean;retired:boolean;stopped:boolean;out:boolean};

type RecCar={t:Float64Array;x:Float32Array;y:Float32Array;z:Float32Array};
type EstCar={s:Float64Array;f:Int8Array};

/** The samples around the displayed instant, for every car, from one server answer. */
export class Buffer{
 key:string;t0:number;t1:number;frontier:number;source:'recorded'|'estimated';step:number;
 rec=new Map<string,RecCar>();est=new Map<string,EstCar>();timing=new Map<string,{t:number;row:TimingRow}[]>();
 constructor(r:RawSamples){
  this.key=r.key;this.t0=r.t0;this.t1=r.t1;this.frontier=r.frontier;this.source=r.source;this.step=r.step||0.25;
  for(const [num,c] of Object.entries(r.cars)){
   if('t' in c)this.rec.set(num,{t:Float64Array.from(c.t,v=>v+r.t0),x:Float32Array.from(c.x),y:Float32Array.from(c.y),z:Float32Array.from(c.z)});
   else this.est.set(num,{s:Float64Array.from(c.s,v=>v==null?NaN:v),f:Int8Array.from(c.f)})}
  for(const [num,rows] of Object.entries(r.timing))this.timing.set(num,rows.map(q=>({t:(q[0] as number)+r.t0,row:{pos:q[1] as number|null,laps:(q[2] as number)||0,
   interval:(q[3] as string)||null,gap:(q[4] as string)||null,inPit:!!q[5],retired:!!q[6],stopped:!!q[7],out:!!q[8]}})));
 }
 covers(D:number){return D>=this.t0&&D<=this.t1}
 timingAt(num:string,D:number):TimingRow|null{const rows=this.timing.get(num);if(!rows||!rows.length)return null;let lo=0,hi=rows.length-1,ans=-1;
  while(lo<=hi){const m=(lo+hi)>>1;if(rows[m].t<=D){ans=m;lo=m+1}else hi=m-1}return ans<0?rows[0].row:rows[ans].row}
 /** Cumulative distance (estimated mode) at D, linear between the server's evenly spaced samples. */
 estAt(num:string,D:number):{s:number;f:number}|null{const c=this.est.get(num);if(!c)return null;const q=(D-this.t0)/this.step;
  const i=Math.floor(q);if(i<0||i>=c.s.length)return null;const j=Math.min(c.s.length-1,i+1),k=q-i;const a=c.s[i],b=c.s[j];
  if(Number.isNaN(a)||Number.isNaN(b))return null;return {s:a+(b-a)*k,f:Math.max(c.f[i],c.f[j])}}
 /** Recorded coordinates at D: cubic Hermite between timestamped samples (no smoothing of the data itself). */
 recAt(num:string,D:number):{x:number;y:number;z:number;vx:number;vy:number;flag:'ok'|'extrapolated'|'stale'}|null{
  const c=this.rec.get(num);if(!c||c.t.length<2)return null;const t=c.t,n=t.length;
  if(D<t[0]-0.5)return null;
  let lo=0,hi=n-1;while(lo<hi-1){const m=(lo+hi)>>1;if(t[m]<=D)lo=m;else hi=m}
  const i=Math.max(0,Math.min(n-2,lo)),j=i+1;
  const P=(k:number)=>[c.x[k],c.y[k],c.z[k]];
  const vel=(k:number)=>{const a=Math.max(0,k-1),b=Math.min(n-1,k+1);const dt=Math.max(1e-3,t[b]-t[a]);return [(c.x[b]-c.x[a])/dt,(c.y[b]-c.y[a])/dt,(c.z[b]-c.z[a])/dt]};
  if(D>t[n-1]){const p=P(n-1),v=vel(n-1),dt=Math.min(1,D-t[n-1]);
   return {x:p[0]+v[0]*dt,y:p[1]+v[1]*dt,z:p[2],vx:v[0],vy:v[1],flag:D-t[n-1]<=1?'extrapolated':'stale'}}
  const h=t[j]-t[i];if(h>2.5){const p=P(i);return {x:p[0],y:p[1],z:p[2],vx:0,vy:0,flag:'stale'}}
  const u=Math.max(0,Math.min(1,(D-t[i])/h)),u2=u*u,u3=u2*u;
  const h00=2*u3-3*u2+1,h10=u3-2*u2+u,h01=-2*u3+3*u2,h11=u3-u2;
  const d00=6*u2-6*u,d10=3*u2-4*u+1,d01=-6*u2+6*u,d11=3*u2-2*u;
  const p0=P(i),p1=P(j),m0=vel(i),m1=vel(j);const out=[0,0,0],dv=[0,0];
  for(let k=0;k<3;k++){out[k]=h00*p0[k]+h10*h*m0[k]+h01*p1[k]+h11*h*m1[k];if(k<2)dv[k]=(d00*p0[k]+d10*h*m0[k]+d01*p1[k]+d11*h*m1[k])/h}
  return {x:out[0],y:out[1],z:out[2],vx:dv[0],vy:dv[1],flag:'ok'}}
}

export async function fetchSamples(base:string,t0:number,t1:number,source:string,step:number,signal?:AbortSignal):Promise<Buffer>{
 const r=await fetch(`${base}?t0=${t0.toFixed(3)}&t1=${t1.toFixed(3)}&source=${source}&step=${step}`,{signal});
 if(!r.ok){let d='';try{d=(await r.json()).detail}catch{d=r.statusText}throw new Error(d||'No samples')}
 return new Buffer(await r.json());
}

/** Every car's pose at instant D. Pure: depends only on D, the buffer and the track (hints only speed up searches). */
export function poses(buf:Buffer,track:TrackCurve,D:number,hints:Map<string,number>,lastHeading:Map<string,number>,
 correction:Map<string,{v:number;at:number}>,wallNow:number):Map<string,Pose>{
 const out=new Map<string,Pose>();
 if(buf.source==='recorded'){
  for(const num of buf.rec.keys()){const r=buf.recAt(num,D);if(!r)continue;
   const near=track.nearest(r.x,r.y,hints.get(num)??-1);hints.set(num,near.i);
   const sp=Math.hypot(r.vx,r.vy);let h=lastHeading.get(num)??track.at(near.d).h;if(sp>3)h=Math.atan2(r.vy,r.vx);lastHeading.set(num,h);
   // Height from the measured circuit under the car (the per-sample z is noisier than the track's).
   out.set(num,{num,x:r.x,y:r.y,z:near.dist<9?track.z[near.i]:r.z,h,d:near.d,lapFrac:near.d/track.length,offTrack:near.dist>9,flag:r.flag,speed:sp})}
 }else{
  for(const num of buf.est.keys()){const e=buf.estAt(num,D);if(!e)continue;
   let s=e.s;const c=correction.get(num);if(c){const k=Math.max(0,1-(wallNow-c.at)/700);if(k>0)s+=c.v*k;else correction.delete(num)}
   const frac=(((s/track.serverLength)%1)+1)%1,d=frac*track.length;const p=track.atLine(d);
   const e2=buf.estAt(num,D+0.5);const sp=e2?Math.max(0,(e2.s-e.s)/0.5):0;
   out.set(num,{num,x:p.x,y:p.y,z:p.z,h:p.h,d,lapFrac:frac,offTrack:false,flag:e.f===0?'ok':e.f===1?'extrapolated':'stale',speed:sp})}
 }
 return out;
}

/** Nearest car physically ahead / behind on the circuit (by where the cars are, not by classification). */
export function neighbours(all:Map<string,Pose>,num:string,L:number){
 const me=all.get(num);if(!me)return {ahead:null as null|{num:string;m:number},behind:null as null|{num:string;m:number}};
 let ahead:null|{num:string;m:number}=null,behind:null|{num:string;m:number}=null;
 for(const p of all.values()){if(p.num===num||p.offTrack)continue;const fwd=((p.lapFrac-me.lapFrac)%1+1)%1*L;const back=L-fwd;
  if(fwd<L/2&&(!ahead||fwd<ahead.m))ahead={num:p.num,m:fwd};if(back<=L/2&&(!behind||back<behind.m))behind={num:p.num,m:back}}
 return {ahead,behind};
}
