import React,{Suspense,useState,useEffect} from 'react';
import {recoverableLazy as lazy,ChunkBoundary} from './chunkRecovery';
import {createRoot} from 'react-dom/client';
import {BrowserRouter,Routes,Route,Link,useLocation} from 'react-router-dom';
import {Flag,Timer,ChartNoAxesCombined,Clapperboard,Download,Layers,RotateCcw,Radio,FolderOpen,PanelLeftClose,PanelLeftOpen,Menu,X} from 'lucide-react';
import {SessionProvider,useSession,useResource} from './state';
import {sessions,countryFlags} from './api';
import {ErrorBox,JobStatus} from './components';
import './styles.css';
import './showcase.css';
import rhLogo from './assets/rh-logo.png';
const RaceCenter=lazy(()=>import('./pages/RaceCenter'));
const Timing=lazy(()=>import('./pages/Timing'));
const Analysis=lazy(()=>import('./pages/Analysis'));
const Videos=lazy(()=>import('./pages/Videos'));
const Telemetry=lazy(()=>import('./pages/Telemetry'));
const Overlays=lazy(()=>import('./pages/Overlays'));
const Replay=lazy(()=>import('./pages/Replay'));
const TeamRadio=lazy(()=>import('./pages/TeamRadio'));
const Downloads=lazy(()=>import('./pages/Downloads'));
// New weekend picker lives in its own folder (src/hype) and route (/hype); the classic shell below is unchanged.
import './hype/boot';
const Hype=lazy(()=>import('./hype/HypeApp'));
const navigation=[
 ['/',Flag,'Race Center','Results, standings & race weekends'],
 ['/timing',Timer,'Timing & Positions','Lap times, sectors & race control'],
 ['/analysis',ChartNoAxesCombined,'Lap & Strategy Analysis','Compare pace, tyres & performance'],
 ['/videos',Clapperboard,'Create Comparison Videos','Turn two drivers’ laps into videos'],
 ['/telemetry',Download,'Download Telemetry','Export real driving data'],
 ['/overlays',Layers,'Create Video Overlays','Broadcast graphics for your edits'],
 ['/replay',RotateCcw,'Watch Race Replays','Follow every car on the circuit'],
 ['/radio',Radio,'Listen to Team Radio','Find and play driver communications'],
 ['/downloads',FolderOpen,'My Downloads','Your saved videos, charts & files'],
] as const;

function ContextBar(){
 const {selection:s,setSelection,calendar,calendarError,calendarLoading,catalog,loadCatalog,catalogJob}=useSession();
 const row=calendar.find(e=>e.EventName===s.event);
 return <div className="session-area"><div className="context-bar">
 <label><span>SEASON</span><select aria-label="Season" value={s.year} onChange={e=>setSelection({year:Number(e.target.value),event:'',driver:'',driver_b:'',lap:null,lap_b:null})}>{Array.from({length:new Date().getFullYear()-2017},(_,i)=>new Date().getFullYear()-i).map(y=><option key={y}>{y}</option>)}</select></label>
 <label className="context-event"><span>GRAND PRIX</span><select aria-label="Grand Prix" value={s.event} disabled={calendarLoading} onChange={e=>setSelection({event:e.target.value,driver:'',driver_b:'',lap:null,lap_b:null})}>{!calendar.length&&<option value="">{calendarLoading?'Loading calendar…':'Calendar unavailable'}</option>}{calendar.map(e=><option key={e.EventName}>{e.EventName}</option>)}</select></label>
 <label><span>SESSION</span><select aria-label="Session" value={s.session} onChange={e=>setSelection({session:e.target.value,driver:'',driver_b:'',lap:null,lap_b:null})}>{Object.entries(sessions).map(([code,name])=><option key={code} value={code}>{name}</option>)}</select></label>
 <button className="btn btn-outline" disabled={!s.event||catalogJob.busy} onClick={loadCatalog}>{catalogJob.busy?'Loading session…':catalog?'Reload session':'Load session'} ↗</button>
 </div><div className="context-caption"><span>{countryFlags[row?.Country]&&<img className="context-flag" src={'/art/flags/'+countryFlags[row.Country]+'.png'} alt={row.Country+' flag'}/>} {row?.Country||'SESSION ARCHIVE'} {row?.Location&&' / '+row.Location}</span><span>{catalog?`${Object.keys(catalog.drivers).length} drivers · shared across tools`:'Your weekend follows you between tools'}</span></div><ErrorBox message={calendarError}/><JobStatus task={catalogJob}/></div>;
}
function Shell(){
 const location=useLocation();const [collapsed,setCollapsed]=useState(false),[mobile,setMobile]=useState(false);
 useEffect(()=>{window.scrollTo({top:0,behavior:'instant'})},[location.pathname]);
 const current=navigation.find(n=>n[0]===location.pathname)||navigation[0];
 const health=useResource('/api/health');
 return <div className={'app-shell '+(collapsed?'collapsed ':'')+(mobile?'nav-open':'')}>
 {mobile&&<button className="nav-scrim" aria-label="Close navigation" onClick={()=>setMobile(false)}/>}
 <aside className="sidebar"><Link className="brand" to={{pathname:'/',search:location.search}} aria-label="Race Hype home"><img className="brand-logo" src={rhLogo} alt="RH"/><span className="brand-word">RACE HYPE<small>CHASE THE DETAIL.</small></span></Link><div className="rail-label">YOUR MOTORSPORT WORKSPACE</div>
 <nav className="side-nav" aria-label="Workspaces">{navigation.map(([path,Icon,label,description])=><Link key={path} className={'nav-link '+(location.pathname===path?'active':'')} aria-label={`${label} ${description}`} aria-current={location.pathname===path?'page':undefined} to={{pathname:path,search:location.search}} title={`${label} — ${description}`} onClick={()=>setMobile(false)}><Icon size={20}/><span><b>{label}</b><small>{description}</small></span></Link>)}</nav>
 <div className="sidebar-bottom"><span className="eyebrow soft">THE DETAIL MAKES THE DIFFERENCE.</span><p>For the fans who rewind that corner. Then rewind it again.</p><span className="engine-label">{health.value?'PYTHON ENGINE CONNECTED':'CONNECTING TO ENGINE'}</span></div>
 <button className="collapse-nav" onClick={()=>{setCollapsed(!collapsed);setMobile(false)}} aria-label={collapsed?'Expand navigation':'Collapse navigation'}>{collapsed?<PanelLeftOpen/>:<PanelLeftClose/>}<span>Collapse navigation</span></button></aside>
 <div className="main-shell"><div className="topbar"><button className="mobile-menu icon-button" aria-label={mobile?'Close menu':'Open menu'} onClick={()=>setMobile(!mobile)}>{mobile?<X/>:<Menu/>}</button><div className="crumb"><span>RACE HYPE</span><i>/</i><b>{current[2]}</b></div><span className="archive-label"><i/> REAL DATA. REAL DETAIL.</span></div>
 <ContextBar/><ErrorBox message={health.error}/>
 <main id="main-content"><ChunkBoundary><Suspense fallback={<div className="skeleton" aria-label="Loading workspace"/>}><Routes>
 <Route path="/" element={<RaceCenter/>}/><Route path="/timing" element={<Timing/>}/><Route path="/analysis" element={<Analysis/>}/><Route path="/videos" element={<Videos/>}/><Route path="/telemetry" element={<Telemetry/>}/><Route path="/overlays" element={<Overlays/>}/><Route path="/replay" element={<Replay/>}/><Route path="/radio" element={<TeamRadio/>}/><Route path="/downloads" element={<Downloads/>}/><Route path="*" element={<RaceCenter/>}/>
 </Routes></Suspense></ChunkBoundary></main><footer className="site-footer"><span>RACE HYPE © {new Date().getFullYear()}</span><span>INDEPENDENT MOTORSPORT ANALYSIS · HISTORICAL DATA IS NOT A LIVE FEED</span><b>CHASE THE DETAIL ↗</b></footer></div></div>;
}
class Boundary extends React.Component<{children:React.ReactNode},{error:string}>{state={error:''};static getDerivedStateFromError(error:Error){return {error:error.message}}render(){return this.state.error?<div className="fatal"><h1>RACE HYPE</h1><ErrorBox message={this.state.error}/><button onClick={()=>window.location.reload()}>Reload the workspace</button></div>:this.props.children}}
createRoot(document.getElementById('root')!).render(<Boundary><BrowserRouter><SessionProvider><Routes><Route path="/hype/*" element={<ChunkBoundary><Suspense fallback={null}><Hype/></Suspense></ChunkBoundary>}/><Route path="*" element={<Shell/>}/></Routes></SessionProvider></BrowserRouter></Boundary>);
