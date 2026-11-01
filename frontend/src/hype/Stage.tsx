import {useRef,type ReactNode} from 'react';

// The HUD art is square (345 × 345 at native size), so its height equals its width.
export const HUD_RATIO=1;
type Place=(preset:string,W:number,H:number,hw:number,hh:number,x:number,y:number)=>{x:number;y:number};
const clampTo=(W:number,H:number,hw:number,hh:number,p:{x:number;y:number})=>({x:Math.max(0,Math.min(W-hw,p.x)),y:Math.max(0,Math.min(H-hh,p.y))});
/** Same placement as services/hud_renderer.resolve_hud_position for transparent overlays. */
export const overlayPlace:Place=(preset,W,H,hw,hh,x,y)=>clampTo(W,H,hw,hh,preset==='Custom'?{x,y}:{x:preset==='Bottom center'?Math.round((W-hw)/2):preset==='Bottom right'?W-hw-80:80,y:1180});
/** Same placement as services/footage_sync.hud_position for burn-in on your clip. */
export const footagePlace:Place=(preset,W,H,hw,hh,x,y)=>{const mx=Math.round(W*.04),mb=Math.round(H*.05);
 return clampTo(W,H,hw,hh,preset==='Custom'?{x,y}:{x:preset==='Bottom center'?Math.floor((W-hw)/2):preset==='Bottom right'?W-hw-mx:mx,y:H-hh-mb})};

export default function Stage({width,height,hud,position,x,y,onMove,place,backdrop,image,video,children}:{width:number;height:number;hud:number;position:string;x:number;y:number;
 onMove:(x:number,y:number)=>void;place:Place;backdrop?:string;image?:string;video?:string;children?:ReactNode}){
 const box=useRef<HTMLDivElement>(null);const drag=useRef<{px:number;py:number;x:number;y:number}|null>(null);
 const hh=Math.round(hud*HUD_RATIO);
 const pos=place(position,width,height,hud,hh,x,y);
 const move=(nx:number,ny:number)=>{const c=clampTo(width,height,hud,hh,{x:nx,y:ny});onMove(Math.round(c.x),Math.round(c.y))};
 const scale=()=>width/(box.current?.clientWidth||width);
 return <div className={'rhx-stage-frame '+(backdrop?'has-backdrop':'')} ref={box} style={{aspectRatio:`${width}/${height}`,maxWidth:`calc(64vh * ${width/height})`}}>
  {backdrop&&<img className="rhx-stage-backdrop" src={backdrop} alt="A frame from your clip"/>}
  {image&&<img src={image} alt="Rendered HUD preview"/>}
  {video&&<video src={video} controls playsInline/>}
  {!video&&<div className={'rhx-hudbox '+(image?'is-ghost':'')} role="slider" tabIndex={0} aria-label="HUD position. Drag, or use arrow keys."
   aria-valuetext={`x ${Math.round(pos.x)}, y ${Math.round(pos.y)}`}
   style={{left:pos.x/width*100+'%',top:pos.y/height*100+'%',width:hud/width*100+'%',height:hh/height*100+'%'}}
   onPointerDown={e=>{drag.current={px:e.clientX,py:e.clientY,x:pos.x,y:pos.y};e.currentTarget.setPointerCapture(e.pointerId)}}
   onPointerMove={e=>{const d=drag.current;if(!d)return;const k=scale();move(d.x+(e.clientX-d.px)*k,d.y+(e.clientY-d.py)*k)}}
   onPointerUp={()=>{drag.current=null}}
   onKeyDown={e=>{const st=e.shiftKey?50:10;const d={ArrowLeft:[-st,0],ArrowRight:[st,0],ArrowUp:[0,-st],ArrowDown:[0,st]}[e.key];if(d){e.preventDefault();move(pos.x+d[0],pos.y+d[1])}}}>
   <span>HUD {hud}px</span></div>}
  {children}
 </div>;
}
