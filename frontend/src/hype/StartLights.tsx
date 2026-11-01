import {useEffect,useRef,useState} from 'react';

type Props={label:string;disabled:boolean;busy:boolean;progress:number;message:string;loaded:boolean;onLaunch:()=>void;onCancel:()=>void};

// Five red pods light one by one, then go out — that's when the session request leaves.
// While data loads, the pods fill in telemetry blue to show progress.
export default function StartLights({label,disabled,busy,progress,message,loaded,onLaunch,onCancel}:Props){
 const [lit,setLit]=useState(0),[out,setOut]=useState(false);
 const timers=useRef<number[]>([]);
 const clear=()=>{timers.current.forEach(clearTimeout);timers.current=[]};
 useEffect(()=>clear,[]);
 const sequencing=lit>0;
 const launch=()=>{
  if(disabled||busy||sequencing)return;
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){onLaunch();return}
  clear();setOut(false);
  for(let i=1;i<=5;i++)timers.current.push(window.setTimeout(()=>setLit(i),i*260));
  // Real starts hold for a random beat. Keep it short so it never feels like a wait.
  timers.current.push(window.setTimeout(()=>{setLit(0);setOut(true);onLaunch();timers.current.push(window.setTimeout(()=>setOut(false),900))},5*260+260+Math.random()*320));
 };
 const filled=busy?Math.max(1,Math.ceil(Math.min(.999,progress||0)*5)):0;
 return <div className={'rhx-lights '+(out?'is-out ':'')+(busy?'is-busy ':'')+(loaded&&!busy?'is-loaded':'')}>
  <div className="rhx-gantry" aria-hidden="true">{[1,2,3,4,5].map(i=><span key={i} className={'rhx-pod '+(lit>=i?'on ':'')+(busy&&filled>=i?'fill':'')}><i/><i/></span>)}</div>
  <div className="rhx-launch-row">
   <button type="button" className="rhx-launch" disabled={disabled||busy||sequencing} onClick={launch}>
    <span>{busy?'Loading session':sequencing?'Lights on…':loaded?'Reload session':'Load session'}</span><small>{label}</small>
   </button>
   {busy&&<button type="button" className="rhx-cancel" onClick={onCancel}>Cancel</button>}
  </div>
  <p className="rhx-lights-status" role="status">{busy?(message||'Contacting the data engine'):out?'Lights out.':''}</p>
 </div>;
}
