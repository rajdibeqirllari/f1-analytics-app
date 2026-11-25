/** Individually modelled cars (Blender: scripts/cars2026/build_field.py), resolved by season and constructor so each
 * driver gets their own team's chassis, livery and their own racing number.
 *
 * The registry (/cars/<season>/registry.json) lists constructors with name patterns, chassis, driver order and number
 * style. A model is used for its own season. For a session from another season the viewer can switch on a labelled
 * preview, which maps that season's constructor identities onto the modelled season (e.g. 2025 Kick Sauber -> 2026
 * Audi); it is never applied silently. Teams with no model keep the generic car (car.ts). */
import * as THREE from 'three';
import {gltfLoader} from './venue';
import {labelTexture,type CarObject} from './car';

export type TeamEntry={key:string;chassis:string;team:string;aliases:string[];drivers:Record<string,number>;
 number:{font:string;fill:string;outline:string|null};finish:string;season:number;url:string;re:RegExp[]};
type Registry={season:number;teams:TeamEntry[];previewFrom:{re:RegExp;key:string}[]};

const SEASONS=[2026];
let registry:Promise<Registry[]>|null=null;
export function loadRegistry(){
 if(!registry)registry=Promise.all(SEASONS.map(async season=>{const r=await fetch(`/cars/${season}/registry.json`);if(!r.ok)throw new Error('car registry missing');const d=await r.json();
  return {season,teams:d.teams.map((t:any)=>({...t,season,url:`/cars/${season}/${t.key}.glb`,re:t.aliases.map((a:string)=>new RegExp(a,'i'))})),
   previewFrom:Object.entries(d.preview_from_2025||{}).map(([re,key])=>({re:new RegExp(re,'i'),key:key as string}))} as Registry})).catch(e=>{registry=null;throw e});
 return registry}

export type Resolved={entry:TeamEntry;preview:boolean;mappedFrom:string|null};
/** The model for a driver's team in this session's season; or, with preview on, the latest modelled season's model
 * for the same constructor identity (renamed teams mapped explicitly). */
export function resolveModel(regs:Registry[],team:string,year:number|null|undefined,preview:boolean):Resolved|null{
 const t=(team||'').trim();
 const own=regs.find(r=>r.season===year);
 if(own){const e=own.teams.find(x=>x.re.some(re=>re.test(t)));return e?{entry:e,preview:false,mappedFrom:null}:null}
 if(!preview)return null;
 const latest=[...regs].sort((a,b)=>b.season-a.season)[0];if(!latest)return null;
 const direct=latest.teams.find(x=>x.re.some(re=>re.test(t)));
 const mapped=latest.previewFrom.find(m=>m.re.test(t));
 const e=mapped?latest.teams.find(x=>x.key===mapped.key):direct;
 const renamed=!!e&&!t.toLowerCase().includes(e.team.toLowerCase().split(' ')[0]);   // e.g. 2025 Kick Sauber shown as 2026 Audi
 return e?{entry:e,preview:true,mappedFrom:(mapped||renamed)&&renamed?t:null}:null}
export function previewAvailable(regs:Registry[],year:number|null|undefined){return !!regs.length&&!regs.some(r=>r.season===year)}

const cache=new Map<string,Promise<THREE.Group>>();
function load(url:string){if(!cache.has(url))cache.set(url,gltfLoader().loadAsync(url).then(g=>g.scene as THREE.Group).catch(e=>{cache.delete(url);throw e}));return cache.get(url)!}

export type DetailedCar=CarObject&{model:string;chassis:string;number:string;lod:[THREE.Object3D|null,THREE.Object3D|null];steer:THREE.Object3D[];radii:number[];
 mounts:{pod:THREE.Vector3;cockpit:THREE.Vector3};numberMats:THREE.MeshStandardMaterial[]};

let shadowTex:THREE.Texture|null=null;
function contactShadow(){if(!shadowTex){const c=document.createElement('canvas');c.width=c.height=64;const x=c.getContext('2d')!;
 const gr=x.createRadialGradient(32,32,2,32,32,31);gr.addColorStop(0,'rgba(0,0,0,.7)');gr.addColorStop(.6,'rgba(0,0,0,.35)');gr.addColorStop(1,'rgba(0,0,0,0)');x.fillStyle=gr;x.fillRect(0,0,64,64);shadowTex=new THREE.CanvasTexture(c)}return shadowTex}

/** One driver's number in the team's style, on a texture owned by that car only. */
export function numberTexture(num:string,style:TeamEntry['number']){
 const c=document.createElement('canvas');c.width=256;c.height=128;const x=c.getContext('2d')!;
 const font=style.font==='serif'?'700 112px Georgia, "Times New Roman", serif':'900 116px "RHX Shoulders", Impact, sans-serif';
 x.font=font;x.textAlign='center';x.textBaseline='middle';
 if(style.outline){x.lineWidth=12;x.lineJoin='round';x.strokeStyle=style.outline;x.strokeText(num,128,68)}
 x.fillStyle=style.fill;x.fillText(num,128,68);
 const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=8;t.flipY=false;   // glTF UV convention
 return t}

/** A per-driver instance: geometry shared with teammates, every material cloned (number plates and T-cam are this car's
 * own, so a teammate's number can never appear on it). */
export async function makeDetailedCar(entry:TeamEntry,code:string,color:string,number:string,teammateIndex:number):Promise<DetailedCar>{
 const src=await load(entry.url);
 const root=src.clone(true);
 const mats:THREE.Material[]=[];const numberMats:THREE.MeshStandardMaterial[]=[];const swap=new Map<THREE.Material,THREE.Material>();
 const gloss=entry.finish==='gloss';
 root.traverse(o=>{const m=o as THREE.Mesh;if(!m.isMesh)return;m.castShadow=true;m.receiveShadow=false;
  const old=m.material as THREE.MeshStandardMaterial;let nm=swap.get(old);
  if(!nm){const n=old.name||'';
   if(/_paint$/.test(n)){nm=new THREE.MeshPhysicalMaterial({name:n,vertexColors:true,color:0xffffff,roughness:gloss?0.26:0.4,metalness:gloss?0.4:0.18,
     clearcoat:1,clearcoatRoughness:gloss?0.05:0.2,envMapIntensity:1.0,side:THREE.DoubleSide})}
   else if(/_carbon$/.test(n)){const p=new THREE.MeshPhysicalMaterial({name:n,map:old.map,normalMap:old.normalMap,normalScale:new THREE.Vector2(.5,.5),color:0xffffff,roughness:0.38,metalness:0.15,
     clearcoat:0.7,clearcoatRoughness:0.12,side:THREE.DoubleSide});if(p.map)p.map.wrapS=p.map.wrapT=THREE.RepeatWrapping;nm=p}
   else if(/_decals$/.test(n)){const p=old.clone();p.transparent=true;p.alphaTest=0.08;p.depthWrite=false;p.polygonOffset=true;p.polygonOffsetFactor=-2;p.polygonOffsetUnits=-2;
     p.roughness=0.3;p.metalness=0;if(p.map){p.map.anisotropy=8}nm=p}
   else if(/_number$/.test(n)){const p=new THREE.MeshStandardMaterial({name:n+':'+number,map:numberTexture(number||'?',entry.number),transparent:true,alphaTest:0.1,depthWrite:false,
     polygonOffset:true,polygonOffsetFactor:-3,polygonOffsetUnits:-3,roughness:0.35,side:THREE.DoubleSide});numberMats.push(p);nm=p}
   else if(/_tcam$/.test(n)){nm=new THREE.MeshStandardMaterial({name:n,color:teammateIndex%2?0xf4d000:0x0b0b0c,roughness:0.5})}   // T-cam: black / yellow by team order
   else if(/tyre_band$/.test(n)){nm=old.clone();(nm as THREE.MeshStandardMaterial).color.setRGB(0.12,0.12,0.12)}
   else if(/_tyre$/.test(n)){nm=old.clone();(nm as THREE.MeshStandardMaterial).roughness=0.88;(nm as THREE.MeshStandardMaterial).envMapIntensity=0.25}
   else{nm=old.clone();if(/rain_light/.test(n))(nm as THREE.MeshStandardMaterial).toneMapped=false;
    if(/mirror_glass/.test(n)){(nm as THREE.MeshStandardMaterial).roughness=0.12;(nm as THREE.MeshStandardMaterial).envMapIntensity=0.35;(nm as THREE.MeshStandardMaterial).color.setRGB(0.35,0.36,0.38)}}
   if(!/_decals$|_number$/.test(n))(nm as THREE.MeshStandardMaterial).side=THREE.DoubleSide;
   swap.set(old,nm);mats.push(nm)}
  m.material=nm;if(/_decals$|_number/.test(nm.name))m.renderOrder=2});
 const find=(n:string)=>root.getObjectByName(n)||null;
 const group=new THREE.Group();group.add(root);group.rotation.order='YZX';group.name=`car:${code}:${entry.key}:${number}`;
 const wheels=['wheel_FL','wheel_FR','wheel_RL','wheel_RR'].map(n=>find(n)!).filter(Boolean);
 const steer=['steer_FL','steer_FR'].map(n=>find(n)!).filter(Boolean);
 const radii=['steer_FL','steer_FR','steer_RL','steer_RR'].map(n=>find(n)?.position.y||0.355);
 const helmet=(find('driver_helmet') as THREE.Mesh)||new THREE.Mesh();
 const pod=find('cam_pod')?.position.clone()||new THREE.Vector3(-0.5,1.06,0);
 const cockpit=find('cam_cockpit')?.position.clone()||new THREE.Vector3(0.13,0.78,0);
 const shadow=new THREE.Mesh(new THREE.PlaneGeometry(5.8,2.3),new THREE.MeshBasicMaterial({map:contactShadow(),transparent:true,depthWrite:false,opacity:.85}));
 shadow.rotation.x=-Math.PI/2;shadow.position.y=0.02;shadow.renderOrder=1;group.add(shadow);
 const label=new THREE.Sprite(new THREE.SpriteMaterial({map:labelTexture(code,color),depthWrite:false,transparent:true}));label.scale.set(2.6,.98,1);label.position.set(0,2.3,0);label.renderOrder=10;group.add(label);
 const paint=mats.find(m=>/_paint$/.test(m.name)) as THREE.MeshStandardMaterial;
 return {group,helmet,wheels,label,shadow,bodyMat:paint,mats,ghost:false,model:entry.key,chassis:entry.chassis,number,lod:[find('LOD0'),find('LOD1')],steer,radii,mounts:{pod,cockpit},numberMats};
}

export function isDetailed(c:CarObject):c is DetailedCar{return 'model' in c}
