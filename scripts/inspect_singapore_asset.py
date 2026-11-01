"""Import supplied GLB safely, report geometry and render a diagnostic overview."""
import bpy,json
import numpy as np
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
ASSET=ROOT/'assets/3d/circuits/marina-bay-street-circuit'
OUT=ROOT/'tmp/reference_review/singapore_asset';OUT.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ASSET/'source/singapore.glb'))
scene=bpy.context.scene;objects=[];arrays={}
for index,obj in enumerate(list(scene.objects)):
    if obj.type!='MESH':continue
    vertices=np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
    obj.data.calc_loop_triangles()
    triangles=np.array([tuple(t.vertices) for t in obj.data.loop_triangles])
    key=f'mesh_{index}'
    arrays[key]=vertices;arrays[key+'_triangles']=triangles
    arrays[key+'_materials']=np.array([t.material_index for t in obj.data.loop_triangles])
    objects.append({'key':key,'name':obj.name,'vertices':len(vertices),'triangles':len(triangles),
                    'min':vertices.min(axis=0).tolist(),'max':vertices.max(axis=0).tolist(),
                    'materials':[m.name if m else None for m in obj.data.materials]})
np.savez_compressed(OUT/'meshes.npz',**arrays)
report={'objects':objects,'images':[{'name':im.name,'path':im.filepath,'size':list(im.size)} for im in bpy.data.images]}
(OUT/'inspection.json').write_text(json.dumps(report,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'inspected.blend'))
print('SINGAPORE_ASSET_INSPECTED',len(objects),flush=True)
bpy.ops.object.camera_add(location=(0,-200,6000))
camera=bpy.context.object;camera.rotation_euler=(0,0,0);camera.data.type='ORTHO';camera.data.ortho_scale=4500;camera.data.clip_end=10000;scene.camera=camera
bpy.ops.object.light_add(type='SUN',location=(0,0,1000));bpy.context.object.data.energy=2
scene.world=bpy.data.worlds.new('Inspection daylight');scene.world.use_nodes=True
scene.world.node_tree.nodes.get('Background').inputs[0].default_value=(.4,.4,.4,1)
scene.render.engine='CYCLES';scene.cycles.samples=8
scene.render.resolution_x=1024;scene.render.resolution_y=1024;scene.render.resolution_percentage=100
scene.render.filepath=str(OUT/'overview.png');bpy.ops.render.render(write_still=True)
