import {useEffect,useRef} from 'react';
import {MAP_COLS,MAP_ROWS,MAP_RUNS} from './mapdata';
import type {Round} from './weekend';

const DOTS:[number,number][]=(()=>{const out:[number,number][]=[];MAP_RUNS.split('|').forEach((row,r)=>{if(!row)return;
 for(const run of row.split(',')){const [s,l]=run.split('.').map(v=>parseInt(v,36));for(let c=s;c<s+l;c++)out.push([c,r])}});return out})();

type Props={rounds:Round[];selected:string;hovered:string|null;onSelect:(key:string)=>void;onHover:(key:string|null)=>void;season:number};
const ease=(t:number)=>1-Math.pow(1-Math.min(1,Math.max(0,t)),3);

export default function LedMap({rounds,selected,hovered,onSelect,onHover,season}:Props){
 const canvas=useRef<HTMLCanvasElement>(null);
 const live=useRef({rounds,selected,hovered,season});
 live.current={rounds,selected,hovered,season};
 const pins=useRef<{key:string;x:number;y:number}[]>([]);
 const timeline=useRef({routeStart:0,routeSeason:-1,pickTime:0,pickKey:''});

 useEffect(()=>{
  const el=canvas.current!;const ctx=el.getContext('2d')!;
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cam={x:MAP_COLS/2,y:MAP_ROWS/2,z:1};
  let raf=0,visible=true,w=0,h=0,dpr=1;
  const css=getComputedStyle(el);
  const color=(name:string,fallback:string)=>css.getPropertyValue(name).trim()||fallback;
  const C={off:color('--rhx-led-off','#243443'),lit:color('--rhx-led-on','#62d7da'),red:color('--rhx-signal','#ff463b'),ink:color('--rhx-ink','#eef2f5'),plate:color('--rhx-raised','#18212c')};
  const resize=()=>{const r=el.getBoundingClientRect();dpr=Math.min(2,devicePixelRatio||1);w=r.width;h=r.height;el.width=Math.round(w*dpr);el.height=Math.round(h*dpr)};
  const ro=new ResizeObserver(resize);ro.observe(el);resize();
  const io=new IntersectionObserver(([e])=>{visible=e.isIntersecting});io.observe(el);

  const frame=(now:number)=>{
   raf=requestAnimationFrame(frame);
   if(!visible||document.hidden||!w)return;
   const {rounds,selected,hovered,season}=live.current,t=timeline.current;
   if(t.routeSeason!==season||!t.routeStart){t.routeSeason=season;t.routeStart=now}
   if(t.pickKey!==selected){t.pickKey=selected;t.pickTime=now}
   const pick=rounds.find(r=>r.key===selected);
   const base=Math.min(w/MAP_COLS,h/MAP_ROWS);
   const narrow=w<760;
   // Wide screens keep the whole season on the board; phones lean in toward the chosen venue.
   const target=narrow&&pick?.point?{x:pick.point[0]*.7+MAP_COLS/2*.3,y:pick.point[1]*.7+MAP_ROWS/2*.3,z:1.85}:{x:MAP_COLS/2,y:MAP_ROWS/2,z:1};
   const k=reduce?1:.075;cam.x+=(target.x-cam.x)*k;cam.y+=(target.y-cam.y)*k;cam.z+=(target.z-cam.z)*k;
   const s=base*cam.z;
   const X=(c:number)=>w/2+(c+.5-cam.x)*s,Y=(r:number)=>h/2+(r+.5-cam.y)*s;
   ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);

   // LED field
   const rad=Math.max(.6,s*.3);
   ctx.fillStyle=C.off;ctx.beginPath();
   for(const [c,r] of DOTS){const x=X(c),y=Y(r);if(x<-4||y<-4||x>w+4||y>h+4)continue;ctx.moveTo(x+rad,y);ctx.arc(x,y,rad,0,6.2832)}
   ctx.fill();

   // Light the board around the chosen venue, with one shock-wave when the pick changes.
   if(pick?.point){
    const [pc,pr]=pick.point,since=(now-t.pickTime)/1000,wave=reduce?99:since*34,reach=13;
    for(const [c,r] of DOTS){const d=Math.hypot(c-pc,r-pr);
     let a=d<reach?Math.pow(1-d/reach,1.4):0;
     if(wave<60){const band=Math.abs(d-wave);if(band<2.2)a=Math.max(a,(1-band/2.2)*(1-wave/60)*.9)}
     if(a<.04)continue;const x=X(c),y=Y(r);if(x<-4||y<-4||x>w+4||y>h+4)continue;
     ctx.globalAlpha=a;ctx.fillStyle=C.lit;ctx.beginPath();ctx.arc(x,y,rad*1.08,0,6.2832);ctx.fill();}
    ctx.globalAlpha=1;
   }

   // The season as a journey: legs draw on in calendar order.
   const legs=rounds.filter(r=>r.point);
   const progress=reduce?1:ease((now-t.routeStart)/2200)*Math.max(1,legs.length-1);
   ctx.lineCap='round';
   for(let i=0;i<legs.length-1;i++){
    const amt=Math.min(1,Math.max(0,progress-i));if(amt<=0)break;
    const a=legs[i].point!,b=legs[i+1].point!;
    const ax=X(a[0]),ay=Y(a[1]),bx=X(b[0]),by=Y(b[1]);
    const mx=(ax+bx)/2,my=(ay+by)/2,len=Math.hypot(bx-ax,by-ay);
    const cx=mx,cy=my-Math.min(90,len*.2);
    const done=legs[i+1].done;
    ctx.strokeStyle=done?'rgba(238,242,245,.34)':'rgba(238,242,245,.16)';ctx.lineWidth=done?1.25:1;ctx.setLineDash(done?[]:[3,5]);
    ctx.beginPath();ctx.moveTo(ax,ay);
    const steps=Math.max(6,Math.round(len/6*amt));
    for(let j=1;j<=steps;j++){const u=amt*j/steps,v=1-u;ctx.lineTo(v*v*ax+2*v*u*cx+u*u*bx,v*v*ay+2*v*u*cy+u*u*by)}
    ctx.stroke();
    if(amt<1){const u=amt,v=1-u;const hx=v*v*ax+2*v*u*cx+u*u*bx,hy=v*v*ay+2*v*u*cy+u*u*by;
     ctx.setLineDash([]);ctx.fillStyle=C.ink;ctx.beginPath();ctx.arc(hx,hy,2.4,0,6.2832);ctx.fill();}
   }
   ctx.setLineDash([]);

   // Pins
   const placed:{key:string;x:number;y:number}[]=[];
   legs.forEach((r,i)=>{
    if(!reduce&&progress<i-.02)return;
    const x=X(r.point![0]),y=Y(r.point![1]);placed.push({key:r.key,x,y});
    const isPick=r.key===selected,isHover=r.key===hovered;
    if(isPick)return;
    ctx.beginPath();ctx.arc(x,y,isHover?5:3.2,0,6.2832);
    if(r.done){ctx.fillStyle=isHover?C.ink:'rgba(238,242,245,.82)';ctx.fill()}else{ctx.fillStyle=C.plate;ctx.fill();ctx.strokeStyle='rgba(238,242,245,.7)';ctx.lineWidth=1.2;ctx.stroke()}
   });
   pins.current=placed;
   if(pick?.point){
    const x=X(pick.point[0]),y=Y(pick.point[1]);
    if(!reduce){const p=((now/1000)%1.8)/1.8;ctx.strokeStyle=C.red;ctx.globalAlpha=1-p;ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(x,y,6+p*22,0,6.2832);ctx.stroke();ctx.globalAlpha=1}
    ctx.fillStyle=C.red;ctx.beginPath();ctx.arc(x,y,6,0,6.2832);ctx.fill();
    ctx.fillStyle=C.ink;ctx.beginPath();ctx.arc(x,y,2,0,6.2832);ctx.fill();
   }
   // Hover plate
   const hov=hovered&&hovered!==selected?rounds.find(r=>r.key===hovered):null;
   if(hov?.point){
    const x=X(hov.point[0]),y=Y(hov.point[1]);
    const label=`R${String(hov.round).padStart(2,'0')}  ${hov.short}`;
    ctx.font='600 13px "RHX Barlow", Barlow, Arial, sans-serif';const tw=ctx.measureText(label).width;
    let lx=x+12,ly=y-30;if(lx+tw+20>w)lx=x-tw-32;if(ly<6)ly=y+12;
    ctx.fillStyle=C.plate;ctx.strokeStyle='rgba(238,242,245,.22)';ctx.lineWidth=1;
    ctx.beginPath();ctx.roundRect(lx,ly,tw+20,26,3);ctx.fill();ctx.stroke();
    ctx.fillStyle=C.ink;ctx.textBaseline='middle';ctx.fillText(label,lx+10,ly+13.5);
   }
  };
  raf=requestAnimationFrame(frame);
  return()=>{cancelAnimationFrame(raf);ro.disconnect();io.disconnect()};
 },[]);

 const nearest=(e:React.PointerEvent<HTMLCanvasElement>)=>{
  const r=e.currentTarget.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
  let best:string|null=null,bd=e.pointerType==='touch'?26:16;
  for(const p of pins.current){const d=Math.hypot(p.x-x,p.y-y);if(d<bd){bd=d;best=p.key}}
  return best;
 };
 return <canvas ref={canvas} className="rhx-map-canvas" aria-hidden="true"
  onPointerMove={e=>{const k=nearest(e);onHover(k);e.currentTarget.style.cursor=k?'pointer':'default'}}
  onPointerLeave={()=>onHover(null)}
  onClick={e=>{const k=nearest(e as any);if(k)onSelect(k)}}/>;
}
