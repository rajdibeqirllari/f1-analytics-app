/** Individually modelled cars (Blender: scripts/qatar/build_cars_blend.py), resolved by season and constructor so each
 * driver gets their own team's chassis. Teams without a finished model keep the generic car from car.ts.
 *
 * A model is used only for its own season. For a session from another season the viewer can turn on a labelled
 * preview (e.g. 2026 shapes on 2025 Qatar data); it is never applied silently. */
import * as THREE from 'three';
import {gltfLoader} from './venue';
import {labelTexture,type CarObject} from './car';

export type ModelEntry={key:string;season:number;team:RegExp;url:string;label:string;gloss:boolean};
export const MODELS:ModelEntry[]=[
 {key:'w17',season:2026,team:/^mercedes(-amg)?( petronas)?( f1 team)?$/i,url:'/cars/2026/w17.glb',label:'Mercedes W17 (2026)',gloss:false},
 {key:'rb22',season:2026,team:/^(oracle )?red bull racing$/i,url:'/cars/2026/rb22.glb',label:'Red Bull RB22 (2026)',gloss:true},
];

/** The model for a driver's team in this session's season, or (preview) the latest model of that constructor. */
export function resolveModel(team:string,year:number|null|undefined,preview:boolean):{entry:ModelEntry;preview:boolean}|null{
 const t=(team||'').trim();const own=MODELS.filter(m=>m.team.test(t));if(!own.length)return null;
 const exact=own.find(m=>m.season===year);if(exact)return {entry:exact,preview:false};
 if(preview)return {entry:own.sort((a,b)=>b.season-a.season)[0],preview:true};
 return null}
export function previewAvailable(teams:string[],year:number|null|undefined){return teams.some(t=>{const own=MODELS.filter(m=>m.team.test((t||'').trim()));return own.length>0&&!own.some(m=>m.season===year)})}

const cache=new Map<string,Promise<THREE.Group>>();
function load(url:string){if(!cache.has(url))cache.set(url,gltfLoader().loadAsync(url).then(g=>g.scene as THREE.Group).catch(e=>{cache.delete(url);throw e}));return cache.get(url)!}

export type DetailedCar=CarObject&{model:string;lod:[THREE.Object3D|null,THREE.Object3D|null];steer:THREE.Object3D[];radii:number[];mounts:{pod:THREE.Vector3;cockpit:THREE.Vector3}};

let shadowTex:THREE.Texture|null=null;
function contactShadow(){if(!shadowTex){const c=document.createElement('canvas');c.width=c.height=64;const x=c.getContext('2d')!;
 const gr=x.createRadialGradient(32,32,2,32,32,31);gr.addColorStop(0,'rgba(0,0,0,.7)');gr.addColorStop(.6,'rgba(0,0,0,.35)');gr.addColorStop(1,'rgba(0,0,0,0)');x.fillStyle=gr;x.fillRect(0,0,64,64);shadowTex=new THREE.CanvasTexture(c)}return shadowTex}

/** A per-driver instance: geometry shared, materials cloned (ghosting changes opacity per car). */
export async function makeDetailedCar(entry:ModelEntry,code:string,color:string):Promise<DetailedCar>{
 const src=await load(entry.url);
 const root=src.clone(true);
 const mats:THREE.Material[]=[];const swap=new Map<THREE.Material,THREE.Material>();
 root.traverse(o=>{const m=o as THREE.Mesh;if(!m.isMesh)return;m.castShadow=true;m.receiveShadow=false;
  const old=m.material as THREE.MeshStandardMaterial;let nm=swap.get(old);
  if(!nm){
   if(/_paint$/.test(old.name)){const p=new THREE.MeshPhysicalMaterial({name:old.name,vertexColors:true,color:0xffffff,roughness:entry.gloss?0.28:0.42,metalness:entry.gloss?0.45:0.2,
     clearcoat:1,clearcoatRoughness:entry.gloss?0.05:0.22,envMapIntensity:1.0,side:THREE.DoubleSide});nm=p}
   else if(/_carbon$/.test(old.name)){const p=new THREE.MeshPhysicalMaterial({name:old.name,map:old.map,normalMap:old.normalMap,normalScale:new THREE.Vector2(.5,.5),color:0xffffff,roughness:0.38,metalness:0.15,
     clearcoat:0.7,clearcoatRoughness:0.12,side:THREE.DoubleSide});if(p.map){p.map.wrapS=p.map.wrapT=THREE.RepeatWrapping}nm=p}
   else if(/tyre_band$/.test(old.name)){nm=old.clone();(nm as THREE.MeshStandardMaterial).color.setRGB(0.12,0.12,0.12)}
   else if(/_tyre$/.test(old.name)){nm=old.clone();(nm as THREE.MeshStandardMaterial).roughness=0.88;(nm as THREE.MeshStandardMaterial).envMapIntensity=0.25}
   else{nm=old.clone();if(/rain_light/.test(old.name))(nm as THREE.MeshStandardMaterial).toneMapped=false;if(/mirror_glass/.test(old.name)){(nm as THREE.MeshStandardMaterial).roughness=0.12;(nm as THREE.MeshStandardMaterial).envMapIntensity=0.35;(nm as THREE.MeshStandardMaterial).color.setRGB(0.35,0.36,0.38)}}
   (nm as THREE.MeshStandardMaterial).side=THREE.DoubleSide;swap.set(old,nm);mats.push(nm)}
  m.material=nm});
 const find=(n:string)=>root.getObjectByName(n)||null;
 const group=new THREE.Group();group.add(root);group.rotation.order='YZX';
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
 return {group,helmet,wheels,label,shadow,bodyMat:paint,mats,ghost:false,model:entry.key,lod:[find('LOD0'),find('LOD1')],steer,radii,mounts:{pod,cockpit}};
}

export function isDetailed(c:CarObject):c is DetailedCar{return 'model' in c}
