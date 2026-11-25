"""Quick material renders of one built car (left, right, front, rear) to check livery and decal orientation.
Run: blender --background assets/3d/cars2026/<team>.blend --python scripts/cars2026/render_check.py -- <team>"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
key = sys.argv[sys.argv.index('--') + 1]
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 900, 420
world = bpy.data.worlds.new('w')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.5, 0.52, 0.55, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.6
sc.world = world
for o in bpy.data.objects:
    if o.name.startswith('LOD1'):
        for c in o.children_recursive:
            c.hide_render = True
for m in bpy.data.materials:
    if m.name.endswith(('_decals', '_number')):
        try:
            m.surface_render_method = 'BLENDED'
        except Exception:
            m.blend_method = 'BLEND'
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
sun.data.energy = 3
sun.rotation_euler = (0.7, 0.2, 0.6)
sc.collection.objects.link(sun)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
views = dict(left=((0, 12, 0.6), 6.2), right=((0, -12, 0.6), 6.2), front=((12, 0, 1.2), 2.6), rear=((-12, 0, 1.0), 2.6), top=((0.5, 0, 12), 6.0))
for name, (loc, scale) in views.items():
    cam.location = loc
    cam.data.ortho_scale = scale
    tgt = Vector((0.0, 0.0, 0.5)) if name != 'top' else Vector((0.5, 0.0, 0.0))
    cam.rotation_euler = (tgt - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = str(ROOT / f'outputs/v3/render_{key}_{name}.png')
    bpy.ops.render.render(write_still=True)
