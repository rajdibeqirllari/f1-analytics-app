"""Inspect/prepare an attributed GLB; no external scripts or rig datablocks."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'assets/3d/cars/qvist'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(folder/'source.glb'))
objects=[]
for obj in bpy.context.scene.objects:
    if obj.type!='MESH':continue
    coords=np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
    objects.append({'name':obj.name,'vertices':len(coords),'faces':len(obj.data.polygons),
                    'min':coords.min(axis=0).tolist(),'max':coords.max(axis=0).tolist()})
(folder/'inspection.json').write_text(json.dumps(objects,indent=2))
print(json.dumps(objects,indent=2),flush=True)
if '--prepare' not in sys.argv:raise SystemExit(0)
from mathutils import Matrix
import bmesh
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
# Source CAD coordinates are millimetres, +X rearward. Normalize to metres,
# +Y rearward / -Y nose, matching the existing renderer's car convention.
transform=Matrix(((0,-.001,0,0),(.001,0,0,-1.7),(0,0,.001,.030771),(0,0,0,1)))
for obj in meshes:
    obj.data.transform(transform @ obj.matrix_world)
    obj.parent=None;obj.matrix_world=Matrix.Identity(4)
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:obj.select_set(True)
bpy.context.view_layer.objects.active=meshes[0]
bpy.ops.object.join()
obj=bpy.context.object
bm=bmesh.new();bm.from_mesh(obj.data)
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00003)
bm.to_mesh(obj.data);bm.free()
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='LOOSE');bpy.ops.object.mode_set(mode='OBJECT')
parts=[]
for obj in bpy.context.scene.objects:
    if obj.type!='MESH':continue
    coords=np.array([tuple(v.co) for v in obj.data.vertices])
    parts.append({'name':obj.name,'vertices':len(coords),'faces':len(obj.data.polygons),
                  'min':coords.min(axis=0).tolist(),'max':coords.max(axis=0).tolist()})
(folder/'parts.json').write_text(json.dumps(parts,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'parts.blend'))
print('PARTS',len(parts),json.dumps(sorted(parts,key=lambda o:-o['vertices'])[:35],indent=2),flush=True)
# Four independent wheel components are identified from their physical bounds.
# Original body surfaces are kept, with paint/carbon/accent face slots assigned
# geometrically because the CAD source has no named bodywork materials.
for obj in list(bpy.context.scene.objects):
    if obj.type!='MESH' or not len(obj.data.polygons):
        bpy.data.objects.remove(obj,do_unlink=True);continue
    coords=np.array([tuple(v.co) for v in obj.data.vertices]);lo=coords.min(0);hi=coords.max(0);center=(lo+hi)/2
    wheel=(hi[0]-lo[0]<.5 and .65<hi[1]-lo[1]<.8 and .65<hi[2]-lo[2]<.8)
    if wheel:
        obj.name=('F' if center[1]<0 else 'R')+('L' if center[0]<0 else 'R')+'_Wheel'
        obj.data.materials.clear();obj.data.materials.append(bpy.data.materials.new('Tire'))
    else:
        obj.name='Livery' if len(coords)>10000 else 'carbon_'+obj.name
        obj.data.materials.clear()
        for name in ('Paint','Carbon','Accent','Helmet'):obj.data.materials.append(bpy.data.materials.new(name))
        for poly in obj.data.polygons:
            x,y,z=poly.center;ax=abs(x)
            dark=(z<.13 or (y< -2.3 and ax>.20) or (y>2.05 and z>.60) or
                  (ax>.43 and (abs(y+1.75)<.35 or abs(y-1.645)<.35) and z<.50) or
                  (ax<.3 and -.9<y<.2 and z>.60))
            accent=(not dark and ((.30<ax<.36 and -.9<y<1.2 and z>.35) or (ax<.055 and y< -1.4 and z>.28)))
            helmet=(ax<.25 and -.65<y<-.1 and z>.87)
            poly.material_index=3 if helmet else 1 if dark or obj.name.startswith('carbon') else 2 if accent else 0
    # Collapse CAD tessellation while retaining the silhouette, boundaries and
    # per-face material assignments. Bake so render jobs never execute modifiers.
    bpy.context.view_layer.objects.active=obj
    mod=obj.modifiers.new('Render LOD','DECIMATE');mod.ratio=.18 if wheel else .25
    bpy.ops.object.modifier_apply(modifier=mod.name)
    for poly in obj.data.polygons:poly.use_smooth=True
objects=[]
for obj in bpy.context.scene.objects:
    coords=np.array([tuple(v.co) for v in obj.data.vertices])
    objects.append({'name':obj.name,'type':'MESH','matrix':np.eye(4).tolist(),
                    'min':coords.min(0).tolist(),'max':coords.max(0).tolist(),
                    'vertices':len(coords),'faces':len(obj.data.polygons)})
if sum('Wheel' in obj['name'] for obj in objects)!=4:raise RuntimeError('Expected four independent wheel meshes')
(folder/'metadata.json').write_text(json.dumps([{'file':str(folder/'car.blend'),'unit_scale':1,'objects':objects,
    'prepared':True,'creator':'Qvist_designs','license':'CC BY 4.0','modifications':'unit/orientation normalization, mesh welding, LOD, materials'}],indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'car.blend'))
print('PREPARED',sum(o['faces'] for o in objects),'faces',flush=True)
