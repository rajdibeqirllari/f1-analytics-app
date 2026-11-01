"""Read-only asphalt/metadata index. No GLB scene or material is changed/saved."""
from pathlib import Path
import hashlib,json,sys
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1];FOLDER=ROOT/'assets/3d/circuits/singapore'
calibration=json.loads((ROOT/'assets/3d/circuits/marina-bay-street-circuit/prepared/profile.json').read_text())
for modern in (False,True):
    source=FOLDER/('singapore-2023.glb' if modern else 'singapore.glb')
    out=FOLDER/'prepared'/('source-2023-onward' if modern else 'source-pre-2023');out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    surfaces=[];objects=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH':continue
        obj.data.calc_loop_triangles()
        slots={i for i,m in enumerate(obj.data.materials) if m and
               (m.name.split('.')[0]=='11861Mtl' or '2023 opaque asphalt surface' in m.name)}
        triangles=[t for t in obj.data.loop_triangles if t.material_index in slots]
        if triangles:
            vertices=np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
            surfaces.append(vertices[np.array([t.vertices[:] for t in triangles])])
        objects.append({'name':obj.name,'vertices':len(obj.data.vertices),
                        'faces':len(obj.data.polygons),'materials':[m.name if m else None for m in obj.data.materials]})
    if not surfaces:raise RuntimeError('Source contains no recognized asphalt surfaces.')
    asphalt=np.concatenate(surfaces)
    vertices,inverse=np.unique(asphalt.reshape(-1,3),axis=0,return_inverse=True)
    triangles=inverse.reshape(-1,3)
    points=np.concatenate([vertices,asphalt.mean(axis=1)])
    np.savez_compressed(out/'road_reference.npz',points=points,vertices=vertices,triangles=triangles)
    stat=source.stat()
    profile=dict(calibration,mode='unmodified-glb',source_model=source.name,
        source_size=stat.st_size,source_mtime_ns=stat.st_mtime_ns,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),objects=objects,
        geometry_changes=False,material_changes=False,removed_faces=0,decimation=False,
        adaptation='Source GLB imported directly. Only car motion and camera/light rig added.')
    (out/'profile.json').write_text(json.dumps(profile,indent=2))
    print('SOURCE_GLB_INDEXED',source.name,len(objects),'meshes',len(triangles),'asphalt triangles',flush=True)
