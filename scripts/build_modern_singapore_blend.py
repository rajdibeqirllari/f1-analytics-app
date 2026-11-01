"""Blender-only safe geometry import and local adaptation; no source scripts."""
import bpy,bmesh
import numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'assets/3d/circuits/marina-bay-street-circuit'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(FOLDER/'source/singapore.glb'))
obj=next(o for o in bpy.context.scene.objects if o.type=='MESH')
if len(obj.data.polygons)!=813653:raise RuntimeError('Source geometry changed; rerun inspection before adapting.')
indices=set(np.load(FOLDER/'prepared/remove_faces.npy').tolist())
bm=bmesh.new();bm.from_mesh(obj.data);bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm,geom=[f for f in bm.faces if f.index in indices],context='FACES')
bm.to_mesh(obj.data);bm.free();obj.data.update();obj.name='Modified Singapore city environment'
# Distant city scenery does not need the original simulation mesh density.
# Collapse planar/detail edges while preserving separate material boundaries.
bpy.context.view_layer.objects.active=obj;obj.select_set(True)
lod=obj.modifiers.new('City scenery render LOD','DECIMATE');lod.ratio=.32
lod.delimit={'MATERIAL'}
bpy.ops.object.modifier_apply(modifier=lod.name)
for mat in obj.data.materials:
    if mat and mat.use_nodes:
        shader=mat.node_tree.nodes.get('Principled BSDF')
        if shader:
            shader.inputs['Roughness'].default_value=.8
            shader.inputs['Metallic'].default_value=0
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(FOLDER/'prepared/modern_environment.blend'))
print('MODERN_SINGAPORE_ENVIRONMENT_READY',len(obj.data.polygons),flush=True)
