import {useRef} from 'react';

// The season as a rolling odometer: drag, scroll, arrow keys or tap a neighbouring year.
export default function YearOdometer({year,years,onChange}:{year:number;years:number[];onChange:(y:number)=>void}){
 const min=Math.min(...years),max=Math.max(...years);
 const drag=useRef<{x:number;start:number;moved:boolean}|null>(null);
 const wheelAt=useRef(0);
 const set=(y:number)=>{const n=Math.max(min,Math.min(max,y));if(n!==year)onChange(n)};
 const digits=String(year).split('').map(Number);
 return <div className="rhx-year">
  <button type="button" className="rhx-year-step" disabled={year<=min} onClick={()=>set(year-1)} aria-label={`Season ${year-1}`}>{year>min?year-1:''}</button>
  <div className="rhx-odometer" role="slider" tabIndex={0} aria-label="Season" aria-valuemin={min} aria-valuemax={max} aria-valuenow={year}
   aria-valuetext={`${year} season`}
   onKeyDown={e=>{const d={ArrowLeft:-1,ArrowDown:-1,ArrowRight:1,ArrowUp:1,PageDown:-3,PageUp:3}[e.key];
    if(d){e.preventDefault();set(year+d)}if(e.key==='Home'){e.preventDefault();set(min)}if(e.key==='End'){e.preventDefault();set(max)}}}
   onWheel={e=>{const now=performance.now();if(now-wheelAt.current<180)return;const d=Math.abs(e.deltaX)>Math.abs(e.deltaY)?e.deltaX:e.deltaY;if(Math.abs(d)<4)return;wheelAt.current=now;set(year+(d>0?-1:1))}}
   onPointerDown={e=>{drag.current={x:e.clientX,start:year,moved:false};e.currentTarget.setPointerCapture(e.pointerId)}}
   onPointerMove={e=>{const g=drag.current;if(!g)return;const steps=Math.round((g.x-e.clientX)/46);if(steps){g.moved=true;set(g.start+steps)}}}
   onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}}>
   {digits.map((d,i)=><span className="rhx-digit" key={i}><span className="rhx-digit-reel" style={{transform:`translateY(${-d*10}%)`,transitionDelay:`${(digits.length-1-i)*40}ms`}}>
    {Array.from({length:10},(_,n)=><span key={n} aria-hidden="true">{n}</span>)}</span></span>)}
  </div>
  <button type="button" className="rhx-year-step" disabled={year>=max} onClick={()=>set(year+1)} aria-label={`Season ${year+1}`}>{year<max?year+1:''}</button>
 </div>;
}
