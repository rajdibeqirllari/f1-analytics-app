/** Detailed venue models for the 3D Broadcast (first one: Lusail). Loaded only when the session's meeting matches.
 *
 * Each venue ships a Draco GLB built in Blender (scripts/qatar/build_lusail_blend.py) and a manifest with its
 * centreline, edges, landmarks and instanced objects. The GLB is authored in the F1 position frame (OpenF1/FastF1
 * x, y, z in metres) minus `origin`; scenes whose payload carries `track.frame` (that frame minus an offset) get an
 * exact placement, others a rigid fit to the scene's centreline. Either way the fit is checked against the scene before
 * the venue replaces the procedural circuit: a venue that does not line up is not shown. */
import * as THREE from 'three';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';
import {DRACOLoader} from 'three/examples/jsm/loaders/DRACOLoader.js';
import type {TrackCurve} from './data';

type Manifest={version:number;venue:string;name:string;match:string[];glb:string;origin:[number,number];z_offset:number;length:number;step:number;
 centre:{x:number[];y:number[];z:number[]};edges:{left:number[];right:number[]};
 landmarks:{control_line:number;start_line:number;corners:{n:number;station:number;dir:string}[];approx:Record<string,number|string>};
 instances:{poles:number[][];boards:number[][];posts?:number[][]};provenance:Record<string,string[]>};

const VENUES:{key:string;re:RegExp;base:string}[]=[{key:'lusail',re:/qatar|lusail|losail/,base:'/venues/lusail/'}];

export function venueKey(meeting:string){const m=meeting.normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();return VENUES.find(v=>v.re.test(m))?.key||null}

let draco:DRACOLoader|null=null;
export function gltfLoader(){const l=new GLTFLoader();if(!draco){draco=new DRACOLoader();draco.setDecoderPath('/draco/');draco.setDecoderConfig({type:'wasm'})}l.setDRACOLoader(draco);return l}

const W=(x:number,y:number,z:number)=>new THREE.Vector3(x,z,-y);

export type Alignment={mode:'exact'|'fit';dx:number;dy:number;dz:number;rot:number;median:number;p95:number;
 landmarks:{name:string;err:number}[];inside:number|null};

export class Venue{
 key:string;manifest:Manifest;root=new THREE.Group();scene:THREE.Group;align:Alignment|null=null;
 cx:Float64Array;cy:Float64Array;cz:Float64Array;n:number;
 detail:{obj:THREE.Object3D;c:THREE.Vector3;r:number;max:number}[]=[];
 bytes=0;loadMs=0;
 private hint=new Map<string,number>();
 constructor(key:string,manifest:Manifest,scene:THREE.Group){this.key=key;this.manifest=manifest;this.scene=scene;
  const m=manifest.centre;this.n=m.x.length;this.cx=Float64Array.from(m.x);this.cy=Float64Array.from(m.y);this.cz=Float64Array.from(m.z);
  this.root.name='venue:'+key;this.root.add(scene)}

 /** Asset (x, y) -> scene (x, y). */
 toScene(x:number,y:number){const a=this.align!;const c=Math.cos(a.rot),s=Math.sin(a.rot);return {x:c*x-s*y+a.dx,y:s*x+c*y+a.dy}}
 toAsset(x:number,y:number){const a=this.align!;const c=Math.cos(a.rot),s=Math.sin(a.rot);const px=x-a.dx,py=y-a.dy;return {x:c*px+s*py,y:-s*px+c*py}}

 /** Nearest asset station to a scene point (searched around the last hit first). */
 nearest(x:number,y:number,key=''){const p=this.toAsset(x,y);const n=this.n;let best=-1,bd=Infinity;const h=key?this.hint.get(key)??-1:-1;
  const scan=(a:number,b:number)=>{for(let q=a;q<=b;q++){const i=((q%n)+n)%n;const d=(this.cx[i]-p.x)**2+(this.cy[i]-p.y)**2;if(d<bd){bd=d;best=i}}};
  if(h>=0)scan(h-40,h+40);if(h<0||bd>20*20)scan(0,n-1);if(key)this.hint.set(key,best);
  // signed lateral offset (left positive) for the edge check
  const j=(best+1)%n,k=(best-1+n)%n;const tx=this.cx[j]-this.cx[k],ty=this.cy[j]-this.cy[k],l=Math.hypot(tx,ty)||1;
  const lat=((p.x-this.cx[best])*-ty+(p.y-this.cy[best])*tx)/l;return {i:best,dist:Math.sqrt(bd),lat}}

 /** Road surface height (scene z) under a scene point: the asphalt is flat across, so the station height. */
 heightAt(x:number,y:number,key=''){const q=this.nearest(x,y,key);return this.cz[q.i]+this.align!.dz}

 /** Places the venue in the scene: exact from the payload's frame offset when there is one, else a rigid fit; then
  * checks it against the scene's centreline and landmarks. Returns false (and the reason) when it does not line up. */
 place(track:TrackCurve,frame:number[]|null|undefined):{ok:boolean;why:string}{
  const m=this.manifest;const ox=m.origin[0],oy=m.origin[1];
  let a:Alignment;
  if(frame&&frame.length===3&&frame.every(Number.isFinite)&&Number.isFinite(m.z_offset))a={mode:'exact',dx:ox-frame[0],dy:oy-frame[1],dz:m.z_offset-frame[2],rot:0,median:0,p95:0,landmarks:[],inside:null};
  else a=this.fit(track);
  this.align=a;
  // Check: scene centreline points against the asset centreline (the scene's curve is a driven lap for recorded
  // scenes, so a few metres apart in corners is expected; tens of metres means the wrong frame).
  const d:number[]=[];for(let i=0;i<track.n;i+=5){d.push(this.nearest(track.x[i],track.y[i]).dist)}
  d.sort((p,q)=>p-q);a.median=d[Math.floor(d.length/2)];a.p95=d[Math.floor(d.length*.95)];
  // Landmarks: where the scene's lap distance says the start line / corners are vs the asset's own stations.
  const sc=(m.length/track.length);const L=track.length;
  const marks:[string,number][]=[['control line',0],['start line',m.landmarks.start_line],...m.landmarks.corners.filter(c=>[1,12,13,14,16].includes(c.n)).map(c=>[`T${c.n}`,c.station] as [string,number])];
  // match by geometry: nearest scene-curve point to the asset landmark (independent of where each lap starts)
  a.landmarks=marks.map(([name,st])=>{const i=Math.round(st/m.step)%this.n;const p=this.toScene(this.cx[i],this.cy[i]);
   let bd=Infinity;for(let k=0;k<track.n;k++){const q=(track.x[k]-p.x)**2+(track.y[k]-p.y)**2;if(q<bd)bd=q}return {name,err:Math.round(Math.sqrt(bd)*100)/100}});
  void sc;void L;
  if(a.median>8)return {ok:false,why:`The ${m.name} model is ${a.median.toFixed(1)} m away from this session's circuit, so it is not shown.`};
  this.root.position.copy(W(a.dx,a.dy,a.dz));this.root.rotation.set(0,a.rot,0);this.root.updateMatrixWorld(true);
  for(const d2 of this.detail)d2.c.copy(d2.obj.getWorldPosition(new THREE.Vector3()));
  return {ok:true,why:''}}

 /** Rigid 2D fit (rotation + translation) of the asset centreline to the scene curve: ICP from a coarse search. */
 fit(track:TrackCurve):Alignment{
  const src:number[][]=[];for(let i=0;i<this.n;i+=5)src.push([this.cx[i],this.cy[i]]);
  const tgt:number[][]=[];for(let i=0;i<track.n;i+=2)tgt.push([track.x[i],track.y[i]]);
  const mean=(p:number[][])=>{let x=0,y=0;for(const q of p){x+=q[0];y+=q[1]}return [x/p.length,y/p.length]};
  const ms=mean(src),mt=mean(tgt);
  const nn=(x:number,y:number)=>{let b=0,bd=Infinity;for(let k=0;k<tgt.length;k++){const d=(tgt[k][0]-x)**2+(tgt[k][1]-y)**2;if(d<bd){bd=d;b=k}}return [b,bd] as const};
  let best={rot:0,dx:0,dy:0,err:Infinity};
  for(let deg=0;deg<360;deg+=10){let rot=deg*Math.PI/180,dx=mt[0]-(Math.cos(rot)*ms[0]-Math.sin(rot)*ms[1]),dy=mt[1]-(Math.sin(rot)*ms[0]+Math.cos(rot)*ms[1]);
   for(let it=0;it<(deg%30?0:12)+3;it++){const c=Math.cos(rot),s=Math.sin(rot);let sxx=0,sxy=0,syx=0,syy=0,ax=0,ay=0,bx=0,by=0,cnt=0;const pairs:[number[],number[]][]=[];
    for(const p of src){const x=c*p[0]-s*p[1]+dx,y=s*p[0]+c*p[1]+dy;const [k,d]=nn(x,y);if(d<60*60){pairs.push([p,tgt[k]]);ax+=p[0];ay+=p[1];bx+=tgt[k][0];by+=tgt[k][1];cnt++}}
    if(cnt<10)break;ax/=cnt;ay/=cnt;bx/=cnt;by/=cnt;
    for(const [p,q] of pairs){const u=p[0]-ax,v=p[1]-ay,U=q[0]-bx,V=q[1]-by;sxx+=u*U;sxy+=u*V;syx+=v*U;syy+=v*V}
    rot=Math.atan2(sxy-syx,sxx+syy);const c2=Math.cos(rot),s2=Math.sin(rot);dx=bx-(c2*ax-s2*ay);dy=by-(s2*ax+c2*ay)}
   const c=Math.cos(rot),s=Math.sin(rot);let e=0;for(let k=0;k<src.length;k+=3){const p=src[k];e+=Math.sqrt(nn(c*p[0]-s*p[1]+dx,s*p[0]+c*p[1]+dy)[1])}
   if(e<best.err)best={rot,dx,dy,err:e}}
  // height: scene curve vs asset heights at matched points
  this.align={mode:'fit',dx:best.dx,dy:best.dy,dz:0,rot:best.rot,median:0,p95:0,landmarks:[],inside:null};
  let dzs:number[]=[];for(let i=0;i<track.n;i+=20){const q=this.nearest(track.x[i],track.y[i]);dzs.push(track.z[i]-this.cz[q.i])}
  dzs.sort((p,q)=>p-q);this.align.dz=dzs[Math.floor(dzs.length/2)]||0;
  return this.align}

 /** Shows fine detail (fences, boards, kerb ribs) only near the camera. */
 updateLod(cam:THREE.Vector3){for(const d of this.detail){const v=d.c.distanceTo(cam)-d.r<d.max;if(d.obj.visible!==v)d.obj.visible=v}}

 dispose(){this.root.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose?.();const mat=(m as any).material;if(mat)for(const x of Array.isArray(mat)?mat:[mat]){for(const k of ['map','normalMap','roughnessMap','metalnessMap','emissiveMap','alphaMap'])(x as any)[k]?.dispose?.();x.dispose()}});this.root.removeFromParent()}
}

/** Material tuning for the floodlit night look (through the live renderer; values checked against photos). */
function tune(mesh:THREE.Mesh,maxAniso:number){
 const mat=mesh.material as THREE.MeshStandardMaterial;if(!mat||!mat.name)return;const n=mat.name;
 for(const k of ['map','normalMap','roughnessMap','metalnessMap'] as const){const t=(mat as any)[k] as THREE.Texture|null;if(t){t.anisotropy=maxAniso;t.wrapS=t.wrapT=THREE.RepeatWrapping}}
 mesh.receiveShadow=/asphalt|paint|kerb|concrete|sand|turf/.test(n);
 if(n==='LUS_asphalt'){mat.color.setRGB(1.18,1.18,1.18);mat.roughness=1;mat.metalness=0;mat.envMapIntensity=0.35;mat.normalScale.set(0.55,0.55)}
 else if(n==='LUS_paint'){mat.roughness=0.66;mat.envMapIntensity=0.3;mat.color.setRGB(0.74,0.74,0.74);mat.normalScale?.set(0.4,0.4)}   // keeps white paint below clipping
 else if(n==='LUS_kerb'){mat.roughness=0.5;mat.envMapIntensity=0.45;mat.color.setRGB(0.92,0.92,0.92)}
 else if(n==='LUS_fence'){mat.transparent=true;mat.depthWrite=false;mat.alphaTest=0.01;mat.alphaToCoverage=false;mat.side=THREE.DoubleSide;mat.metalness=0.5;mat.roughness=0.5;
  mat.color.setRGB(0.75,0.77,0.8);mesh.renderOrder=2;if(mat.map){mat.map.anisotropy=maxAniso;mat.map.minFilter=THREE.LinearMipmapLinearFilter}}   // blends to a faint haze far away (no shimmer)
 else if(n==='LUS_white_cladding'){mat.color.setRGB(0.6,0.61,0.62);mat.envMapIntensity=0.5}
 else if(n==='LUS_sand'){mat.color.setRGB(0.42,0.40,0.38);mat.roughness=1;mat.envMapIntensity=0.15}
 else if(n==='LUS_turf'){mat.color.setRGB(0.55,0.58,0.55);mat.roughness=1;mat.envMapIntensity=0.15}
 else if(n==='LUS_lamp'){mat.emissiveIntensity=5;mat.toneMapped=false}
 else if(n==='LUS_led_purple'){mat.emissiveIntensity=0.55;mat.emissive.setRGB(0.55,0.16,0.8)}
 else if(n==='LUS_facade'){mat.emissiveIntensity=0.9;mat.envMapIntensity=1.2}
 else if(n==='LUS_garage_interior'){mat.emissiveIntensity=0.9}
 else if(n==='LUS_boards'){mat.roughness=0.45;mat.envMapIntensity=0.6}
 else if(n==='LUS_crowd'){mat.roughness=0.95;mat.envMapIntensity=0.2}
 else mat.envMapIntensity=0.6;
 mat.needsUpdate=true;
}

function boardTex(k:number){const c=document.createElement('canvas');c.width=64;c.height=96;const x=c.getContext('2d')!;x.fillStyle='#f2f2ef';x.fillRect(0,0,64,96);
 x.fillStyle='#1b1f24';for(let s=0;s<k;s++)x.fillRect(10,14+s*26,44,14);const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;return t}

const cache=new Map<string,Promise<{manifest:Manifest;gltf:any;bytes:number;ms:number}>>();

export async function loadVenue(key:string,renderer:THREE.WebGLRenderer):Promise<Venue>{
 const v=VENUES.find(q=>q.key===key)!;
 if(!cache.has(key))cache.set(key,(async()=>{const t0=performance.now();
  const r=await fetch(v.base+'manifest.json');if(!r.ok)throw new Error('Venue manifest missing');const manifest:Manifest=await r.json();
  const buf=await (await fetch(v.base+manifest.glb)).arrayBuffer();
  const gltf=await gltfLoader().parseAsync(buf,v.base);return {manifest,gltf,bytes:buf.byteLength+JSON.stringify(manifest).length,ms:performance.now()-t0}})());
 let res;try{res=await cache.get(key)!}catch(e){cache.delete(key);throw e}
 const scene=(res.gltf.scene as THREE.Group).clone(true);
 const venue=new Venue(key,res.manifest,scene);venue.bytes=res.bytes;venue.loadMs=res.ms;
 const maxAniso=renderer.capabilities.getMaxAnisotropy();
 const protos=new Map<string,THREE.Mesh>();
 scene.traverse(o=>{const m=o as THREE.Mesh;if(!m.isMesh)return;
  if(o.name.startsWith('proto_')){protos.set(o.name.replace(/\.\d+$/,''),m);return}
  tune(m,maxAniso);
  const base=(o.name.match(/^(fence|boards|kerb|line)/)||[''])[0];   // GLTFLoader drops the '.' from Blender names
  const max=base==='fence'?420:base==='boards'?650:base==='kerb'?900:base==='line'?1200:0;
  if(max){m.geometry.computeBoundingSphere();const bs=m.geometry.boundingSphere!;venue.detail.push({obj:m,c:new THREE.Vector3(),r:bs.radius,max})}});
 for(const p of protos.values())p.removeFromParent();
 // Instanced floodlight poles and heads (positions/headings from the manifest, asset frame).
 const poles=res.manifest.instances.poles;const mtx=new THREE.Matrix4(),q=new THREE.Quaternion(),one=new THREE.Vector3(1,1,1);
 for(const name of ['proto_pole','proto_light_frame','proto_light_lamps']){const pr=protos.get(name);if(!pr)continue;
  const mat=pr.material as THREE.MeshStandardMaterial;tune(pr,maxAniso);
  const im=new THREE.InstancedMesh(pr.geometry,mat,poles.length);im.name='inst:'+name;
  poles.forEach((p,i)=>{q.setFromAxisAngle(new THREE.Vector3(0,1,0),p[3]);mtx.compose(W(p[0],p[1],p[2]),q,one);im.setMatrixAt(i,mtx)});
  im.instanceMatrix.needsUpdate=true;im.computeBoundingSphere();venue.root.add(im)}
 const fp=protos.get('proto_fence_post');const posts=res.manifest.instances.posts||[];
 if(fp&&posts.length){const im=new THREE.InstancedMesh(fp.geometry,fp.material as THREE.Material,posts.length);im.name='inst:fence_posts';
  posts.forEach((b,i)=>{q.setFromAxisAngle(new THREE.Vector3(0,1,0),b[3]);mtx.compose(W(b[0],b[1],b[2]),q,one);im.setMatrixAt(i,mtx)});im.instanceMatrix.needsUpdate=true;im.computeBoundingSphere();venue.root.add(im)}
 venue.root.add(horizon());
 const bp=protos.get('proto_brake_board');
 if(bp)for(const k of [3,2,1]){const list=res.manifest.instances.boards.filter(b=>b[4]===k);if(!list.length)continue;
  const im=new THREE.InstancedMesh(bp.geometry,new THREE.MeshStandardMaterial({map:boardTex(k),roughness:.5}),list.length);
  list.forEach((b,i)=>{q.setFromAxisAngle(new THREE.Vector3(0,1,0),b[3]+Math.PI/2);mtx.compose(W(b[0],b[1],b[2]),q,one);im.setMatrixAt(i,mtx)});
  im.instanceMatrix.needsUpdate=true;im.computeBoundingSphere();venue.root.add(im)}
 return venue;
}

/** Lusail's horizon at night: open desert all round, the glow and towers of Lusail / Doha to the south (generic
 * silhouettes, no real buildings). A band 3.2 km out, unaffected by fog. */
function horizon(){
 const w=2048,h=256;const c=document.createElement('canvas');c.width=w;c.height=h;const x=c.getContext('2d')!;
 const g=x.createLinearGradient(0,0,0,h);g.addColorStop(0,'rgba(0,0,0,0)');g.addColorStop(.72,'rgba(40,30,30,.0)');g.addColorStop(.9,'rgba(70,48,40,.55)');g.addColorStop(1,'rgba(30,24,24,1)');
 x.fillStyle=g;x.fillRect(0,0,w,h);
 let seed=11;const r=()=>{seed=(seed*16807)%2147483647;return seed/2147483647};
 // u = 0 faces +z in three.js = south in the track plane; towers cluster within +-40 degrees of south
 for(let k=0;k<70;k++){const u=(r()-.5)*0.22;const px=((u+1)%1)*w;const bw=4+r()*12,bh=8+r()*r()*70;
  x.fillStyle='rgba(12,12,16,1)';x.fillRect(px,h*.92-bh,bw,bh);
  for(let yy=h*.92-bh+3;yy<h*.92-2;yy+=4)for(let xx=px+1;xx<px+bw-1;xx+=3)if(r()<.35){x.fillStyle=r()<.6?'rgba(255,214,160,.9)':'rgba(200,220,255,.85)';x.fillRect(xx,yy,1.4,1.6)}}
 const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;t.wrapS=THREE.RepeatWrapping;
 const m=new THREE.Mesh(new THREE.CylinderGeometry(3200,3200,420,96,1,true),new THREE.MeshBasicMaterial({map:t,transparent:true,side:THREE.BackSide,fog:false,depthWrite:false}));
 m.position.y=150;m.name='horizon';m.renderOrder=-1;return m}

/** Image-based light for the floodlit night: a dark dome with two rows of bright lamp heads and a warm city glow,
 * prefiltered once. Curved bodywork picks up the light rows the way TV pictures of Lusail show them. */
export function nightEnvironment(renderer:THREE.WebGLRenderer){
 const s=new THREE.Scene();
 const dome=new THREE.Mesh(new THREE.SphereGeometry(50,32,16),new THREE.MeshBasicMaterial({side:THREE.BackSide,vertexColors:true}));
 const g=dome.geometry as THREE.BufferGeometry;const pos=g.attributes.position;const col:number[]=[];
 for(let i=0;i<pos.count;i++){const y=pos.getY(i)/50;const sky=y>0?0.012+0.05*Math.pow(1-y,6):0.025;col.push(sky*1.4,sky*1.1,sky*1.0)}
 g.setAttribute('color',new THREE.Float32BufferAttribute(col,3));s.add(dome);
 const lamp=new THREE.MeshBasicMaterial({color:new THREE.Color(9,8.6,8)});
 for(let k=0;k<48;k++){const a=k/48*Math.PI*2;for(const el of [0.30,0.42]){const r=45;const b=new THREE.Mesh(new THREE.BoxGeometry(1.6,0.7,0.2),lamp);
   b.position.set(Math.cos(a)*r*Math.cos(el),Math.sin(el)*r,Math.sin(a)*r*Math.cos(el));b.lookAt(0,0,0);s.add(b)}}
 const ground=new THREE.Mesh(new THREE.CircleGeometry(48,32),new THREE.MeshBasicMaterial({color:new THREE.Color(0.10,0.10,0.11)}));ground.rotation.x=-Math.PI/2;ground.position.y=-1;s.add(ground);
 const pm=new THREE.PMREMGenerator(renderer);const rt=pm.fromScene(s,0.035);pm.dispose();
 s.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose?.();(m.material as THREE.Material|undefined)?.dispose?.()});
 return rt.texture;
}
