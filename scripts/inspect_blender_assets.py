"""Run with Blender --background --disable-autoexec --python this file."""
import bpy
import json
import numpy as np
from pathlib import Path
from mathutils import Vector

root = Path(__file__).resolve().parents[1]
paths = [root / 'assets/3d/cars/bgrt/F1_Concept_2026/F1_Concept_2026.blend',
         root / 'assets/3d/circuits/paul_ricard/source/PaulRicardnosides.blend']
report = []
for path in paths:
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    objects = []
    for obj in bpy.data.objects:
        corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
        objects.append({'name': obj.name, 'type': obj.type,
                        'parent': obj.parent.name if obj.parent else None,
                        'matrix': [list(row) for row in obj.matrix_world],
                        'vertices': len(obj.data.vertices) if obj.type == 'MESH' else 0,
                        'min': [min(v[i] for v in corners) for i in range(3)],
                        'max': [max(v[i] for v in corners) for i in range(3)],
                        'materials': [m.name for m in obj.data.materials if m] if obj.type == 'MESH' else []})
    report.append({'file': str(path), 'unit_scale': bpy.context.scene.unit_settings.scale_length,
                   'objects': objects, 'images': [{'name': im.name, 'path': im.filepath,
                                                  'packed': bool(im.packed_file)} for im in bpy.data.images]})
    if 'PaulRicard' in path.name:
        arrays = {}
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                arrays[obj.name] = np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
                obj.data.calc_loop_triangles()
                arrays[obj.name + '_triangles'] = np.array([tuple(t.vertices) for t in obj.data.loop_triangles])
                arrays[obj.name + '_materials'] = np.array([t.material_index for t in obj.data.loop_triangles])
        np.savez(root / 'tmp/reference_review/circuit_mesh_vertices.npz', **arrays)
output = root / 'tmp/reference_review/blender_asset_inspection.json'
output.write_text(json.dumps(report, indent=2), encoding='utf8')
print('ASSET_INSPECTION', output)
