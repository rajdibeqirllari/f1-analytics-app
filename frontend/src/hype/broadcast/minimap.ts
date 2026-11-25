/** Transparent circuit map for the fullscreen broadcast: thin white outline, a dot per car in its team colour and its
 * three-letter code. Drawn every frame from the same poses as the 3D cars (same instant, Live delay included).
 * Labels keep their side between frames (hysteresis) and move to short leader lines when cars bunch up; the selected
 * driver is placed first. Orientation = the page map's rotation (degrees) so it matches the 2D map. */
import type {Pose,TrackCurve} from './data';

type Slot={dx:number;dy:number;lead:boolean};
const SLOTS:Slot[]=[{dx:9,dy:-7,lead:false},{dx:9,dy:9,lead:false},{dx:-9,dy:-7,lead:false},{dx:-9,dy:9,lead:false},
 {dx:0,dy:-16,lead:false},{dx:0,dy:18,lead:false},{dx:24,dy:-20,lead:true},{dx:24,dy:22,lead:true},{dx:-24,dy:-20,lead:true},{dx:-24,dy:22,lead:true},
 {dx:40,dy:0,lead:true},{dx:-40,dy:0,lead:true}];

export class MiniMap{
 canvas:HTMLCanvasElement;ctx:CanvasRenderingContext2D;track:TrackCurve|null=null;rot=0;pts:Float32Array|null=null;
 bounds={minx:0,maxx:1,miny:0,maxy:1};slot=new Map<string,number>();w=0;h=0;dpr=1;
 constructor(c:HTMLCanvasElement){this.canvas=c;this.ctx=c.getContext('2d')!}
 setTrack(tr:TrackCurve|null,rotDeg:number){this.track=tr;this.rot=rotDeg;this.slot.clear();if(!tr){this.pts=null;return}
  const r=-rotDeg*Math.PI/180,c=Math.cos(r),s=Math.sin(r);const p=new Float32Array(tr.n*2);let minx=Infinity,maxx=-Infinity,miny=Infinity,maxy=-Infinity;
  for(let i=0;i<tr.n;i++){const x=tr.x[i]*c-tr.y[i]*s,y=-(tr.x[i]*s+tr.y[i]*c);p[i*2]=x;p[i*2+1]=y;minx=Math.min(minx,x);maxx=Math.max(maxx,x);miny=Math.min(miny,y);maxy=Math.max(maxy,y)}
  this.pts=p;this.bounds={minx,maxx,miny,maxy}}
 private tf(x:number,y:number){const r=-this.rot*Math.PI/180,c=Math.cos(r),s=Math.sin(r);return [x*c-y*s,-(x*s+y*c)]}
 draw(all:Map<string,Pose>,meta:Record<string,{code:string;color:string}>,sel:string|null){
  const cv=this.canvas,ctx=this.ctx;if(!this.pts||!this.track)return;
  const dpr=Math.min(2,window.devicePixelRatio||1),W=cv.clientWidth,H=cv.clientHeight;if(!W||!H)return;
  if(cv.width!==Math.round(W*dpr)||cv.height!==Math.round(H*dpr)){cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr)}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
  const b=this.bounds,pad=26,sc=Math.min((W-pad*2)/(b.maxx-b.minx),(H-pad*2)/(b.maxy-b.miny));
  const ox=(W-(b.maxx-b.minx)*sc)/2-b.minx*sc,oy=(H-(b.maxy-b.miny)*sc)/2-b.miny*sc;
  const P=(x:number,y:number)=>{const [u,v]=this.tf(x,y);return [ox+u*sc,oy+v*sc]};
  // outline: a dark halo under a thin white line keeps it visible over bright floodlit asphalt
  ctx.beginPath();const p=this.pts;for(let i=0;i<this.track.n;i++){const x=ox+p[i*2]*sc,y=oy+p[i*2+1]*sc;if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y)}ctx.closePath();
  ctx.lineJoin='round';ctx.strokeStyle='rgba(0,0,0,.55)';ctx.lineWidth=4.5;ctx.stroke();ctx.strokeStyle='rgba(255,255,255,.92)';ctx.lineWidth=1.8;ctx.stroke();
  // start/finish: a short tick across the line at lap distance 0
  const s0=this.track.at(0),[sx,sy]=P(s0.x,s0.y),[tx,ty]=P(s0.x+Math.cos(s0.h)*10,s0.y+Math.sin(s0.h)*10);const nx=-(ty-sy),ny=tx-sx,nl=Math.hypot(nx,ny)||1;
  ctx.strokeStyle='#fff';ctx.lineWidth=2.4;ctx.beginPath();ctx.moveTo(sx-nx/nl*6,sy-ny/nl*6);ctx.lineTo(sx+nx/nl*6,sy+ny/nl*6);ctx.stroke();
  // cars, selected last so it sits on top; labels placed selected first, then by lap order
  const cars=[...all.values()].filter(q=>!q.offTrack&&meta[q.num]).map(q=>{const [x,y]=P(q.x,q.y);return {q,x,y}});
  const order=[...cars].sort((a,c)=>(a.q.num===sel?-1:c.q.num===sel?1:0)||c.q.lapFrac-a.q.lapFrac);
  ctx.font='700 11px "RHX Shoulders", "Barlow", system-ui, sans-serif';ctx.textBaseline='middle';
  const placed:{x0:number;y0:number;x1:number;y1:number}[]=[];const dots=cars.map(c=>({x0:c.x-5,y0:c.y-5,x1:c.x+5,y1:c.y+5}));
  const hit=(r:{x0:number;y0:number;x1:number;y1:number})=>{let n=0;for(const o of placed)if(r.x0<o.x1&&r.x1>o.x0&&r.y0<o.y1&&r.y1>o.y0)n+=3;for(const o of dots)if(r.x0<o.x1&&r.x1>o.x0&&r.y0<o.y1&&r.y1>o.y0)n++;
   if(r.x0<0||r.y0<0||r.x1>W||r.y1>H)n+=2;return n};
  const labels:{c:typeof cars[0];slot:Slot;box:{x0:number;y0:number;x1:number;y1:number};tw:number}[]=[];
  for(const c of order){const code=meta[c.q.num].code;const tw=ctx.measureText(code).width+(c.q.num===sel?6:0);
   const box=(sl:Slot)=>{const x=sl.dx>=0?c.x+sl.dx:c.x+sl.dx-tw,y=c.y+sl.dy;return {x0:x-2,y0:y-7,x1:x+tw+2,y1:y+7}};
   const prev=this.slot.get(c.q.num);let best=prev??0,bestScore=prev!=null?hit(box(SLOTS[prev]))-0.5:Infinity;   // keep the side unless it collides
   if(bestScore>0)for(let k=0;k<SLOTS.length;k++){const sc2=hit(box(SLOTS[k]))+k*0.05;if(sc2<bestScore){bestScore=sc2;best=k}if(sc2===0&&k>=0)break}
   this.slot.set(c.q.num,best);const bx=box(SLOTS[best]);placed.push(bx);labels.push({c,slot:SLOTS[best],box:bx,tw})}
  for(const l of labels){const {c,slot}=l;const m=meta[c.q.num];
   if(slot.lead){ctx.strokeStyle='rgba(255,255,255,.7)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(c.x,c.y);ctx.lineTo(slot.dx>=0?l.box.x0:l.box.x1,(l.box.y0+l.box.y1)/2);ctx.stroke()}}
  for(const c of cars){const m=meta[c.q.num];const on=c.q.num===sel;
   ctx.beginPath();ctx.arc(c.x,c.y,on?5.5:4,0,Math.PI*2);ctx.fillStyle=c.q.flag==='stale'?'rgba(0,0,0,.4)':m.color;ctx.fill();
   ctx.lineWidth=on?2:1.2;ctx.strokeStyle=on?'#fff':'rgba(0,0,0,.75)';if(c.q.flag==='stale'){ctx.strokeStyle=m.color;ctx.lineWidth=1.6}ctx.stroke()}
  for(const l of labels){const m=meta[l.c.q.num];const on=l.c.q.num===sel;const x=l.box.x0+2,y=(l.box.y0+l.box.y1)/2;
   ctx.lineWidth=3;ctx.strokeStyle='rgba(0,0,0,.85)';ctx.strokeText(m.code,x,y);ctx.fillStyle=on?'#ffe066':'#fff';ctx.fillText(m.code,x,y)}
 }
}
