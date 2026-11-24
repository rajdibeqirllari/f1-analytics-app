/** A lightweight, generic open-wheel car built from primitives: team-coloured body, carbon wings and floor, halo,
 * four exposed wheels. No team liveries, logos or real car designs. Local frame: +x forward, y up, z to the side,
 * origin on the ground midway between the axles. */
import * as THREE from 'three';
import {mergeGeometries} from 'three/examples/jsm/utils/BufferGeometryUtils.js';

const g=(geo:THREE.BufferGeometry,x:number,y:number,z:number,rx=0,ry=0,rz=0)=>{geo.rotateX(rx);geo.rotateY(ry);geo.rotateZ(rz);geo.translate(x,y,z);return geo.index?geo.toNonIndexed():geo};
const box=(lx:number,ly:number,lz:number,x:number,y:number,z:number,rz=0,ry=0)=>g(new THREE.BoxGeometry(lx,ly,lz),x,y,z,0,ry,rz);

/** A hexahedron tapering from (x0: width w0, bottom y0, height h0) to (x1: w1, y1, h1). */
function taper(x0:number,x1:number,w0:number,w1:number,y0:number,h0:number,y1:number,h1:number,zc=0){
 const v=[[x0,y0,-w0/2],[x0,y0,w0/2],[x0,y0+h0,w0/2],[x0,y0+h0,-w0/2],[x1,y1,-w1/2],[x1,y1,w1/2],[x1,y1+h1,w1/2],[x1,y1+h1,-w1/2]].map(p=>[p[0],p[1],p[2]+zc]);
 const f=[[0,3,2,1],[4,5,6,7],[0,1,5,4],[3,7,6,2],[1,2,6,5],[0,4,7,3]];const pos:number[]=[];
 for(const q of f){for(const t of [[q[0],q[1],q[2]],[q[0],q[2],q[3]]])for(const i of t)pos.push(...v[i])}
 const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
 geo.setAttribute('uv',new THREE.Float32BufferAttribute(new Array(pos.length/3*2).fill(0),2));geo.computeVertexNormals();return geo}

function tube(points:number[][],r:number){const curve=new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(p[0],p[1],p[2])));
 return new THREE.TubeGeometry(curve,40,r,8,false).toNonIndexed()}

function arm(a:number[],b:number[],r=0.018){const A=new THREE.Vector3(...a),B=new THREE.Vector3(...b);const len=A.distanceTo(B);
 const geo=new THREE.CylinderGeometry(r,r,len,6);geo.translate(0,len/2,0);
 const q=new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),B.clone().sub(A).normalize());geo.applyQuaternion(q);geo.translate(A.x,A.y,A.z);return geo.toNonIndexed()}

let shared:{body:THREE.BufferGeometry;carbon:THREE.BufferGeometry;tyre:THREE.CylinderGeometry;rim:THREE.CylinderGeometry;helmet:THREE.BufferGeometry;wheels:number[][];tyreTex:THREE.Texture}|null=null;

function build(){
 const body=mergeGeometries([
  taper(-0.65,1.5,0.78,0.5,0.1,0.56,0.14,0.46),          // monocoque
  taper(1.5,2.88,0.44,0.15,0.16,0.42,0.2,0.13),          // nose, dropping to the tip
  taper(-1.25,0.55,0.4,0.44,0.1,0.42,0.1,0.52,0.56),     // sidepods
  taper(-1.25,0.55,0.4,0.44,0.1,0.42,0.1,0.52,-0.56),
  taper(-1.95,-0.35,0.24,0.56,0.12,0.36,0.12,0.86),       // engine cover, rising to the airbox
  taper(-0.62,-0.3,0.3,0.3,0.86,0.14,0.86,0.12),          // airbox above the driver's head
  box(1.3,0.32,0.02,-1.3,0.86,0),                         // engine fin
 ]);
 const carbon=mergeGeometries([
  box(3.5,0.05,1.5,-0.25,0.06,0),                         // floor
  box(0.52,0.04,1.86,2.7,0.1,0),box(0.3,0.03,1.6,2.52,0.18,0,0.28),   // front wing planes
  box(0.62,0.28,0.025,2.66,0.2,0.93),box(0.62,0.28,0.025,2.66,0.2,-0.93),   // endplates
  box(0.36,0.035,1.0,-2.42,0.84,0),box(0.24,0.03,1.0,-2.5,0.95,0,0.35),     // rear wing
  box(0.56,0.66,0.025,-2.42,0.66,0.5),box(0.56,0.66,0.025,-2.42,0.66,-0.5), // rear endplates
  box(0.3,0.03,0.8,-2.3,0.42,0),box(0.06,0.4,0.03,-2.3,0.62,0),             // beam wing, pillar
  box(0.5,0.12,0.06,-0.1,0.66,0.34),box(0.5,0.12,0.06,-0.1,0.66,-0.34),     // cockpit rim pads
  box(0.08,0.06,0.2,0.36,0.58,0),                                             // steering wheel
  box(0.14,0.06,0.04,0.32,0.72,0.56),box(0.14,0.06,0.04,0.32,0.72,-0.56),   // mirrors
  arm([0.25,0.6,0.38],[0.32,0.72,0.56],0.01),arm([0.25,0.6,-0.38],[0.32,0.72,-0.56],0.01),
  // halo: central pillar and hoop around the driver's head
  tube([[0.66,0.58,0],[0.6,0.78,0],[0.48,0.93,0]],0.028),
  tube([[-0.42,0.63,-0.37],[-0.32,0.85,-0.36],[0.02,0.95,-0.32],[0.36,0.95,-0.15],[0.48,0.94,0],[0.36,0.95,0.15],[0.02,0.95,0.32],[-0.32,0.85,0.36],[-0.42,0.63,0.37]],0.026),
  // suspension
  arm([1.55,0.3,0.25],[1.8,0.4,0.66]),arm([1.3,0.42,0.25],[1.8,0.42,0.66]),arm([1.55,0.3,-0.25],[1.8,0.4,-0.66]),arm([1.3,0.42,-0.25],[1.8,0.42,-0.66]),
  arm([-1.5,0.3,0.25],[-1.8,0.38,0.6]),arm([-1.3,0.45,0.25],[-1.8,0.45,0.6]),arm([-1.5,0.3,-0.25],[-1.8,0.38,-0.6]),arm([-1.3,0.45,-0.25],[-1.8,0.45,-0.6]),
 ]);
 const helmet=new THREE.SphereGeometry(0.135,16,12).toNonIndexed();helmet.translate(-0.12,0.8,0);
 const tyre=new THREE.CylinderGeometry(0.36,0.36,1,24,1,true);tyre.rotateX(Math.PI/2);
 const rim=new THREE.CylinderGeometry(0.24,0.24,1,16);rim.rotateX(Math.PI/2);
 // Tread blocks so a turning wheel reads as turning (no brand marks).
 const c=document.createElement('canvas');c.width=128;c.height=16;const x=c.getContext('2d')!;x.fillStyle='#16181b';x.fillRect(0,0,128,16);
 x.fillStyle='#24272b';for(let i=0;i<128;i+=16)x.fillRect(i,0,7,16);const tyreTex=new THREE.CanvasTexture(c);tyreTex.colorSpace=THREE.SRGBColorSpace;
 shared={body:body!,carbon:carbon!,tyre,rim,helmet,wheels:[[1.8,0.36,0.8,0.32],[1.8,0.36,-0.8,0.32],[-1.8,0.36,0.78,0.4],[-1.8,0.36,-0.78,0.4]],tyreTex};
 return shared;
}

export type CarObject={group:THREE.Group;helmet:THREE.Mesh;wheels:THREE.Object3D[];label:THREE.Sprite;shadow:THREE.Mesh;bodyMat:THREE.MeshStandardMaterial;mats:THREE.Material[];ghost:boolean};

let shadowTex:THREE.Texture|null=null;
function shadowTexture(){if(shadowTex)return shadowTex;const c=document.createElement('canvas');c.width=c.height=64;const x=c.getContext('2d')!;
 const gr=x.createRadialGradient(32,32,4,32,32,31);gr.addColorStop(0,'rgba(0,0,0,.55)');gr.addColorStop(1,'rgba(0,0,0,0)');x.fillStyle=gr;x.fillRect(0,0,64,64);
 shadowTex=new THREE.CanvasTexture(c);return shadowTex}

export function labelTexture(code:string,color:string,pos?:number|null){const c=document.createElement('canvas');c.width=256;c.height=96;const x=c.getContext('2d')!;
 x.fillStyle='rgba(8,12,16,.86)';x.beginPath();x.roundRect(4,14,248,68,10);x.fill();x.fillStyle=color;x.fillRect(4,14,16,68);
 x.fillStyle='#eef2f5';x.font='800 50px "RHX Shoulders", Impact, sans-serif';x.textBaseline='middle';
 x.fillText(pos?`${pos} ${code}`:code,34,50);const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;return t}

export function makeCar(color:string,code:string):CarObject{
 const s=shared||build();
 const bodyMat=new THREE.MeshStandardMaterial({color:new THREE.Color(color),roughness:.38,metalness:.25,side:THREE.DoubleSide});
 const carbonMat=new THREE.MeshStandardMaterial({color:0x15181c,roughness:.55,metalness:.3,side:THREE.DoubleSide});
 const group=new THREE.Group();
 group.add(new THREE.Mesh(s.body,bodyMat),new THREE.Mesh(s.carbon,carbonMat));
 const helmet=new THREE.Mesh(s.helmet,new THREE.MeshStandardMaterial({color:0xf2f2f0,roughness:.3,metalness:.1}));group.add(helmet);
 const tyreMat=new THREE.MeshStandardMaterial({map:s.tyreTex,roughness:.9,side:THREE.DoubleSide}),rimMat=new THREE.MeshStandardMaterial({color:0x2a2d31,roughness:.5,metalness:.6});
 const wheels:THREE.Object3D[]=[];
 for(const [wx,wy,wz,ww] of s.wheels){const w=new THREE.Group();w.position.set(wx,wy,wz);
  const t=new THREE.Mesh(s.tyre,tyreMat);t.scale.set(1,1,ww);const r=new THREE.Mesh(s.rim,rimMat);r.scale.set(1,1,ww*.98);w.add(t,r);group.add(w);wheels.push(w)}
 const shadow=new THREE.Mesh(new THREE.PlaneGeometry(6.4,2.6),new THREE.MeshBasicMaterial({map:shadowTexture(),transparent:true,depthWrite:false}));
 shadow.rotation.x=-Math.PI/2;shadow.position.y=0.03;group.add(shadow);
 const label=new THREE.Sprite(new THREE.SpriteMaterial({map:labelTexture(code,color),depthWrite:false,transparent:true}));
 label.scale.set(2.6,0.98,1);label.position.set(0,2.3,0);label.renderOrder=10;group.add(label);
 group.rotation.order='YZX';
 return {group,helmet,wheels,label,shadow,bodyMat,mats:[bodyMat,carbonMat,helmet.material as THREE.Material,tyreMat,rimMat],ghost:false};
}
