import {useState} from 'react';
import {useSession,useTask,useResource} from '../../state';
import {request} from '../../api';
import {PageHead,NeedSession,Choice,Slider,NumberField,Group,Action,JobBar,FileButton,Note,SourcePicker,Shape} from '../kit';
import {DuelBar} from '../DriverDuel';
import Stage,{overlayPlace} from '../Stage';
import {FootageStudio} from './Footage';

const CANVASES=[['1080x1920','9:16',1080,1920],['1920x1080','16:9',1920,1080],['1080x1080','1:1',1080,1080],['1080x1350','4:5',1080,1350]] as const;

export default function Overlays(){
 const {selection:s,catalog}=useSession();const task=useTask('rh-hud-active'),health=useResource('/api/health');
 const [make,setMake]=useState('overlay'),[source,setSource]=useState('Auto'),[upload,setUpload]=useState(''),[fps,setFps]=useState(30);
 const [width,setWidth]=useState(1080),[height,setHeight]=useState(1920),[hudWidth,setHudWidth]=useState(460),[position,setPosition]=useState('Bottom left');
 const [x,setX]=useState(80),[y,setY]=useState(1180),[format,setFormat]=useState('WebM VP9 Alpha'),[time,setTime]=useState(0);
 const options={source,upload_id:upload,fps,width,height,hud_width:hudWidth,position,x,y,time};
 const valid=source==='Upload CSV'?!!upload:!!catalog;
 const preset=CANVASES.find(c=>c[2]===width&&c[3]===height)?.[0]||'custom';
 const noFfmpeg=!!health.value&&!health.value.ffmpeg&&format!=='PNG Sequence';
 const file=task.result?.file;
 const bar=(w:number)=><span className="rhx-sizebar" style={{width:w/560*100+'%'}}/>;
 const hudGroup=<Group title="HUD">      <Choice label="Size" value={hudWidth} onChange={setHudWidth} variant="cards" options={[{value:360,label:'Small',hint:'360 px',visual:bar(360)},{value:460,label:'Medium',hint:'460 px',visual:bar(460)},{value:560,label:'Large',hint:'560 px',visual:bar(560)}]}/>      <Choice label="Position" value={position} onChange={setPosition} options={['Bottom left','Bottom center','Bottom right','Custom'].map(v=>({value:v,label:v==='Custom'?'Free (drag it)':v}))}/>      {position==='Custom'&&<div className="rhx-pair"><NumberField label="X" suffix="px" value={x} onChange={setX}/><NumberField label="Y" suffix="px" value={y} onChange={setY}/></div>}      <Note>Drag the box on the frame to place the HUD anywhere. Arrow keys nudge it, Shift moves further.</Note>     </Group>;
 return <main className="rhx-page-body">
  <PageHead title="Make the moment." lede="A broadcast HUD drawn from real lap data. Layer it in your editor, or put it straight onto your own onboard clip."/>
  <Choice label="What to make" value={make} onChange={setMake} variant="cards" className="is-wide" options={[
   {value:'overlay',label:'Transparent overlay',hint:'A HUD-only file to layer over footage in your editor'},
   {value:'footage',label:'Add it to your clip',hint:'Upload an onboard, sync it from the engine sound, download one finished video'}]}/>
  <SourcePicker {...{source,setSource,upload,setUpload,request}}/>
  {make==='footage'&&source==='Upload CSV'&&<p className="rhx-error">Syncing to your clip needs session telemetry with timestamps. Choose Auto, FastF1 or OpenF1.</p>}
  {(source!=='Upload CSV'||make==='footage')&&(!catalog?<NeedSession what={make==='footage'?'Syncing your clip':'An overlay'}/>:<DuelBar pair={false}/>)}
  {make==='footage'&&catalog&&source!=='Upload CSV'&&<FootageStudio hudWidth={hudWidth} position={position} x={x} y={y} source={source}
   onMove={(nx,ny)=>{setPosition('Custom');setX(nx);setY(ny)}} hudControls={hudGroup}/>}
  {make==='overlay'&&(source==='Upload CSV'||catalog)&&<div className="rhx-studio">
   <div className="rhx-studio-controls">
    <Group title="Canvas">
     <Choice label="Canvas" value={preset} variant="shapes" onChange={v=>{const c=CANVASES.find(c=>c[0]===v);if(c){setWidth(c[2]);setHeight(c[3])}}}
      options={[...CANVASES.map(([v,r,w,h])=>({value:v as string,label:r,hint:`${w} × ${h}`,visual:<Shape w={w} h={h}/>})),{value:'custom',label:'Custom',hint:'Any size'}]}/>
     {preset==='custom'&&<div className="rhx-pair"><NumberField label="Width" suffix="px" min={64} max={3840} value={width} onChange={setWidth}/><NumberField label="Height" suffix="px" min={64} max={3840} value={height} onChange={setHeight}/></div>}
    </Group>
    {hudGroup}
    <Group title="Timing and export">
     <Slider label="Preview moment" min={0} max={180} step={.1} value={time} format={v=>v.toFixed(1)+' s into the lap'} onChange={setTime}/>
     <Choice label="Frame rate" value={fps} onChange={setFps} options={[24,25,30,50,60].map(v=>({value:v,label:String(v)}))}/>
     <Choice label="Export as" value={format} onChange={setFormat} variant="cards" options={[{value:'WebM VP9 Alpha',label:'WebM',hint:'VP9 with alpha, plays in browsers'},{value:'MOV ProRes 4444',label:'ProRes 4444',hint:'MOV for Premiere, Resolve, Final Cut'},{value:'PNG Sequence',label:'PNG sequence',hint:'One transparent image per frame'}]}/>
     {noFfmpeg&&<p className="rhx-error">FFmpeg isn't available, so only the PNG sequence can be exported.</p>}
     <Note>Actual source data only. Missing boost, overtake, recharge and active-aero fields stay empty.</Note>
    </Group>
   </div>
   <aside className="rhx-monitor">
    <Stage place={overlayPlace} width={width} height={height} hud={hudWidth} position={position} x={x} y={y} onMove={(nx,ny)=>{setPosition('Custom');setX(nx);setY(ny)}}
     image={file?.name.endsWith('.png')?file.url:undefined} video={file?.name.endsWith('.webm')?file.url:undefined}/>
    <JobBar task={task}/>
    <div className="rhx-pair">
     <Action quiet disabled={task.busy||!valid} sub={`at ${time.toFixed(1)}s`} onClick={()=>task.start('hud',s,{...options,format:'Preview'})}>Update preview</Action>
     <Action disabled={task.busy||!valid||noFfmpeg} sub={format} onClick={()=>task.start('hud',s,{...options,format})}>Export overlay</Action>
    </div>
    {task.result&&<div className="rhx-result"><FileButton file={file}/><Note>Source: {task.result.metadata.source}.{task.result.frames?` ${task.result.frames} frames, ${task.result.duration.toFixed(2)} s.`:''} MOV and PNG sequences are for your editor; browsers may not play them.</Note></div>}
   </aside>
  </div>}
 </main>;
}
