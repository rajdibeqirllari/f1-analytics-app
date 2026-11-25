/** 3D Broadcast engine: one Three.js world with every car at the same instant, three camera rigs, and its own
 * render loop (independent of React). React only passes the feed, the selected driver and the camera mode in,
 * and receives a small HUD object a few times a second. */
import * as THREE from 'three';
import {Buffer,Clock,TrackCurve,fetchSamples,neighbours,poses,type FeedInfo,type Pose,type SceneInfo,type TimingRow} from './data';
import {labelTexture,makeCar,type CarObject} from './car';
import {loadVenue,nightEnvironment,venueKey,type Venue,type Alignment} from './venue';
import {isDetailed,makeDetailedCar,previewAvailable,resolveModel,type DetailedCar} from './models';

export type CameraMode='pod'|'broadcast'|'cockpit';
export type Hud={elapsed:number|null;utc:number|null;num:string|null;auto:boolean;code:string;name:string;team:string;color:string;timing:TimingRow|null;totalLaps:number|null;
 ahead:{code:string;color:string;m:number}|null;behind:{code:string;color:string;m:number}|null;flag:'ok'|'extrapolated'|'stale'|'none';
 cam:string;battle:string|null;buffering:boolean;error:string;onTrack:number;ghosted:boolean;
 venue:{name:string;status:'loading'|'ready'|'off'|'error';align:Alignment|null;why:string}|null;models:{count:number;preview:boolean;previewAvailable:boolean;labels:string[]}};

const W=(x:number,y:number,z:number)=>new THREE.Vector3(x,z,-y);   // track plane (x east, y north, z up) → three.js
const HALF=7;   // half the asphalt width (m)

function rng(seed:number){return ()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296}}

function noiseTexture(base:[number,number,number],spread:number,size=256,streak=0){
 const c=document.createElement('canvas');c.width=c.height=size;const x=c.getContext('2d')!;const img=x.createImageData(size,size);const r=rng(size*7+spread);
 for(let i=0;i<size*size;i++){const n=(r()-.5)*spread+(streak?Math.sin((i%size)/size*Math.PI*2*streak)*spread*.15:0);
  img.data[i*4]=base[0]+n;img.data[i*4+1]=base[1]+n;img.data[i*4+2]=base[2]+n;img.data[i*4+3]=255}
 x.putImageData(img,0,0);const t=new THREE.CanvasTexture(c);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.colorSpace=THREE.SRGBColorSpace;return t}

/** A strip along the circuit between lateral offsets a and b (left positive), lifted by `lift`. */
function ribbon(tr:TrackCurve,a:number,b:number,lift:number,opts:{uLen?:number;color?:(i:number)=>THREE.Color|null;from?:number;to?:number;outer?:Float32Array;drop?:number}={}){
 const n=tr.n,pos:number[]=[],uv:number[]=[],col:number[]=[];const from=opts.from??0,to=opts.to??n;
 // `outer` caps the outer edge's distance from the centreline per point; `drop` lowers that edge (an embankment).
 const outerIsB=Math.abs(b)>Math.abs(a);
 const P=(i:number,o:number)=>{const k=((i%n)+n)%n;const nx=-tr.ty[k],ny=tr.tx[k];let z=tr.z[k]+lift;
  if(opts.outer&&Math.abs(o)===Math.abs(outerIsB?b:a)){const cap=opts.outer[k];if(Math.abs(o)>cap)o=Math.sign(o)*cap;z+=(opts.drop||0)*Math.min(1,(Math.abs(o)-HALF)/38)}
  return W(tr.x[k]+nx*o,tr.y[k]+ny*o,z)};
 for(let i=from;i<to;i++){const c=opts.color?opts.color(((i%n)+n)%n):null;if(opts.color&&!c)continue;
  const p0=P(i,a),p1=P(i,b),p2=P(i+1,b),p3=P(i+1,a);const u0=(tr.s[((i%n)+n)%n])/(opts.uLen||10),u1=u0+tr.length/n/(opts.uLen||10);
  for(const [p,u,v] of [[p0,u0,0],[p2,u1,1],[p1,u0,1],[p0,u0,0],[p3,u1,0],[p2,u1,1]] as [THREE.Vector3,number,number][]){pos.push(p.x,p.y,p.z);uv.push(u,v);if(c)col.push(c.r,c.g,c.b)}}
 const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));
 if(col.length)g.setAttribute('color',new THREE.Float32BufferAttribute(col,3));g.computeVertexNormals();return g}

function polyRibbon(pts:{x:number;y:number;z:number}[],half:number,lift:number){const pos:number[]=[];
 for(let i=0;i<pts.length-1;i++){const a=pts[i],b=pts[i+1];const dx=b.x-a.x,dy=b.y-a.y,l=Math.hypot(dx,dy)||1,nx=-dy/l*half,ny=dx/l*half;
  const q=[W(a.x+nx,a.y+ny,a.z+lift),W(a.x-nx,a.y-ny,a.z+lift),W(b.x-nx,b.y-ny,b.z+lift),W(b.x+nx,b.y+ny,b.z+lift)];
  for(const k of [0,1,2,0,2,3])pos.push(q[k].x,q[k].y,q[k].z)}
 const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));g.computeVertexNormals();return g}

type Site={i:number;d:number;pos:THREE.Vector3;name:string};

export class BroadcastEngine{
 el:HTMLElement;renderer:THREE.WebGLRenderer;scene=new THREE.Scene();camera:THREE.PerspectiveCamera;
 clock=new Clock();info:SceneInfo|null=null;track:TrackCurve|null=null;world=new THREE.Group();
 cars=new Map<string,CarObject>();labels=new Map<string,string>();buf:Buffer|null=null;prev:Buffer|null=null;
 hints=new Map<string,number>();headings=new Map<string,number>();correction=new Map<string,{v:number;at:number}>();
 feed:FeedInfo|null=null;focus:string|null=null;mode:CameraMode='pod';source='auto';
 /** Where samples come from (Live: the engine's feed; Replay: the loaded replay) and, on Replay, the page's own
  * classification at the displayed instant (the replay payload has no timing feed). */
 samplesBase='/api/live/scene/samples';external:Record<string,TimingRow>|null=null;
 env={street:false,night:false};hemi:THREE.HemisphereLight;sun:THREE.DirectionalLight;amb:THREE.AmbientLight;
 gen=0;inflight:AbortController|null=null;lastFetch=0;fetchErr='';raf=0;timer:any=0;ro:ResizeObserver;lastHud=0;onHud:(h:Hud)=>void;
 sites:Site[]=[];site=-1;cutAt=0;look=new THREE.Vector3();lookReady=false;fov=40;battle:string|null=null;camDir=new THREE.Vector3(1,0,0);camReady=false;lastSel:Pose|null=null;ghosted=false;
 disposed=false;
 /** Procedural circuit (replaced by a venue model when one matches and lines up) and the far skyline. */
 proc=new THREE.Group();far=new THREE.Group();venue:Venue|null=null;venueGen=0;venueState:Hud['venue']=null;
 occluders:THREE.Object3D[]=[];occCheck=0;ray=new THREE.Raycaster();
 key:THREE.DirectionalLight;envTex:THREE.Texture|null=null;preview=false;carGen=0;frameTimes:number[]=[];lastFrame=0;

 constructor(el:HTMLElement,onHud:(h:Hud)=>void){
  this.el=el;this.onHud=onHud;
  this.renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'high-performance',logarithmicDepthBuffer:true});
  this.renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.75));this.renderer.outputColorSpace=THREE.SRGBColorSpace;
  this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.05;
  el.appendChild(this.renderer.domElement);
  this.camera=new THREE.PerspectiveCamera(50,16/9,0.02,9000);
  const sky=document.createElement('canvas');sky.width=4;sky.height=256;const sx=sky.getContext('2d')!;const gr=sx.createLinearGradient(0,0,0,256);
  gr.addColorStop(0,'#5d86b3');gr.addColorStop(.55,'#a9c2d8');gr.addColorStop(1,'#d9d6cb');sx.fillStyle=gr;sx.fillRect(0,0,4,256);
  const bg=new THREE.CanvasTexture(sky);bg.colorSpace=THREE.SRGBColorSpace;this.scene.background=bg;
  this.scene.fog=new THREE.Fog(0xb9cad8,350,3200);
  this.hemi=new THREE.HemisphereLight(0xdfeeff,0x5a6648,1.25);this.scene.add(this.hemi);
  this.sun=new THREE.DirectionalLight(0xfff1dc,1.9);this.sun.position.set(-600,900,400);this.scene.add(this.sun);
  this.amb=new THREE.AmbientLight(0xffffff,0);this.scene.add(this.amb);
  // Key light for venue scenes: the floodlights' main direction, casting the shadow under nearby cars (follows the camera).
  this.key=new THREE.DirectionalLight(0xfff3e4,0);this.key.castShadow=true;this.key.shadow.mapSize.set(2048,2048);
  const sc=this.key.shadow.camera;sc.left=-26;sc.right=26;sc.top=26;sc.bottom=-26;sc.near=1;sc.far=160;this.key.shadow.bias=-0.0004;this.key.shadow.normalBias=0.03;
  this.scene.add(this.key,this.key.target);
  this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  this.scene.add(this.world);
  this.ro=new ResizeObserver(()=>this.resize());this.ro.observe(el);this.resize();
  this.timer=setInterval(()=>this.pump(),250);
  (window as any).__rhxBroadcast=this;   // inspection hook for checks in the browser console
  const loop=()=>{if(this.disposed)return;this.raf=requestAnimationFrame(loop);this.frame()};this.raf=requestAnimationFrame(loop);
 }

 resize(){const w=this.el.clientWidth||640,h=this.el.clientHeight||360;this.renderer.setSize(w,h,false);this.camera.aspect=w/h;this.camera.updateProjectionMatrix()}

 dispose(){this.disposed=true;cancelAnimationFrame(this.raf);clearInterval(this.timer);this.ro.disconnect();this.inflight?.abort();
  this.clearWorld();this.envTex?.dispose();this.renderer.dispose();this.renderer.domElement.remove();if((window as any).__rhxBroadcast===this)(window as any).__rhxBroadcast=null}

 clearWorld(){this.venueGen++;this.carGen++;const v=this.venue;this.venue=null;if(v){v.dispose()}
  // Detailed cars share geometry with the cached model: only their own materials are disposed.
  for(const c of this.cars.values())if(isDetailed(c)){for(const m of c.mats)m.dispose();(c.label.material as THREE.SpriteMaterial).map?.dispose();c.group.removeFromParent()}
  this.world.traverse(o=>{const m=o as THREE.Mesh;if(m.geometry)m.geometry.dispose();const mat=(m as any).material;
   if(mat){for(const x of Array.isArray(mat)?mat:[mat]){(x as any).map?.dispose?.();x.dispose()}}});
  this.occluders=[];this.world.clear();this.proc=new THREE.Group();this.far=new THREE.Group();this.cars.clear();this.labels.clear()}

 resetMotion(){this.gen++;this.inflight?.abort();this.inflight=null;this.buf=null;this.prev=null;this.hints.clear();this.headings.clear();this.correction.clear();
  this.site=-1;this.lookReady=false;this.camReady=false;this.battle=null;this.lastFetch=0}

 setTiming(t:Record<string,TimingRow>|null){this.external=t}
 timingOf(num:string,D:number,buf:Buffer|null):TimingRow|null{return this.external?this.external[num]??null:buf?buf.timingAt(num,D):null}

 /** Street circuit (walls and fences close to the asphalt, buildings, no grass) and/or night race (floodlights). */
 applyEnv(meeting:string){
  const m=meeting.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const street=/las vegas|monaco|singapore|azerbaijan|baku|saudi|jeddah|miami|madrid/.test(m);
  const night=/las vegas|singapore|bahrain|saudi|jeddah|qatar|abu dhabi/.test(m);
  this.env={street,night};
  const sky=document.createElement('canvas');sky.width=4;sky.height=256;const sx=sky.getContext('2d')!;const gr=sx.createLinearGradient(0,0,0,256);
  if(night){gr.addColorStop(0,'#03050b');gr.addColorStop(.6,'#10162a');gr.addColorStop(1,'#3a2a44')}
  else{gr.addColorStop(0,'#5d86b3');gr.addColorStop(.55,'#a9c2d8');gr.addColorStop(1,'#d9d6cb')}
  sx.fillStyle=gr;sx.fillRect(0,0,4,256);const bg=new THREE.CanvasTexture(sky);bg.colorSpace=THREE.SRGBColorSpace;
  (this.scene.background as THREE.Texture|null)?.dispose?.();this.scene.background=bg;
  this.scene.fog=night?new THREE.Fog(0x0b0f1c,300,2600):new THREE.Fog(0xb9cad8,350,3200);
  // Night: floodlit track, so plenty of cool fill light but no sun.
  this.hemi.color.set(night?0xc4ceff:0xdfeeff);this.hemi.groundColor.set(night?0x2a2830:0x5a6648);this.hemi.intensity=night?1.05:1.25;
  this.sun.color.set(night?0xbfd0ff:0xfff1dc);this.sun.intensity=night?0.55:1.9;this.amb.intensity=night?0.45:0;
  this.renderer.toneMappingExposure=night?1.15:1.05}

 setFeed(f:FeedInfo){this.feed=f;const r=this.clock.update(f,performance.now());if(r!=='ok')this.resetMotion();this.pump()}
 /** Labelled preview of a constructor's latest modelled chassis on a session from another season. */
 setPreview(on:boolean){if(on===this.preview)return;this.preview=on;if(this.info?.ok)this.buildCars(this.info)}
 setFocus(n:string|null){if(n!==this.focus){this.focus=n;this.site=-1;this.lookReady=false;this.camReady=false;this.battle=null}}
 setMode(m:CameraMode){if(m!==this.mode){this.mode=m;this.site=-1;this.lookReady=false;this.camReady=false}}

 setScene(info:SceneInfo,source:string){
  this.source=source;this.info=info;this.resetMotion();this.clearWorld();this.track=null;
  if(!info.ok||!info.track?.x?.length)return;
  this.applyEnv(info.session?.meeting||'');
  const tr=this.track=new TrackCurve(info.track);
  this.sites=this.buildSites(tr);
  this.world.add(this.proc,this.far);
  this.buildWorld(tr,info);
  this.buildCars(info);
  // Venue model (only for matching meetings): the procedural circuit stays until the model is loaded and lines up.
  const vk=venueKey(info.session?.meeting||'');this.venueState=null;this.key.intensity=0;this.scene.environment=null;
  if(vk){const gen=this.venueGen;this.venueState={name:vk,status:'loading',align:null,why:''};
   loadVenue(vk,this.renderer).then(v=>{if(gen!==this.venueGen||this.disposed||this.track!==tr){v.dispose();return}
    const r=v.place(tr,info.track.frame);this.venueState={name:v.manifest.name,status:r.ok?'ready':'off',align:v.align,why:r.why};
    if(!r.ok){v.dispose();return}
    this.venue=v;this.world.add(v.root);this.proc.visible=false;this.far.visible=false;this.lightVenue();this.sites=this.venueSites(tr,v);this.site=-1;
    (window as any).__rhxVenue={bytes:v.bytes,loadMs:Math.round(v.loadMs),align:v.align}})
   .catch(e=>{if(gen===this.venueGen)this.venueState={name:vk,status:'error',align:null,why:(e as Error).message}})}
 }

 /** Cars for this scene: the team's modelled chassis for its season (or the labelled preview), else the generic car.
  * The generic car is shown at once and swapped when the model has loaded. */
 buildCars(info:SceneInfo){
  const gen=++this.carGen;
  for(const [num,c] of this.cars){c.group.removeFromParent();if(isDetailed(c))for(const m of c.mats)m.dispose();this.cars.delete(num);this.labels.delete(num)}
  for(const [num,m] of Object.entries(info.drivers)){const car=makeCar(m.color,m.code);car.group.visible=false;this.world.add(car.group);this.cars.set(num,car);
   const r=resolveModel(m.team,info.session?.year,this.preview);if(!r)continue;
   makeDetailedCar(r.entry,m.code,m.color).then(d=>{if(gen!==this.carGen||this.disposed||this.info!==info){for(const x of d.mats)x.dispose();return}
    const old=this.cars.get(num);if(!old)return;
    d.group.visible=old.group.visible;d.group.position.copy(old.group.position);d.group.rotation.copy(old.group.rotation);old.group.removeFromParent();
    this.world.add(d.group);this.cars.set(num,d);this.labels.delete(num)}).catch(e=>console.warn('car model',e))}}

 /** Floodlit night for venue scenes: image-based light with lamp rows, a key light for shadows, low fill. */
 lightVenue(){
  if(!this.envTex)this.envTex=nightEnvironment(this.renderer);
  this.scene.environment=this.envTex;
  this.hemi.color.set(0xaab8d8);this.hemi.groundColor.set(0x2c2a2e);this.hemi.intensity=0.55;
  this.sun.intensity=0.35;this.amb.intensity=0.12;this.key.intensity=2.4;
  this.renderer.toneMappingExposure=1.0;
  this.scene.fog=new THREE.Fog(0x0c0f18,450,3400)}

 // ------------------------------------------------------------- world
 buildWorld(tr:TrackCurve,info:SceneInfo){
  const n=tr.n,L=tr.length;const lam=(o:THREE.MeshLambertMaterialParameters)=>new THREE.MeshLambertMaterial(o);const P=this.proc;
  let minx=Infinity,maxx=-Infinity,miny=Infinity,maxy=-Infinity,minz=Infinity;
  for(let i=0;i<n;i++){minx=Math.min(minx,tr.x[i]);maxx=Math.max(maxx,tr.x[i]);miny=Math.min(miny,tr.y[i]);maxy=Math.max(maxy,tr.y[i]);minz=Math.min(minz,tr.z[i])}
  const sub:number[]=[];for(let i=0;i<n;i+=6)sub.push(i);
  // Nearest track point, plus the lowest track point within 110 m (terrain must never rise over a lower section).
  const nearTrack=(x:number,y:number)=>{let b=Infinity,bi=0,low=Infinity;for(const i of sub){const d=(tr.x[i]-x)**2+(tr.y[i]-y)**2;if(d<b){b=d;bi=i}if(d<110*110&&tr.z[i]<low)low=tr.z[i]}
   return {d:Math.sqrt(b),z:tr.z[bi],low:Number.isFinite(low)?low:tr.z[bi]}};
  // Terrain: follows the circuit's elevation near the track, flattening out far from it, always below the asphalt.
  const pad=1400,cells=110,gw=(maxx-minx)+pad*2,gh=(maxy-miny)+pad*2;const terr=new THREE.PlaneGeometry(gw,gh,cells,cells);terr.rotateX(-Math.PI/2);
  const pa=terr.attributes.position as THREE.BufferAttribute;let zsum=0;for(let i=0;i<n;i++)zsum+=tr.z[i];const zmean=zsum/n;
  for(let i=0;i<pa.count;i++){const x=pa.getX(i)+(minx+maxx)/2,y=-(pa.getZ(i))+(miny+maxy)/2;const q=nearTrack(x,y);const k=Math.min(1,Math.max(0,(q.d-120)/700));
   pa.setXYZ(i,x,(q.low*(1-k)+Math.min(zmean,q.low+8)*k)-2.6-Math.min(3,q.d/250),-y)}
  terr.computeVertexNormals();
  const env=this.env;
  const grass=env.street?noiseTexture([50,52,56],14,256):noiseTexture([70,96,52],26,256);grass.repeat.set(gw/40,gh/40);
  P.add(new THREE.Mesh(terr,lam({map:grass})));
  // Grass verges at track height, sloping down outwards, cut short where another part of the circuit is close.
  const reach=(side:number)=>{const out=new Float32Array(n).fill(HALF+38);
   for(let i=0;i<n;i+=3){let lim=HALF+38;for(let o=HALF+4;o<=HALF+38;o+=4){const x=tr.x[i]-tr.ty[i]*side*o,y=tr.y[i]+tr.tx[i]*side*o;
     let hit=false;for(const j of sub){const ds=Math.abs(tr.s[j]-tr.s[i]),gap=Math.min(ds,L-ds);if(gap<90)continue;if((tr.x[j]-x)**2+(tr.y[j]-y)**2<(HALF+5)**2){hit=true;break}}
     if(hit){lim=Math.max(HALF+1,o-6);break}}
    for(let k=0;k<3&&i+k<n;k++)out[i+k]=lim}
   return out};
  const verge=env.street?noiseTexture([66,68,72],10,128):noiseTexture([82,110,60],22,128);   // street: concrete, not grass
  const vMat=lam({map:verge,polygonOffset:true,polygonOffsetFactor:2,polygonOffsetUnits:2});
  P.add(new THREE.Mesh(ribbon(tr,HALF,HALF+38,-0.06,{uLen:20,outer:reach(1),drop:-2.4}),vMat),new THREE.Mesh(ribbon(tr,-HALF-38,-HALF,-0.06,{uLen:20,outer:reach(-1),drop:-2.4}),vMat));
  // Paved run-off just outside the asphalt edges.
  const runMat=lam({color:0x6b7067,polygonOffset:true,polygonOffsetFactor:1,polygonOffsetUnits:1});
  P.add(new THREE.Mesh(ribbon(tr,HALF,HALF+5,-0.03),runMat),new THREE.Mesh(ribbon(tr,-HALF-5,-HALF,-0.03),runMat));
  const asphalt=noiseTexture([66,68,72],16,256,0);asphalt.anisotropy=8;
  P.add(new THREE.Mesh(ribbon(tr,-HALF,HALF,0,{uLen:14}),lam({map:asphalt})));
  const white=lam({color:0xe9ecef});
  P.add(new THREE.Mesh(ribbon(tr,HALF-0.55,HALF-0.3,0.015),white),new THREE.Mesh(ribbon(tr,-HALF+0.3,-HALF+0.55,0.015),white));
  // Kerbs where the circuit bends, red and white every 2 m.
  const curv=new Float64Array(n);for(let i=0;i<n;i++){const a=(i-8+n)%n,b=(i+8)%n;let dh=Math.atan2(tr.ty[b],tr.tx[b])-Math.atan2(tr.ty[a],tr.tx[a]);dh=(dh+Math.PI*3)%(Math.PI*2)-Math.PI;curv[i]=dh/32}
  const red=new THREE.Color(0xc4232c),wht=new THREE.Color(0xf1f1ee);
  const kc=(side:number)=>(i:number)=>Math.abs(curv[i])>1/260&&Math.sign(curv[i])*side>0||Math.abs(curv[i])>1/90?(Math.floor(tr.s[i]/2.2)%2?red:wht):null;
  const kMat=lam({vertexColors:true});
  P.add(new THREE.Mesh(ribbon(tr,HALF-0.1,HALF+1.3,0.03,{color:kc(1)}),kMat),new THREE.Mesh(ribbon(tr,-HALF-1.3,-HALF+0.1,0.03,{color:kc(-1)}),kMat));
  // Street circuits run on public roads: dashed lane lines stay painted on the straights.
  if(env.street){const dash=(i:number)=>{for(let q=-20;q<=20;q+=5)if(Math.abs(curv[(i+q+n)%n])>1/700)return null;return Math.floor(tr.s[i]/3)%4===0?wht:null};
   const lm=lam({vertexColors:true});for(const o of [-HALF/3,HALF/3])P.add(new THREE.Mesh(ribbon(tr,o-0.08,o+0.08,0.012,{color:dash}),lm))}
  // Start/finish line and gantry.
  const p0=tr.at(0),nx=-Math.sin(p0.h),ny=Math.cos(p0.h);
  const line=new THREE.Mesh(new THREE.PlaneGeometry(1.0,HALF*2),lam({color:0xffffff}));line.rotation.set(-Math.PI/2,0,p0.h);line.position.copy(W(p0.x,p0.y,p0.z+0.02));P.add(line);
  const gmat=lam({color:0x2b3138});
  for(const s of [-1,1]){const post=new THREE.Mesh(new THREE.BoxGeometry(0.6,9,0.6),gmat);post.position.copy(W(p0.x+nx*(HALF+2.5)*s,p0.y+ny*(HALF+2.5)*s,p0.z+4.5));P.add(post)}
  const beam=new THREE.Mesh(new THREE.BoxGeometry(1.2,1.6,HALF*2+5.6),gmat);beam.position.copy(W(p0.x,p0.y,p0.z+8.6));beam.rotation.y=p0.h;P.add(beam);
  const chk=document.createElement('canvas');chk.width=64;chk.height=8;const cx=chk.getContext('2d')!;for(let i=0;i<16;i++)for(let j=0;j<2;j++){cx.fillStyle=(i+j)%2?'#111':'#eee';cx.fillRect(i*4,j*4,4,4)}
  const ct=new THREE.CanvasTexture(chk);ct.magFilter=THREE.NearestFilter;const band=new THREE.Mesh(new THREE.PlaneGeometry(HALF*2+5,1.2),new THREE.MeshBasicMaterial({map:ct,side:THREE.DoubleSide}));
  band.position.copy(W(p0.x,p0.y,p0.z+8.6));band.rotation.y=p0.h+Math.PI/2;band.translateZ(0.62);P.add(band);
  // Pit lane: measured path (recorded mode) or drawn beside the outline (estimated; no cars are moved along it).
  let pit:{x:number;y:number;z:number}[]=[];
  if(info.track.pit?.length){pit=info.track.pit.map(([x,y])=>{const q=tr.nearest(x,y);return {x,y,z:tr.z[q.i]}})}
  else if(info.track.pit_frac){const {entry,exit}=info.track.pit_frac;const len=((exit-entry)%1+1)%1;const mid=tr.at((entry+len/2)*L);
   const side=((mid.x-(minx+maxx)/2)*-Math.sin(mid.h)+(mid.y-(miny+maxy)/2)*Math.cos(mid.h))>0?-1:1;
   for(let k=0;k<=120;k++){const t=k/120,d=(entry+len*t)*L,p=tr.at(d);const e=Math.min(1,t/.12,(1-t)/.12),s=e*e*(3-2*e);pit.push({x:p.x-Math.sin(p.h)*side*16*s,y:p.y+Math.cos(p.h)*side*16*s,z:p.z})}}
  if(pit.length>2)P.add(new THREE.Mesh(polyRibbon(pit,5,-0.01),lam({color:0x55585d,polygonOffset:true,polygonOffsetFactor:-1})));
  const nearPit=(x:number,y:number,r:number)=>pit.some(p=>(p.x-x)**2+(p.y-y)**2<r*r);
  // Barriers with posts every 6 m (they give the sense of speed), left out where the pit lane passes.
  // Street circuits: concrete walls a few metres from the asphalt with catch fences on top; elsewhere wide run-off.
  const bar=env.street?HALF+4:HALF+17;const barPos:number[]=[];const postM:THREE.Matrix4[]=[];const fence:number[]=[],fenceUv:number[]=[];
  for(const side of [1,-1]){for(let i=0;i<n;i+=1){const j=(i+1)%n;const o=side*bar;
   const ax=tr.x[i]-tr.ty[i]*o,ay=tr.y[i]+tr.tx[i]*o,bx=tr.x[j]-tr.ty[j]*o,by=tr.y[j]+tr.tx[j]*o;
   if(nearPit(ax,ay,16)||nearTrack(ax,ay).d<bar-3)continue;
   const a0=W(ax,ay,tr.z[i]-0.2),a1=W(ax,ay,tr.z[i]+1.1),b0=W(bx,by,tr.z[j]-0.2),b1=W(bx,by,tr.z[j]+1.1);
   for(const p of [a0,b0,b1,a0,b1,a1])barPos.push(p.x,p.y,p.z);
   if(env.street){const f0=W(ax,ay,tr.z[i]+1.1),f1=W(ax,ay,tr.z[i]+4.4),g0=W(bx,by,tr.z[j]+1.1),g1=W(bx,by,tr.z[j]+4.4);const u0=tr.s[i]/1.6,u1=u0+tr.length/n/1.6;
    for(const [p,u,v] of [[f0,u0,0],[g0,u1,0],[g1,u1,1],[f0,u0,0],[g1,u1,1],[f1,u0,1]] as [THREE.Vector3,number,number][]){fence.push(p.x,p.y,p.z);fenceUv.push(u,v)}}
   if(i%(env.street?2:3)===0){const back=env.street?0.25:1.2;postM.push(new THREE.Matrix4().makeTranslation(...W(ax-tr.ty[i]*side*back,ay+tr.tx[i]*side*back,tr.z[i]+2.2).toArray() as [number,number,number]))}}}
  const bg=new THREE.BufferGeometry();bg.setAttribute('position',new THREE.Float32BufferAttribute(barPos,3));bg.computeVertexNormals();
  P.add(new THREE.Mesh(bg,lam({color:env.street?0xd8dbde:0xc9ced3,side:THREE.DoubleSide})));
  if(fence.length){const c=document.createElement('canvas');c.width=c.height=32;const x=c.getContext('2d')!;x.strokeStyle='rgba(40,46,54,.9)';x.lineWidth=2;
   for(let k=-32;k<64;k+=8){x.beginPath();x.moveTo(k,0);x.lineTo(k+32,32);x.stroke();x.beginPath();x.moveTo(k+32,0);x.lineTo(k,32);x.stroke()}
   const ft=new THREE.CanvasTexture(c);ft.wrapS=ft.wrapT=THREE.RepeatWrapping;ft.repeat.set(1,6);ft.anisotropy=4;
   const fg=new THREE.BufferGeometry();fg.setAttribute('position',new THREE.Float32BufferAttribute(fence,3));fg.setAttribute('uv',new THREE.Float32BufferAttribute(fenceUv,2));fg.computeVertexNormals();
   P.add(new THREE.Mesh(fg,new THREE.MeshLambertMaterial({map:ft,transparent:true,alphaTest:0.2,side:THREE.DoubleSide,depthWrite:false})))}
  const posts=new THREE.InstancedMesh(new THREE.BoxGeometry(0.14,4.6,0.14),lam({color:0x3a4048}),postM.length);postM.forEach((m,i)=>posts.setMatrixAt(i,m));P.add(posts);
  // Floodlight poles (street circuits and night races): every ~45 m, alternating sides, lamps reaching over the track.
  if(env.street||env.night){const poleM:THREE.Matrix4[]=[],lampM:THREE.Matrix4[]=[];const lo=bar+(env.street?1.2:2);
   for(let i=0,k=0;i<n;i+=22,k++){const side=k%2?1:-1;const ax=tr.x[i]-tr.ty[i]*side*lo,ay=tr.y[i]+tr.tx[i]*side*lo;if(nearPit(ax,ay,12)||nearTrack(ax,ay).d<lo-3)continue;
    poleM.push(new THREE.Matrix4().makeTranslation(...W(ax,ay,tr.z[i]+6).toArray() as [number,number,number]));
    const lx=tr.x[i]-tr.ty[i]*side*(lo-2.2),ly=tr.y[i]+tr.tx[i]*side*(lo-2.2);
    lampM.push(new THREE.Matrix4().compose(W(lx,ly,tr.z[i]+12),new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),Math.atan2(tr.ty[i],tr.tx[i])),new THREE.Vector3(1,1,1)))}
   const poles=new THREE.InstancedMesh(new THREE.BoxGeometry(0.3,12,0.3),lam({color:0x4a5058}),poleM.length);poleM.forEach((m,i)=>poles.setMatrixAt(i,m));P.add(poles);
   const lamps=new THREE.InstancedMesh(new THREE.BoxGeometry(1.0,0.3,4.6),new THREE.MeshBasicMaterial({color:env.night?0xfff6e0:0xcfd4da}),lampM.length);lampM.forEach((m,i)=>lamps.setMatrixAt(i,m));P.add(lamps)}
  // Grandstands along the main straight, on the side away from the pit lane.
  const standSide=pit.length&&pit[Math.floor(pit.length/2)]?(()=>{const p=pit[Math.floor(pit.length/2)];const q=tr.nearest(p.x,p.y);return ((p.x-tr.x[q.i])*-tr.ty[q.i]+(p.y-tr.y[q.i])*tr.tx[q.i])>0?-1:1})():-1;
  const sMat=lam({color:0x4b5463}),seat=lam({color:0x34507a});
  for(let d=-260;d<=360;d+=44){const p=tr.at((d+L)%L);const o=standSide*(HALF+30);const cx2=p.x-Math.sin(p.h)*o,cy2=p.y+Math.cos(p.h)*o;
   if(nearTrack(cx2,cy2).d<HALF+20||nearPit(cx2,cy2,14))continue;
   for(let k=0;k<3;k++){const b=new THREE.Mesh(new THREE.BoxGeometry(40,3.2+k*3.2,8),k?seat:sMat);const off=standSide*(k*7);
    b.position.copy(W(cx2-Math.sin(p.h)*off,cy2+Math.cos(p.h)*off,p.z+1.6*(k+1)));b.rotation.y=p.h;P.add(b)}
   const roof=new THREE.Mesh(new THREE.BoxGeometry(42,0.5,24),sMat);roof.position.copy(W(cx2-Math.sin(p.h)*standSide*8,cy2+Math.cos(p.h)*standSide*8,p.z+13));roof.rotation.y=p.h;P.add(roof)}
  // Braking boards (3-2-1) before the slow corners.
  const boardTex=[3,2,1].map(k=>{const c=document.createElement('canvas');c.width=64;c.height=96;const x=c.getContext('2d')!;x.fillStyle='#f4f4f2';x.fillRect(0,0,64,96);
   x.fillStyle='#1b1f24';for(let s=0;s<k;s++)x.fillRect(10,14+s*26,44,14);const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;return t});
  const sp=tr.speed;for(let i=0;i<n;i++){const b=(i+n-60)%n;if(sp[b]-sp[i]>0.32&&sp[i]<=Math.min(sp[(i+n-1)%n],sp[(i+1)%n])){
   let start=b;for(let k=0;k<160;k++){const q=(i-k+n)%n;if(sp[(q+n-1)%n]<=sp[q]+0.002){start=q;break}}
   const side=curv[i]>0?-1:1;
   [150,100,50].forEach((m,k)=>{const p=tr.at(tr.s[start]-m);const o=side*(HALF+6);const bd=new THREE.Mesh(new THREE.PlaneGeometry(1.4,2.1),lam({map:boardTex[k],side:THREE.DoubleSide}));
    bd.position.copy(W(p.x-Math.sin(p.h)*o,p.y+Math.cos(p.h)*o,p.z+1.3));bd.rotation.y=p.h+Math.PI/2;P.add(bd)})}}
  // Trees and a distant skyline for depth (generic, procedural).
  const r=rng(Math.round(L));const treeM:THREE.Matrix4[]=[],bldM:THREE.Matrix4[]=[];
  for(let k=0;k<2600&&treeM.length<700&&!env.street;k++){const x=minx-300+r()*(maxx-minx+600),y=miny-300+r()*(maxy-miny+600);const q=nearTrack(x,y);if(q.d<HALF+42||q.d>260||nearPit(x,y,25))continue;
   if(this.sites.some(c=>(c.pos.x-x)**2+(c.pos.z+y)**2<110*110))continue;   // keep trackside camera views clear
   const s=0.8+r()*0.9;treeM.push(new THREE.Matrix4().compose(W(x,y,q.z-0.6+5*s),new THREE.Quaternion(),new THREE.Vector3(s,s,s)))}
  // Street circuits: hotels and casinos right behind the fences.
  if(env.street)for(let k=0;k<5000&&bldM.length<480;k++){const x=minx-250+r()*(maxx-minx+500),y=miny-250+r()*(maxy-miny+500);const q=nearTrack(x,y);if(q.d<HALF+38||q.d>360||nearPit(x,y,40))continue;
   if(this.sites.some(c=>(c.pos.x-x)**2+(c.pos.z+y)**2<70*70))continue;
   const h=14+r()*r()*150,w=16+r()*34;bldM.push(new THREE.Matrix4().compose(W(x,y,q.low-1+h/2),new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),r()*3),new THREE.Vector3(w,h,w*(.6+r()*.8))))}
  for(let k=0;k<3000&&bldM.length<(env.street?900:420);k++){const x=minx-pad+r()*(gw),y=miny-pad+r()*(gh);const q=nearTrack(x,y);if(q.d<420)continue;
   const h=12+r()*r()*90,w=18+r()*30;bldM.push(new THREE.Matrix4().compose(W(x,y,zmean-1+h/2),new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),r()*3),new THREE.Vector3(w,h,w*(.6+r()*.8))))}
  const trees=new THREE.InstancedMesh(new THREE.ConeGeometry(3.4,10,7),lam({color:0x2f4a2a}),treeM.length);treeM.forEach((m,i)=>trees.setMatrixAt(i,m));P.add(trees);
  // Facades with windows; lit at night (generic, no real buildings or signs).
  const wc=document.createElement('canvas');wc.width=64;wc.height=128;const wx=wc.getContext('2d')!;const wr=rng(7);
  wx.fillStyle=env.night?'#161b25':'#9aa3ad';wx.fillRect(0,0,64,128);
  for(let yy=4;yy<124;yy+=8)for(let xx=4;xx<60;xx+=8){const lit=wr();wx.fillStyle=env.night?(lit<.45?['#ffd9a0','#cfe3ff','#ffc28a','#f6a6ff'][Math.floor(wr()*4)]:'#0d1118'):(lit<.5?'#5d6874':'#7c8792');wx.fillRect(xx,yy,4,5)}
  const wt=new THREE.CanvasTexture(wc);wt.colorSpace=THREE.SRGBColorSpace;wt.wrapS=wt.wrapT=THREE.RepeatWrapping;wt.repeat.set(1,3);
  const blds=new THREE.InstancedMesh(new THREE.BoxGeometry(1,1,1),lam(env.night?{map:wt,emissiveMap:wt,emissive:new THREE.Color(0xffffff),emissiveIntensity:0.85}:{map:wt}),bldM.length);bldM.forEach((m,i)=>blds.setMatrixAt(i,m));this.far.add(blds);
 }

 /** Venue scenes: trackside cameras just behind the debris fence on the outside of each bend (or the grandstand side of
  * the straight), raised above the fence, moved until nothing in the venue blocks the view of the track in front. */
 venueSites(tr:TrackCurve,v:Venue):Site[]{
  const out:Site[]=[];const n=tr.n,L=tr.length;const count=Math.max(8,Math.round(L/280));const ray=new THREE.Raycaster();
  const meshes:THREE.Object3D[]=[];const boxes:THREE.Box3[]=[];
  v.root.traverse(o=>{const m=o as THREE.Mesh;if(!m.isMesh||/fence|horizon|fence_posts|brake/.test(o.name))return;meshes.push(o);   // floodlight poles count (instanced)
   if(/^(grandstand|pit_building|building|stand|bleachers|gantry)/.test(o.name)){const bx=new THREE.Box3().setFromObject(o);if(bx.getSize(new THREE.Vector3()).length()<900)boxes.push(bx.expandByScalar(4))}});
  this.occluders=meshes;
  const poles=v.manifest.instances.poles.map(q=>v.toScene(q[0],q[1]));   // floodlight poles: keep 9 m clear of the lens
  for(let k=0;k<count;k++){const d=(k+0.5)*L/count;const i=Math.floor(d/L*n)%n;
   const a=(i-20+n)%n,b=(i+20)%n;let dh=Math.atan2(tr.ty[b],tr.tx[b])-Math.atan2(tr.ty[a],tr.tx[a]);dh=(dh+Math.PI*3)%(Math.PI*2)-Math.PI;
   const pref=Math.abs(dh)>0.12?-Math.sign(dh):1;let best:THREE.Vector3|null=null;
   const tgt=W(tr.x[(i+15)%n],tr.y[(i+15)%n],tr.z[(i+15)%n]+0.8);
   for(const side of [pref,-pref])for(const off of [14,20,28,38])for(const h of [7,11,16]){if(best)break;
    const x=tr.x[i]-tr.ty[i]*side*off,y=tr.y[i]+tr.tx[i]*side*off;if(tr.nearest(x,y).dist<off-3)continue;
    const p=W(x,y,v.heightAt(x,y)+h);let clear=!boxes.some(bx=>bx.containsPoint(p))&&!poles.some(q=>(q.x-x)**2+(q.y-y)**2<9*9);
    // sight lines to the track 50 m either side and straight across, and nothing within 4 m of the lens (roof masts)
    for(const q of [(i-25+n)%n,(i+15)%n,(i+40)%n]){const t2=W(tr.x[q],tr.y[q],tr.z[q]+0.8);const dir=t2.sub(p);const len=dir.length();ray.set(p,dir.normalize());ray.far=len*0.97;if(ray.intersectObjects(meshes,false).length){clear=false;break}}
    for(let a2=0;clear&&a2<8;a2++){ray.set(p,new THREE.Vector3(Math.cos(a2*Math.PI/4),0,Math.sin(a2*Math.PI/4)));ray.far=4;if(ray.intersectObjects(meshes,false).length)clear=false}
    if(clear)best=p}
   out.push({i,d:tr.s[i],pos:best||W(tr.x[i],tr.y[i],tr.z[i]+30),name:`CAM ${k+1}`})}
  return out}

 /** Fixed trackside camera positions, every ~300 m, on the outside of the bends, raised a few metres. */
 buildSites(tr:TrackCurve):Site[]{
  const out:Site[]=[];const n=tr.n,L=tr.length;const count=Math.max(8,Math.round(L/300));const r=rng(Math.round(L*3));
  for(let k=0;k<count;k++){const d=(k+0.5)*L/count;const i=Math.floor(d/L*n)%n;
   const a=(i-20+n)%n,b=(i+20)%n;let dh=Math.atan2(tr.ty[b],tr.tx[b])-Math.atan2(tr.ty[a],tr.tx[a]);dh=(dh+Math.PI*3)%(Math.PI*2)-Math.PI;
   let side=Math.abs(dh)>0.12?-Math.sign(dh):(k%2?1:-1);let off=this.env.street?HALF+7+r()*6:HALF+22+r()*18,pos:THREE.Vector3|null=null;   // street: platforms just behind the wall, above the fence
   for(let t=0;t<4&&!pos;t++){const x=tr.x[i]-tr.ty[i]*side*off,y=tr.y[i]+tr.tx[i]*side*off;const q=tr.nearest(x,y);
    if(q.dist>=off-4)pos=W(x,y,tr.z[i]+(this.env.street?8.5+r()*6:5+r()*8));else if(t===1){side=-side}else off*=0.75}
   if(!pos)pos=W(tr.x[i]-tr.ty[i]*side*(HALF+12),tr.y[i]+tr.tx[i]*side*(HALF+12),tr.z[i]+6);
   out.push({i,d:tr.s[i],pos,name:`CAM ${k+1}`})}
  return out}

 // ------------------------------------------------------------- data
 display(){return this.clock.now(performance.now())}

 /** Keeps a short buffer of samples around the displayed instant (fetches ahead, refreshes live data). */
 pump(){
  if(!this.info?.ok||!this.feed||this.inflight||!this.clock.valid)return;
  const D=this.display();if(!Number.isFinite(D))return;
  const sp=this.clock.paused?1:Math.max(1,this.clock.speed),now=performance.now();
  const b=this.buf;const live=this.feed.mode==='follow';
  const need=!b||D<b.t0+1||D>b.t1-Math.max(4,3*sp)||(live&&now-this.lastFetch>1000);
  if(!need)return;
  const t0=D-Math.max(3,2*sp),t1=D+Math.min(600,Math.max(14,10*sp));
  const step=this.info.source==='estimated'?(sp>8?0.5:0.25):0.25;
  const gen=this.gen,ctrl=new AbortController();this.inflight=ctrl;this.lastFetch=now;
  fetchSamples(this.samplesBase,t0,t1,this.source,step,ctrl.signal).then(nb=>{
   if(gen!==this.gen||this.disposed)return;
   if(this.info&&nb.key!==this.info.key){this.fetchErr='The position source changed. Reloading the scene…';return}
   // Live data replaces extrapolated samples: blend the difference out instead of jumping (estimated mode).
   if(this.buf&&nb.source==='estimated'){const D2=this.display(),w=performance.now();
    for(const num of nb.est.keys()){const a=this.buf.estAt(num,D2),c=nb.estAt(num,D2);if(a&&c){const v=a.s-c.s;if(Math.abs(v)>0.3&&Math.abs(v)<60)this.correction.set(num,{v,at:w})}}}
   this.prev=this.buf;this.buf=nb;this.fetchErr=''})
  .catch(e=>{if(gen===this.gen&&(e as Error).name!=='AbortError')this.fetchErr=(e as Error).message})
  .finally(()=>{if(this.inflight===ctrl)this.inflight=null})}

 // ------------------------------------------------------------- frame
 frame(){
  const tr=this.track,info=this.info;const now=performance.now();
  if(!tr||!info){this.renderer.render(this.scene,this.camera);return}
  const D=this.display();
  const buf=this.buf&&Number.isFinite(D)&&this.buf.covers(D)?this.buf:this.prev&&this.prev.covers(D)?this.prev:null;
  const all=buf?poses(buf,tr,D,this.hints,this.headings,this.correction,now):new Map<string,Pose>();
  // Selected driver: the viewer's pick, else the leader at this instant.
  let sel=this.focus,auto=false;
  if(!sel||!info.drivers[sel]){auto=true;let best=99;if(buf||this.external)for(const num of Object.keys(info.drivers)){const t=this.timingOf(num,D,buf);if(t?.pos&&t.pos<best&&!t.out){best=t.pos;sel=num}}}
  for(const [num,car] of this.cars){const p=all.get(num);const t=this.timingOf(num,D,buf);
   if(!p||t?.retired&&p.flag==='stale'){car.group.visible=false;continue}
   car.group.visible=true;
   const vz=this.venue?this.venue.heightAt(p.x,p.y,num):null;
   car.group.position.copy(W(p.x,p.y,vz??p.z));
   const ahead=tr.at(p.d+3),behind=tr.at(p.d-3);
   let pitch=p.offTrack?0:Math.atan2(ahead.z-behind.z,6);
   if(this.venue&&!p.offTrack){const fx=Math.cos(p.h)*3,fy=Math.sin(p.h)*3;pitch=Math.atan2(this.venue.heightAt(p.x+fx,p.y+fy)-this.venue.heightAt(p.x-fx,p.y-fy),6)}
   car.group.rotation.set(0,p.h,pitch);
   if(isDetailed(car)){car.wheels.forEach((w,k)=>{w.rotation.z=-(p.d%2000)/(car.radii[k]||0.355)});
    // steer with the circuit's curvature at this point (the feed has no steering data)
    const a2=tr.at(p.d+6),b2=tr.at(p.d-6);let dh=a2.h-b2.h;dh=(dh+Math.PI*3)%(Math.PI*2)-Math.PI;const st=THREE.MathUtils.clamp(Math.atan(3.4*dh/12)*1.15,-0.35,0.35);
    for(const s of car.steer)s.rotation.y=st;
    const dist=car.group.position.distanceTo(this.camera.position);const hi=dist<70||(num===sel&&this.mode!=='broadcast');
    if(car.lod[0])car.lod[0].visible=hi;if(car.lod[1])car.lod[1].visible=!hi}
   else{const spin=-(p.d%1000)/0.36;for(const w of car.wheels)w.rotation.z=spin}
   const own=num===sel&&this.mode!=='broadcast';car.helmet.visible=!(own&&this.mode==='cockpit');car.label.visible=!own;
   const tag=`${t?.pos??''}|${p.flag}`;if(this.labels.get(num)!==tag){this.labels.set(num,tag);const m=info.drivers[num];
    (car.label.material as THREE.SpriteMaterial).map?.dispose();(car.label.material as THREE.SpriteMaterial).map=labelTexture(m.code,m.color,t?.pos);
    (car.label.material as THREE.SpriteMaterial).opacity=p.flag==='stale'?0.45:1;(car.label.material as THREE.SpriteMaterial).needsUpdate=true}
   car.group.updateMatrixWorld()}
  // Estimated positions have no lateral information: cars closer than a car length along the lap can't be
  // separated honestly, so they are drawn see-through instead of being given an invented side-by-side line.
  const ghosts=new Set<string>();
  if(info.source==='estimated'){const list=[...all.values()].sort((a,b)=>a.d-b.d);
   for(let i=0;i<list.length;i++){const a=list[i],b=list[(i+1)%list.length];if(a===b)continue;const gap=((b.d-a.d)%tr.length+tr.length)%tr.length;if(gap<6.5){ghosts.add(a.num);ghosts.add(b.num)}}}
  for(const [num,car] of this.cars){const g=ghosts.has(num)&&!(num===sel&&this.mode!=='broadcast');if(g!==car.ghost){car.ghost=g;
   for(const m of car.mats){m.transparent=g;m.opacity=g?0.32:1;m.depthWrite=!g;m.needsUpdate=true}}}
  this.ghosted=sel?ghosts.has(sel):false;
  const me=sel?all.get(sel):undefined;
  if(me)this.lastSel=me;
  this.placeCamera(me||null,all,sel,tr,now);
  if(this.venue){this.venue.updateLod(this.camera.position);
   const f=me?W(me.x,me.y,this.venue.heightAt(me.x,me.y,me.num)):this.camera.position.clone();
   this.key.target.position.copy(f);this.key.position.copy(f).add(new THREE.Vector3(-34,62,22));this.key.target.updateMatrixWorld()}
  const dtf=now-this.lastFrame;this.lastFrame=now;if(dtf>0&&dtf<1000){this.frameTimes.push(dtf);if(this.frameTimes.length>600)this.frameTimes.shift()}
  for(const [,car] of this.cars)if(car.group.visible&&car.label.visible){const dist=car.group.position.distanceTo(this.camera.position);car.label.visible=dist<520;
   // Roughly constant size on screen: small on a car just ahead, readable far away.
   const s=THREE.MathUtils.clamp(dist*Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2))/(this.mode==='broadcast'?14:16),0.2,8);car.label.scale.set(2.6*s,0.98*s,1);
   car.label.position.y=1.3+1.0*s}
  this.renderer.render(this.scene,this.camera);
  if(now-this.lastHud>200){this.lastHud=now;this.emitHud(D,buf,all,sel,auto,tr)}
 }

 placeCamera(me:Pose|null,all:Map<string,Pose>,sel:string|null,tr:TrackCurve,now:number){
  const cam=this.camera;const dt=1/60;
  if(!me){const p=this.lastSel;if(!p&&!this.camReady){const c=tr.at(0);cam.position.copy(W(c.x,c.y,c.z+60));cam.lookAt(W(c.x+Math.cos(c.h)*120,c.y+Math.sin(c.h)*120,c.z));this.camReady=true}return}
  if(this.mode==='broadcast'){this.broadcastCam(me,all,tr,now);return}
  const car=this.cars.get(me.num)!;const cockpit=this.mode==='cockpit';
  const mount=isDetailed(car)?(cockpit?car.mounts.cockpit:car.mounts.pod).clone():cockpit?new THREE.Vector3(0.0,0.87,0):new THREE.Vector3(-0.74,1.31,0);
  const eye=car.group.localToWorld(mount);
  const ahead=tr.at(me.d+(cockpit?22:35));const fwd=new THREE.Vector3(Math.cos(me.h),0,-Math.sin(me.h));
  const toPath=W(ahead.x,ahead.y,ahead.z).sub(eye).setY(0).normalize();
  const want=fwd.clone().lerp(me.offTrack?fwd:toPath,cockpit?0.45:0.3).normalize();
  if(!this.camReady){this.camDir.copy(want);this.camReady=true}else this.camDir.lerp(want,1-Math.exp(-dt/(cockpit?0.14:0.09))).normalize();
  const fov=cockpit?(isDetailed(car)?54:64):46;if(cam.fov!==fov||cam.near!==0.02){cam.fov=fov;cam.near=0.02;cam.updateProjectionMatrix()}
  cam.position.copy(eye);
  const dist=cockpit?25:35;const tgt=eye.clone().add(this.camDir.clone().multiplyScalar(dist));tgt.y=ahead.z+(cockpit?0.15:0.05);
  if(isDetailed(car)&&!me.offTrack){const road=eye.y-mount.y;tgt.y=cockpit?road+mount.y-dist*Math.tan(THREE.MathUtils.degToRad(3.5)):road+mount.y-dist*Math.tan(THREE.MathUtils.degToRad(6.5))}   // T-cam and helmet pitch (from onboard footage)
  if(me.offTrack)tgt.y=eye.y-(cockpit?0.3:0.9);
  cam.lookAt(tgt);
 }

 broadcastCam(me:Pose,all:Map<string,Pose>,tr:TrackCurve,now:number){
  const cam=this.camera,L=tr.length,sites=this.sites;if(!sites.length)return;
  const rel=(s:Site)=>{let x=s.d-me.d;if(x>L/2)x-=L;if(x<-L/2)x+=L;return x};   // camera position relative to the car along the lap
  const inWin=(s:Site)=>{const x=rel(s);return x>=-120&&x<=230};
  const pick=()=>{let best=-1,score=-Infinity;sites.forEach((s,i)=>{if(!inWin(s))return;const x=rel(s);const sc=x+120;if(sc>score){score=sc;best=i}});
   if(best<0){let bd=Infinity;sites.forEach((s,i)=>{const x=Math.abs(rel(s));if(x<bd){bd=x;best=i}})}return best};
  // Cut when the driver leaves this camera's stretch, and never sooner than ~3 s after the last cut unless they are gone.
  let cut=false;
  if(this.site<0||!sites[this.site]){this.site=pick();cut=true}
  else{const s=sites[this.site];const x=rel(s);const out=!inWin(s);if(out||(x<-90&&now-this.cutAt>3000)){const nx=pick();if(nx!==this.site){this.site=nx;cut=true}}}
  // Venue scenes: never stay on a camera whose view of the car is blocked (stands, poles, the gantry).
  if(this.venue&&this.occluders.length&&(cut||now-this.occCheck>500)){this.occCheck=now;
   const blocked=(k:number)=>{const p=sites[k].pos,t=W(me.x,me.y,me.z+0.7);const d=t.clone().sub(p);const len=d.length();this.ray.set(p,d.normalize());this.ray.far=len-3;return this.ray.intersectObjects(this.occluders,false).length>0};
   if(blocked(this.site)){const order=sites.map((s,k)=>k).filter(k=>k!==this.site&&inWin(sites[k])).sort((a,b)=>rel(sites[b])-rel(sites[a]));
    const alt=order.find(k=>!blocked(k));if(alt!==undefined){this.site=alt;cut=true}}}
  if(cut){this.cutAt=now;this.lookReady=false}
  const site=sites[this.site];
  // Battle: another car physically close on track fits naturally in the same frame.
  const nb=neighbours(all,me.num,L);const close=[nb.ahead,nb.behind].filter(Boolean).sort((a,b)=>a!.m-b!.m)[0];
  if(this.battle){const still=[nb.ahead,nb.behind].find(q=>q&&q.num===this.battle&&q.m<65);if(!still)this.battle=null}
  if(!this.battle&&close&&close.m<40)this.battle=close.num;
  const meW=W(me.x,me.y,me.z+0.6);let target=meW.clone().add(new THREE.Vector3(Math.cos(me.h),0,-Math.sin(me.h)).multiplyScalar(Math.min(6,me.speed*0.08)));let span=7;
  const other=this.battle?all.get(this.battle):null;
  if(other){const oW=W(other.x,other.y,other.z+0.6);target=meW.clone().add(oW).multiplyScalar(0.5);span=meW.distanceTo(oW)+9}
  const dt=1/60;if(!this.lookReady){this.look.copy(target);this.lookReady=true}else this.look.lerp(target,1-Math.exp(-dt/0.22));
  cam.position.copy(site.pos);cam.lookAt(this.look);
  const dist=site.pos.distanceTo(this.look);const fill=0.42;const hHalf=Math.atan(span/(2*dist*fill));
  const v=THREE.MathUtils.clamp(2*THREE.MathUtils.radToDeg(Math.atan(Math.tan(hHalf)/cam.aspect)),2.5,42);
  this.fov=cut?v:this.fov+(v-this.fov)*(1-Math.exp(-dt/0.45));
  if(Math.abs(cam.fov-this.fov)>0.01||cam.near!==0.5){cam.fov=this.fov;cam.near=0.5;cam.updateProjectionMatrix()}
 }

 emitHud(D:number,buf:Buffer|null,all:Map<string,Pose>,sel:string|null,auto:boolean,tr:TrackCurve){
  const info=this.info!;const m=sel?info.drivers[sel]:null;const p=sel?all.get(sel):undefined;
  const nb=sel?neighbours(all,sel,tr.length):{ahead:null,behind:null};
  const nm=(q:{num:string;m:number}|null)=>q?{code:info.drivers[q.num]?.code||q.num,color:info.drivers[q.num]?.color||'#888',m:q.m}:null;
  let onTrack=0;for(const q of all.values())if(!q.offTrack)onTrack++;
  this.onHud({elapsed:Number.isFinite(D)&&this.feed?.start?D-this.feed.start:null,utc:Number.isFinite(D)?D:null,num:sel,auto,code:m?.code||'',name:m?.name||'',team:m?.team||'',color:m?.color||'#62d7da',
   timing:sel?this.timingOf(sel,D,buf):null,totalLaps:info.total_laps,ahead:nm(nb.ahead),behind:nm(nb.behind),flag:p?p.flag:'none',
   cam:this.mode==='broadcast'&&this.site>=0?this.sites[this.site]?.name||'':'',battle:this.mode==='broadcast'&&this.battle?info.drivers[this.battle]?.code||null:null,
   buffering:!buf,error:this.fetchErr,onTrack,ghosted:this.ghosted,venue:this.venueState,
   models:{count:[...this.cars.values()].filter(isDetailed).length,preview:this.preview,previewAvailable:previewAvailable(Object.values(info.drivers).map(d=>d.team),info.session?.year),
    labels:[...new Set([...this.cars.values()].filter(isDetailed).map(c=>(c as DetailedCar).model))]}});
 }
}
