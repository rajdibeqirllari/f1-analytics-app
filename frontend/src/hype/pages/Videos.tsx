import {useState} from 'react';
import {useSession,useTask,useResource} from '../../state';
import {clock} from '../../api';
import {PageHead,NeedSession,Choice,Slider,NumberField,Group,Action,JobBar,FileButton,Note,Shape} from '../kit';
import {DuelBar} from '../DriverDuel';

const ART:Record<string,React.ReactElement>={
 director:<svg viewBox="0 0 120 64"><path d="M8 50 C30 50 30 14 58 14 S88 46 112 30" className="a-track"/><circle cx="58" cy="14" r="4" className="a-a"/><circle cx="44" cy="24" r="4" className="a-b"/><rect x="82" y="44" width="30" height="13" rx="2" className="a-box"/></svg>,
 '2D':<svg viewBox="0 0 120 64"><path d="M10 46 L34 18 L60 40 L84 12 L110 34" className="a-a-line"/><path d="M10 50 L34 26 L60 44 L84 22 L110 38" className="a-b-line"/></svg>,
 cinematic:<svg viewBox="0 0 120 64"><path d="M50 8 L70 8 L112 60 L8 60 Z" className="a-road"/><rect x="40" y="38" width="14" height="9" rx="2" className="a-a-fill"/><rect x="66" y="26" width="11" height="7" rx="2" className="a-b-fill"/></svg>,
 chase:<svg viewBox="0 0 120 64"><path d="M30 46 H90 M38 46 V36 H82 V46 M46 36 L52 22 H68 L74 36 M24 30 H96" className="a-track"/><circle cx="34" cy="50" r="7" className="a-tyre"/><circle cx="86" cy="50" r="7" className="a-tyre"/></svg>,
 onboard:<svg viewBox="0 0 120 64"><path d="M10 60 C24 30 40 18 60 18 S96 30 110 60" className="a-track"/><path d="M60 18 V60" className="a-track"/><path d="M34 60 C44 46 76 46 86 60" className="a-a-line"/></svg>,
};
const MODES=[
 ['director','Race Hype Cut','A live timer, shifting gaps and rotating trackside angles. The signature take.'],
 ['2D','The Breakdown','A bird’s-eye view of both laps. Every input, every gain.'],
 ['cinematic','Trackside','Both cars in 3D. Follow them or watch the full circuit.'],
 ['chase','On Their Tail','Close behind one car, the rival as a ghost.'],
 ['onboard','In the Cockpit','Mounted camera, translucent rival. Best in landscape.'],
] as const;
const STORIES=[
 ['The Limit','A 3.2s time-canyon opening, measured-gain callouts and a sculpture finale.'],
 ['Cinematic Ghost Chase','Steady chase camera with a ghost rival and smooth zoom.'],
 ['Classic Broadcast','Overhead broadcast framing, like a TV replay.'],
 ['Social director','The original Race Hype Cut camera, kept for older edits.'],
] as const;

export default function Videos(){
 const {selection:s,catalog}=useSession(),health=useResource('/api/health');
 const task=useTask('rh-video-active');
 const [mode,setMode]=useState('director'),[orientation,setOrientation]=useState('portrait'),[camera,setCamera]=useState('Follow cars'),[focus,setFocus]=useState('A'),[quality,setQuality]=useState('Balanced');
 const [resolution,setResolution]=useState(540),[finalResolution,setFinalResolution]=useState(1080),[fps,setFps]=useState(60),[length,setLength]=useState('full'),[start,setStart]=useState(0),[duration,setDuration]=useState(10);
 const [playbackSpeed,setPlaybackSpeed]=useState(3),[cameraStyle,setCameraStyle]=useState('The Limit'),[pacing,setPacing]=useState('Dynamic cinematic'),[targetDuration,setTargetDuration]=useState(35);
 const [cameraOptions,setCameraOptions]=useState({smoothness:.55,lookahead:.35,zoom:1,dynamic_zoom:.35,intensity:.35,framing:1});
 const [audio,setAudio]=useState('The Duel'),[audioVolume,setAudioVolume]=useState(80);
 const dynamic=mode==='director'&&pacing==='Dynamic cinematic';
 // Same request shape as the classic Videos page: nothing about the render changes.
 const settings={style:mode==='2D'?'2D':'3D',orientation,camera:mode==='director'?cameraStyle:mode==='onboard'?'Onboard ghost '+focus:mode==='chase'?'Night chase '+focus:camera,quality,playback_speed:playbackSpeed,pacing:dynamic?pacing:'Constant',target_duration:targetDuration,camera_options:cameraOptions,audio,audio_volume:audioVolume,start:length==='full'?0:start,end:length==='full'?null:start+duration};
 const unavailable=mode!=='2D'&&health.value&&!health.value.blender;
 const valid=!!catalog&&s.driver!==s.driver_b&&!!s.driver&&!!s.driver_b;
 const limit=mode==='director'&&cameraStyle==='The Limit';
 const outLine=dynamic?`About ${(targetDuration+(limit?3.2:0)).toFixed(1)} seconds${limit?', including the 3.2s opening':''}, with a 2s result`
  :length==='clip'?`${duration} lap seconds become ${(duration/playbackSpeed).toFixed(1)} seconds of action`:`The full lap at ${playbackSpeed}×, then a 2s result`;
 const r=task.result;

 return <main className="rhx-page-body">
  <PageHead title="Two drivers. One clip." lede="Pick the look, set the pace, render a short preview first. Lap clocks and gaps come straight from the data."/>
  {!catalog?<NeedSession what="A comparison video"/>:<>
   <DuelBar/>
   <div className="rhx-modes" role="radiogroup" aria-label="Video style">{MODES.map(([key,title,copy])=><button type="button" key={key} role="radio" aria-checked={mode===key}
    className={'rhx-mode '+(mode===key?'on':'')} onClick={()=>setMode(key)}><span className="rhx-mode-art" aria-hidden="true">{ART[key]}</span><b>{title}</b><small>{copy}</small></button>)}</div>
   <div className="rhx-studio">
    <div className="rhx-studio-controls">
     <Group title="Look">
      <Choice label="Frame" value={orientation} onChange={setOrientation} variant="shapes" options={[{value:'portrait',label:'Vertical 9:16',hint:'Reels, TikTok, Shorts',visual:<Shape w={9} h={16}/>},{value:'landscape',label:'Landscape 16:9',hint:'YouTube',visual:<Shape w={16} h={9}/>}]}/>
      {mode==='director'&&<Choice label="Story" value={cameraStyle} onChange={setCameraStyle} variant="cards" className="is-wide" options={STORIES.map(([v,h])=>({value:v,label:v==='Classic Broadcast'?'Classic Broadcast':v==='Social director'?'Legacy Race Hype Cut':v,hint:h}))}/>}
      {limit&&<Note>Ridge height in the opening shows time advantage, not track elevation.</Note>}
      {(mode==='chase'||mode==='onboard')&&<Choice label={mode==='onboard'?'Whose cockpit':'Follow'} value={focus} onChange={setFocus} options={[{value:'A',label:s.driver},{value:'B',label:s.driver_b}]}/>}
      {(mode==='2D'||mode==='cinematic')&&<Choice label="Camera" value={camera} onChange={setCamera} options={[{value:'Follow cars',label:'Follow the cars'},{value:'Full circuit',label:'Full circuit'}]}/>}
     </Group>
     <Group title="Pace">
      <Choice label="Length" value={length} onChange={setLength} options={[{value:'full',label:'Full lap'},{value:'clip',label:'Short clip'}]}/>
      {length==='clip'&&<div className="rhx-pair"><NumberField label="Start at" suffix="s" min={0} max={1000} step={.1} value={start} onChange={setStart}/><NumberField label="Clip length" suffix="s" min={1} max={300} step={.1} value={duration} onChange={setDuration}/></div>}
      {mode==='director'&&<Choice label="Playback" value={pacing} onChange={setPacing} variant="cards" options={[{value:'Dynamic cinematic',label:'Cinematic pacing',hint:'Braking zones and timing swings get more screen time'},{value:'Constant',label:'Constant speed',hint:'One steady multiplier for the whole lap'}]}/>}
      {dynamic?<Slider label="Target length" min={30} max={40} value={targetDuration} format={v=>v+' s'} onChange={setTargetDuration}/>
       :<Choice label="Speed" value={playbackSpeed} onChange={setPlaybackSpeed} options={[1,2,3,5,8,10,20].map(v=>({value:v,label:v+'×',hint:v===1?'Real time':undefined}))}/>}
      <p className="rhx-readout">{outLine}.</p>
     </Group>
     <Group title="Sound">
      <Choice label="Soundtrack" value={audio} onChange={setAudio} variant="cards" options={[{value:'The Duel',label:'Industrial Cut',hint:'Percussion and tension'},{value:'Grit & Drums',label:'Grit & Drums',hint:'Guitar and bass'},{value:'Silent',label:'Silent',hint:'Add your own audio later'}]}/>
      {audio!=='Silent'&&<><Slider label="Music volume" min={0} max={100} step={5} value={audioVolume} format={v=>v+'%'} onChange={setAudioVolume}/>
       <details className="rhx-details"><summary>Music credit to paste into your post</summary><p>{audio==='The Duel'?'Industrial Cinematic':'Gearhead'} by Kevin MacLeod (incompetech.com). Licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/ · Edited with excerpts, loops, fades and adaptive mixing.</p></details></>}
     </Group>
     <Group title="Quality">
      <Choice label="Finish" value={quality} onChange={setQuality} variant="cards" options={[{value:'Fast',label:'Fast',hint:'8 samples'},{value:'Balanced',label:'Balanced',hint:'24 samples'},{value:'High',label:'High',hint:'64 samples, slowest'}]}/>
      <Choice label="Preview size" value={resolution} onChange={setResolution} options={[540,720,1080].map(v=>({value:v,label:v+'p'}))}/>
      <Choice label="Frame rate" value={fps} onChange={setFps} options={[{value:60,label:'60 fps',hint:'Smoothest'},{value:30,label:'30 fps'},{value:24,label:'24 fps'}]}/>
      {mode==='director'&&<details className="rhx-details"><summary>Fine-tune the camera</summary><div className="rhx-sliders">{([['smoothness','Follow smoothness',.15,1.2],['lookahead','Lookahead',0,1],['zoom','Camera distance',.75,1.5],['dynamic_zoom','Dynamic zoom',0,1],['intensity','Movement',0,1],['framing','Car size in frame',.75,1.3]] as const).map(([key,label,min,max])=>
       <Slider key={key} label={label} min={min} max={max} step={.05} value={cameraOptions[key]} format={v=>v.toFixed(2)} onChange={v=>setCameraOptions({...cameraOptions,[key]:v})}/>)}</div></details>}
     </Group>
    </div>

    <aside className="rhx-monitor">
     <div className={'rhx-screen is-'+orientation}>
      {r?<video src={r.file.url} controls playsInline preload="metadata"/>:<div className="rhx-screen-idle">
       <span className="rhx-screen-duel"><b>{s.driver}</b><em>vs</em><b>{s.driver_b}</b></span>
       <span>{MODES.find(m=>m[0]===mode)?.[1]}{mode==='director'?`, ${cameraStyle==='Social director'?'Legacy':cameraStyle}`:''}</span>
       <small>{task.busy?'Rendering…':'Your preview plays here'}</small></div>}
     </div>
     <JobBar task={task}/>
     {unavailable&&<p className="rhx-error">Blender isn't set up, so 3D styles can't render. Configure Blender or choose The Breakdown.</p>}
     {s.driver===s.driver_b&&<p className="rhx-error">Pick two different drivers.</p>}
     <Action disabled={!valid||task.busy||!!unavailable} sub={`${resolution}p · ${fps} fps · ${quality}`} onClick={()=>task.start('video',s,{...settings,resolution,fps,preview:true})}>Render preview</Action>
     {r&&<div className="rhx-result">
      <div className="rhx-laptimes">{r.laps.map((l:any)=><div key={l.driver}><b>{l.driver}</b><strong>{clock(l.lap_time)}</strong><small>Lap {l.lap}</small></div>)}</div>
      <Note>Showing the last finished render: {r.pacing==='Dynamic cinematic'?'cinematic pacing':`${r.playback_speed??1}× speed`}, {r.fps??24} fps. Change settings and render again to update it.</Note>
      <FileButton file={r.file} label="Download this MP4"/>
      <Choice label="Final size" value={finalResolution} onChange={setFinalResolution} options={[720,1080].map(v=>({value:v,label:v+'p'}))}/>
      <Action quiet disabled={task.busy||!valid||!!unavailable} sub={`${finalResolution}p, same settings`} onClick={()=>task.start('video',s,{...settings,resolution:finalResolution,fps,preview:false,preview_job:task.id?.replace(/^v_/,'')})}>Render final video</Action>
      {r.warnings?.map((w:string)=><Note key={w}>{w}</Note>)}
     </div>}
     {mode!=='2D'&&<details className="rhx-details"><summary>About 3D accuracy and credits</summary><p>Real lap clocks and telemetry on illustrative, telemetry-built circuits. Elevation is estimated from telemetry where usable, otherwise flat. Ghost routes are illustrative, not each driver’s exact line. Generic concept car by Qvist_designs, CC BY 4.0, with team-inspired paint. Not an authentic team replica.</p></details>}
    </aside>
   </div>
  </>}
 </main>;
}
