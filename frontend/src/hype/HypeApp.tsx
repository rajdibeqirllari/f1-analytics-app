import {Suspense,useEffect} from 'react';
import {recoverableLazy as lazy,ChunkBoundary} from '../chunkRecovery';
import {Link,NavLink,Routes,Route,useLocation} from 'react-router-dom';
import rhLogo from '../assets/rh-logo.png';
import {NAV} from './nav';
import {WeekendBar} from './kit';
import Picker from './pages/Picker';
import './hype.css';
import './kit.css';

const Videos=lazy(()=>import('./pages/Videos'));
const Overlays=lazy(()=>import('./pages/Overlays'));
const Analysis=lazy(()=>import('./pages/Analysis'));
const Timing=lazy(()=>import('./pages/Timing'));
const Telemetry=lazy(()=>import('./pages/Telemetry'));
const Replay=lazy(()=>import('./pages/Replay'));
const Radio=lazy(()=>import('./pages/Radio'));
const Library=lazy(()=>import('./pages/Library'));
const Live=lazy(()=>import('./pages/Live'));

export default function HypeApp(){
 const loc=useLocation();const search=loc.search;
 const sub=loc.pathname.replace(/^\/hype/,'').replace(/\/$/,'');
 const here=NAV.find(n=>n[0]===sub)||NAV[0];
 useEffect(()=>{document.documentElement.classList.add('rhx-page');return()=>document.documentElement.classList.remove('rhx-page')},[]);
 useEffect(()=>{window.scrollTo({top:0,behavior:'instant' as ScrollBehavior})},[sub]);
 return <div className="rhx">
  <header className="rhx-top">
   <Link to={{pathname:'/hype',search}} className="rhx-brand" aria-label="Race Hype, pick a weekend"><img src={rhLogo} alt=""/><span>RACE HYPE</span></Link>
   <nav className="rhx-nav" aria-label="Pages">{NAV.map(([path,label,Icon])=><NavLink key={path} end to={{pathname:'/hype'+path,search}} aria-label={label} className={({isActive})=>isActive?'on':''}>
    <Icon aria-hidden="true"/><span>{label}</span></NavLink>)}</nav>
   <Link className="rhx-classic" to={{pathname:here[3],search}}>Classic workspace</Link>
  </header>
  {sub&&sub!=='/live'&&<div className="rhx-wbar-row"><WeekendBar/></div>}
  <ChunkBoundary className="rhx-chunk-error"><Suspense fallback={<div className="rhx-loading" aria-label="Loading page"/>}>
   <Routes>
    <Route index element={<Picker/>}/>
    <Route path="videos" element={<Videos/>}/>
    <Route path="overlays" element={<Overlays/>}/>
    <Route path="analysis" element={<Analysis/>}/>
    <Route path="timing" element={<Timing/>}/>
    <Route path="telemetry" element={<Telemetry/>}/>
    <Route path="replay" element={<Replay/>}/>
    <Route path="radio" element={<Radio/>}/>
    <Route path="library" element={<Library/>}/>
    <Route path="live" element={<Live/>}/>
    <Route path="*" element={<Picker/>}/>
   </Routes>
  </Suspense></ChunkBoundary>
  <footer className="rhx-foot"><span>Chase the detail.</span><span>{sub==='/live'?'@theracehype · Unofficial fan project, not affiliated with Formula 1. Public timing data; map positions are estimated; AI commentary.':'@theracehype · Historical session data, not a live feed.'}</span></footer>
 </div>;
}
