import {useEffect,useRef,useState,type PointerEvent} from 'react';
import {ChevronLeft,ChevronRight} from 'lucide-react';

type Constructor={id:string;name:string;image:string};

export default function ConstructorShowcase({cars,season}:{cars:Constructor[];season:number}){
 const [index,setIndex]=useState(0),[interaction,setInteraction]=useState(0);
 const [hovered,setHovered]=useState(false),[focused,setFocused]=useState(false);
 const [offset,setOffset]=useState(0),[dragging,setDragging]=useState(false);
 const gesture=useRef<{id:number;x:number;y:number;horizontal:boolean}|null>(null);
 const count=cars.length,active=count?index%count:0,car=cars[active];

 const choose=(next:number)=>{
  if(count<2)return;
  setIndex((next+count)%count);
  setInteraction(n=>n+1);
 };
 useEffect(()=>{
  if(count<2||hovered||focused||dragging||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const timer=setTimeout(()=>setIndex(i=>(i+1)%count),8000);
  return()=>clearTimeout(timer);
 },[count,index,interaction,hovered,focused,dragging]);

 const endGesture=(event:PointerEvent<HTMLDivElement>,cancelled=false)=>{
  const start=gesture.current;
  if(!start||event.pointerId!==start.id)return;
  const dx=event.clientX-start.x;
  if(!cancelled&&start.horizontal&&Math.abs(dx)>=Math.max(38,event.currentTarget.clientWidth*.07)){
   choose(active+(dx<0?1:-1));
  }
  gesture.current=null;setDragging(false);setOffset(0);
  if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
 };

 return <div className={'hero-art constructor-showcase '+(dragging?'is-dragging':'')}
  role="region" aria-roledescription={count>1?'carousel':undefined} aria-label="Constructor showcase"
  tabIndex={count>1?0:undefined}
  onFocus={()=>setFocused(true)} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setFocused(false)}}
  onPointerEnter={e=>{if(e.pointerType==='mouse')setHovered(true)}} onPointerLeave={()=>setHovered(false)}
  onKeyDown={e=>{
   if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)||count<2)return;
   e.preventDefault();choose(e.key==='Home'?0:e.key==='End'?count-1:active+(e.key==='ArrowRight'?1:-1));
  }}
  onPointerDown={e=>{
   if(count<2||!e.isPrimary||e.button!==0||(e.target as HTMLElement).closest('button'))return;
   gesture.current={id:e.pointerId,x:e.clientX,y:e.clientY,horizontal:false};
   e.currentTarget.setPointerCapture(e.pointerId);
  }}
  onPointerMove={e=>{
   const start=gesture.current;if(!start||start.id!==e.pointerId)return;
   const dx=e.clientX-start.x,dy=e.clientY-start.y;
   if(!start.horizontal&&Math.abs(dx)>10&&Math.abs(dx)>Math.abs(dy)*1.25){start.horizontal=true;setDragging(true)}
   if(start.horizontal){if(e.cancelable)e.preventDefault();setOffset(Math.max(-45,Math.min(45,dx*.25)))}
  }}
  onPointerUp={e=>endGesture(e)} onPointerCancel={e=>endGesture(e,true)}>
  <span className="hero-giantnum" aria-hidden="true">RH</span>
  <div className="constructor-stage" style={{transform:`translateX(${offset}px)`}}>
   <img key={car?.id||'ferrari'} src={car?'/art/f1_2026/'+car.image:'/design/ferrari-race.png'}
    alt={car?`${car.name} constructor artwork`:'User-supplied Ferrari race artwork'} draggable={false}/>
  </div>
  <div className="hero-car-caption">
   <div className="constructor-meta"><div><span>{car?'CONSTRUCTOR SHOWCASE / '+season:'RACE HYPE / ARTWORK'}</span>
    <strong>{car?.name||'BUILT FOR THE OBSESSED.'}</strong></div>
    {count>1&&<div className="constructor-arrows">
     <button aria-label="Previous constructor" onClick={()=>choose(active-1)}><ChevronLeft size={17}/></button>
     <button aria-label="Next constructor" onClick={()=>choose(active+1)}><ChevronRight size={17}/></button>
    </div>}
   </div>
   {count>1&&<div className="constructor-pagination-row"><div className="car-pagination" aria-label="Choose constructor">
    {cars.map((c,i)=><button key={c.id} className={i===active?'active':''} aria-current={i===active?'true':undefined}
     onClick={()=>choose(i)} aria-label={'Show '+c.name}/>)}
   </div><span className="constructor-count">{String(active+1).padStart(2,'0')} / {String(count).padStart(2,'0')}</span></div>}
   {count>1&&<span className="constructor-swipe-hint">SWIPE OR DRAG TO EXPLORE</span>}
  </div>
 </div>;
}
