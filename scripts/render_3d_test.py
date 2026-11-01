"""Blender prototype: downloaded real circuit, generic cars, real ghost-lap timing.

Run Blender with --background --disable-autoexec --python-exit-code 1.
Only geometric datablocks are imported from the car file. No asset script runs.
"""
from pathlib import Path
import sys
import json
import math
import hashlib
import bpy
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0,str(ROOT))
from cinematic_math import chase_rig, motion_progress, ghost_lane_side
from services.night_chase import night_chase_rig
from services.cornering import curvature
from services.car_style import comparison_styles,rgb
from services.render_quality import render_samples, SHADOW_POOL_SIZE
from services.ghost_material import configure_ghost_material
from services.circuit_lighting import race_lighting
FOLDER = ROOT / 'tmp/reference_review'
args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
CONFIG = json.loads(Path(args[args.index('--config')+1]).read_text(encoding='utf8')) if '--config' in args else None
INPUT = CONFIG['comparison'] if CONFIG else json.loads((FOLDER / 'paul_ricard_3d_input.json').read_text())
FIT = CONFIG['alignment'] if CONFIG else json.loads((FOLDER / '3d_alignment.json').read_text())
OUTPUT = Path(CONFIG['work_dir']) if CONFIG else ROOT / 'output/video_studio/3d_test'
OUTPUT.mkdir(parents=True, exist_ok=True)
ANIMATE = '--animate' in args
FPS = CONFIG['fps'] if CONFIG else 24
START = CONFIG['start'] if CONFIG else 4.0
END = CONFIG['end'] if CONFIG else 12.0
FRAMES = CONFIG['frames'] if CONFIG else 192
SIZE = CONFIG['size'] if CONFIG else (540,960)
CAMERA = CONFIG['camera'] if CONFIG else 'Follow cars'
ONBOARD=CAMERA in ('Onboard ghost A','Onboard ghost B')
CINEMATIC=CAMERA in ('Cinematic Ghost Chase','Classic Broadcast','The Limit')
DIRECTOR=CAMERA=='Social director' or CINEMATIC
NIGHT=CAMERA in ('Night chase A','Night chase B') or ONBOARD or DIRECTOR
PLAYBACK_SPEED=float((CONFIG or {}).get('playback_speed',1.))
TIMELINE=(CONFIG or {}).get('timeline')
SOURCE_TIMES=np.asarray(TIMELINE['source_times'] if TIMELINE else np.minimum(END,START+np.arange(FRAMES)*PLAYBACK_SPEED/FPS))
TRAIL_TIMES=np.asarray(TIMELINE['trail_times'] if TIMELINE else START+np.arange(FRAMES)*PLAYBACK_SPEED/FPS)
# NIGHT is the legacy camera-mode identifier. Lighting is independently chosen
# from the venue, so a close chase does not turn a daytime GP into a night race.
LIGHTING=race_lighting(INPUT['year'],INPUT['event'])
DARK=NIGHT and LIGHTING in ('night','twilight')
FOCUS=int(CAMERA in ('Night chase B','Onboard ghost B'))
DRIVING = CONFIG.get('driving_path') if CONFIG else None
GENERATED = CONFIG.get('generated_road') if CONFIG else None
ENVIRONMENT=CONFIG.get('asset_environment') if CONFIG else None
SOURCE_GLB=CONFIG.get('source_glb') if CONFIG else None
PRESENTATION = CONFIG.get('circuit_presentation',{}) if CONFIG else {}
STYLES=comparison_styles(INPUT['laps'])

def material(name, color, metallic=0, rough=.5, emission=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Emission Color'].default_value = (*color, 1)
    bsdf.inputs['Emission Strength'].default_value = emission
    return mat

def look_at(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()

scale = math.exp(FIT['parameters'][1])
offset = np.array(FIT['road_origin']) + np.array(FIT['parameters'][2:])
source_objects=[]
def source_digest(objects):
    digest=hashlib.sha256()
    for obj in objects:
        coords=np.empty(len(obj.data.vertices)*3,dtype=np.float32);obj.data.vertices.foreach_get('co',coords)
        loops=np.empty(len(obj.data.loops),dtype=np.int32);obj.data.loops.foreach_get('vertex_index',loops)
        mats=np.empty(len(obj.data.polygons),dtype=np.int32);obj.data.polygons.foreach_get('material_index',mats)
        digest.update(coords.tobytes());digest.update(loops.tobytes());digest.update(mats.tobytes())
        digest.update(np.asarray(obj.matrix_world).tobytes())
        for uv in obj.data.uv_layers:
            values=np.empty(len(uv.data)*2,dtype=np.float32);uv.data.foreach_get('uv',values);digest.update(values.tobytes())
        digest.update(str([m.name if m else None for m in obj.data.materials]).encode())
        for mat in obj.data.materials:
            if not mat:continue
            digest.update(str((tuple(mat.diffuse_color),mat.roughness,mat.metallic,mat.use_backface_culling,mat.surface_render_method)).encode())
            if mat.use_nodes:
                for node in mat.node_tree.nodes:
                    inputs=[]
                    for socket in node.inputs:
                        if not hasattr(socket,'default_value'):continue
                        value=socket.default_value
                        if hasattr(value,'__len__') and not isinstance(value,str):value=tuple(value)
                        inputs.append((socket.identifier,str(value)))
                    digest.update(str((node.name,node.bl_idname,inputs)).encode())
                    if hasattr(node,'image') and node.image:digest.update(str((node.image.name,node.image.filepath)).encode())
                digest.update(str([(link.from_node.name,link.from_socket.identifier,link.to_node.name,link.to_socket.identifier) for link in mat.node_tree.links]).encode())
    return digest.hexdigest()

if SOURCE_GLB:
    if GENERATED or ENVIRONMENT:raise RuntimeError('Original GLB mode forbids replacement road/environment geometry.')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SOURCE_GLB)
    scene=bpy.context.scene
    source_objects=[obj for obj in scene.objects if obj.type=='MESH']
    original_source_digest=source_digest(source_objects)
    with np.load(CONFIG['source_reference']) as data:
        world_verts=data['vertices'].copy();asphalt_triangles=data['triangles'].copy()
    road=None
elif GENERATED:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    if ENVIRONMENT:
        # Prepared locally from the supplied GLB. Append meshes only, never
        # cameras, worlds, text blocks or executable asset rigging.
        with bpy.data.libraries.load(ENVIRONMENT,link=False) as (source,target):
            target.objects=[name for name in source.objects if name=='Modified Singapore city environment']
        for obj in target.objects:
            if obj and obj.type=='MESH':scene.collection.objects.link(obj)
    mesh=bpy.data.meshes.new('Telemetry-built asphalt and decorative kerbs')
    mesh.from_pydata(GENERATED['vertices'],[],GENERATED['faces']); mesh.update()
    road=bpy.data.objects.new('Stylized circuit (not surveyed)',mesh); scene.collection.objects.link(road)
    world_verts=np.array(GENERATED['vertices'])
else:
    bpy.ops.wm.open_mainfile(filepath=CONFIG['circuit'] if CONFIG else str(ROOT/'assets/3d/circuits/paul_ricard/source/PaulRicardnosides.blend'),
                             load_ui=False, use_scripts=False)
    scene = bpy.context.scene
    road = next(o for o in scene.objects if o.type == 'MESH')
    for obj in list(scene.objects):
        if obj != road: bpy.data.objects.remove(obj, do_unlink=True)
    world_verts = np.array([tuple(road.matrix_world @ v.co) for v in road.data.vertices])
    z_base = float(np.median(world_verts[:,2]))
    world_verts[:,:2] = (world_verts[:,:2]-offset)/scale
    world_verts[:,2] = (world_verts[:,2]-z_base)/scale
    road.matrix_world = Matrix.Identity(4)
    for v, point in zip(road.data.vertices, world_verts): v.co = point
    road.data.update()
colors = [(.035,.044,.06),(.012,.19,.52),(.72,.025,.04),(.92,.93,.88),(.02,.025,.03),(.28,.25,.20)]
for idx,color in enumerate(colors if not SOURCE_GLB else []):
    mat=material('Circuit_'+str(idx),color,rough=.85)
    if GENERATED: road.data.materials.append(mat)
    else: road.data.materials[idx]=mat
if GENERATED:
    for polygon,index in zip(road.data.polygons,GENERATED['materials']): polygon.material_index=index
surface = BVHTree.FromPolygons([Vector(v) for v in world_verts],
    asphalt_triangles.tolist() if SOURCE_GLB else [tuple(p.vertices) for p in road.data.polygons])
path = np.array(INPUT['track'])
mapped = (np.array(FIT['mapped_xy'])-offset)/scale
if DRIVING:
    mapped=np.array(DRIVING['xy'])
    path=np.column_stack([DRIVING['progress'],mapped,np.zeros(len(mapped))])
heights=[]; road_hits=0; surface_counts={}
for x,y in mapped:
    hit,normal,face,dist = surface.ray_cast(Vector((x,y,500)), Vector((0,0,-1)),1000)
    if hit is None: raise RuntimeError('Telemetry path misses the circuit mesh')
    heights.append(hit.z)
    material_index=0 if SOURCE_GLB else road.data.polygons[face].material_index
    surface_counts[material_index]=surface_counts.get(material_index,0)+1
    road_hits += material_index==0 if DRIVING else material_index in {0,1,2,3,4}
coverage = road_hits/len(mapped)
print('PATH_SURFACES',surface_counts,flush=True)
if coverage < (1. if DRIVING else .95): raise RuntimeError(f'Insufficient asphalt coverage: {coverage:.1%}')
print('DRIVABLE_SURFACE_COVERAGE',coverage,flush=True)
path3 = np.column_stack([mapped,heights])
path_curvature=curvature(mapped) if NIGHT else None
ground=None
if not SOURCE_GLB:
    if GENERATED:
        # A 60-km two-triangle plane only centimetres below asphalt loses depth
        # precision as the camera moves: road/kerbs and grass fight for pixels.
        from services.render_stability import ground_mesh
        terrain=GENERATED.get('terrain')
        ground_vertices,ground_faces=(terrain['vertices'],terrain['faces']) if terrain else ground_mesh(world_verts)
        mesh=bpy.data.meshes.new('Depth-stable tiled terrain')
        mesh.from_pydata(ground_vertices,[],ground_faces);mesh.update()
        ground=bpy.data.objects.new(mesh.name,mesh);scene.collection.objects.link(ground)
    else:
        ground_z=float(world_verts[:,2].min())-.4
        bpy.ops.mesh.primitive_plane_add(size=6000,location=(0,0,ground_z))
        ground=bpy.context.object
    ground.name='Surrounding ground (decorative)'
    ground.data.materials.append(material('Stylized grass' if GENERATED else 'Dry terrain',
                                         (.065,.14,.11) if GENERATED else (.26,.235,.19),rough=1))
night_details=None
day_details=None
if GENERATED and not DARK and not ENVIRONMENT:
    from day_environment import build_environment as build_day_environment
    day_details=build_day_environment(CONFIG['scenery_plan'],material,scene,ground,road)
active=np.array([motion_progress(INPUT['laps'][FOCUS]['samples'],t) for t in np.linspace(START,min(END,INPUT['laps'][FOCUS]['lap_time']),40)])
if ENVIRONMENT:
    from singapore_furniture import build_furniture
    night_details=build_furniture(DRIVING,path3,material,scene,active)
if DARK and not SOURCE_GLB:
    ground.data.materials.clear();ground.data.materials.append(material('Night city ground',(.012,.018,.025),rough=.8))
    if not ENVIRONMENT:
        from night_environment import build_environment
        night_details=build_environment(DRIVING,material,scene,active,ground=ground)
    asphalt=road.data.materials[0];shader=asphalt.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(.045,.052,.064,1);shader.inputs['Roughness'].default_value=.55
    noise=asphalt.node_tree.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=80
    bump=asphalt.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.012
    asphalt.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);asphalt.node_tree.links.new(bump.outputs['Normal'],shader.inputs['Normal'])

# Import only geometric objects; prepared paint/carbon/tire slots are replaced
# with controlled team-inspired materials, never an external script or rig.
car_path=Path(CONFIG['car']) if CONFIG else ROOT/'assets/3d/cars/qvist/car.blend'
metadata=Path(CONFIG['car_metadata']) if CONFIG else ROOT/'assets/3d/cars/qvist/metadata.json'
car_metadata=json.loads(metadata.read_text(encoding='utf8'))[0]
car_info=car_metadata['objects']
prepared=car_metadata.get('prepared',False)
car_transforms={o['name']:o for o in car_info if o['type']=='MESH'}
cars=[]; wheels=[]
for index,lap in enumerate(INPUT['laps']):
    with bpy.data.libraries.load(str(car_path),link=False) as (source,target):
        if not set(car_transforms).issubset(source.objects):raise RuntimeError('Prepared car metadata does not match its meshes')
        target.objects=list(car_transforms)
    parent=bpy.data.objects.new('Ghost_'+lap['code'],None)
    scene.collection.objects.link(parent)
    tint=rgb(STYLES[index]['body'])
    body=material(lap['code']+'_body',tint,metallic=.5,rough=.27)
    carbon=material(lap['code']+'_carbon',(.012,.016,.02),rough=.45)
    accent=material(lap['code']+'_accent',rgb(STYLES[index]['accent']),metallic=.25,rough=.3)
    helmet_mat=material(lap['code']+'_helmet',rgb(STYLES[index]['accent']),rough=.3)
    tire=material(lap['code']+'_tire',(.006,.007,.009),rough=.85)
    rim=material(lap['code']+'_rim',(.065,.075,.09),metallic=.8,rough=.32)
    from car_finish import refine_finish
    refine_finish(body,carbon,accent,tire,rim)
    if NIGHT and index!=FOCUS:
        for mat in (body,carbon,accent,helmet_mat,tire,rim):
            configure_ghost_material(mat,alpha=.50 if CINEMATIC else .42)
            if CINEMATIC:
                bsdf=mat.node_tree.nodes.get('Principled BSDF')
                bsdf.inputs['Emission Color'].default_value=(*rgb(STYLES[index]['display']),1)
                facing=mat.node_tree.nodes.new('ShaderNodeLayerWeight')
                power=mat.node_tree.nodes.new('ShaderNodeMath');power.operation='POWER';power.inputs[1].default_value=4
                mat.node_tree.links.new(facing.outputs['Facing'],power.inputs[0])
                mat.node_tree.links.new(power.outputs[0],bsdf.inputs['Emission Strength'])
    car_wheels=[]
    for source_name,obj in zip(car_transforms,target.objects):
        scene.collection.objects.link(obj)
        obj.data=obj.data.copy()
        # Bake original evaluated world transforms; imported meshes have parent
        # rotations/inverses which must not survive reparenting to a ghost root.
        obj.data.transform(Matrix(car_transforms[source_name]['matrix']))
        obj.parent=parent
        obj.matrix_parent_inverse=Matrix.Identity(4)
        obj.matrix_basis=Matrix.Identity(4)
        obj.hide_render=False
        if prepared:
            if 'Wheel' in source_name:
                obj.data.materials.clear();obj.data.materials.append(tire);obj.data.materials.append(rim)
                center=(np.array(car_transforms[source_name]['min'])+np.array(car_transforms[source_name]['max']))*.5
                for poly in obj.data.polygons:
                    poly.material_index=int(np.linalg.norm(np.array(poly.center)[1:]-center[1:])<.22)
            else:
                # Preserve the prepared face-slot indices when replacing materials.
                for slot,mat in enumerate((body,carbon,accent,helmet_mat)):obj.data.materials[slot]=mat
        elif obj.name.startswith('Livery'): obj.data.materials.clear(); obj.data.materials.append(body)
        if 'Wheel' in obj.name:
            # Reduce excessive tire tessellation only; retain UVs and materials.
            if not prepared:
                modifier=obj.modifiers.new('Preview tire LOD','DECIMATE'); modifier.ratio=.22
            center=(np.array(car_transforms[source_name]['min'])+np.array(car_transforms[source_name]['max']))*.5
            obj.data.transform(Matrix.Translation(-Vector(center)))
            obj.location=center
            car_wheels.append(obj)
    cars.append(parent); wheels.append(car_wheels)
    if not prepared:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.28)
        helmet=bpy.context.object; helmet.name=lap['code']+'_helmet'
        helmet.parent=parent; helmet.location=(0,-.25,.68)
        helmet.data.materials.append(helmet_mat)

bpy.ops.object.camera_add()
camera=bpy.context.object; scene.camera=camera; camera.data.lens=40
camera.data.sensor_width=36
camera.data.sensor_fit='AUTO'
if NIGHT and SIZE[0]>SIZE[1]:camera.data.shift_x=-.1
if CAMERA=='Follow cars' and SIZE[0]>SIZE[1]: camera.data.shift_x=-.1
camera.data.clip_start=.25 if ONBOARD else 1.0
if ONBOARD:camera.data.lens=22;camera.data.shift_x=0
if DIRECTOR:camera.data.lens=40;camera.data.shift_x=0;camera.data.shift_y=-.10
camera.data.clip_end=8000 if CAMERA=='Full circuit' else 4000
bpy.ops.object.light_add(type='SUN', location=(0,0,100))
sun=bpy.context.object; sun.data.energy=2.5; sun.data.angle=.08
sun.data.use_shadow_jitter=False
sun.data.color=(1.,.84,.66); sun.rotation_euler=(.72,-.48,-.7)
world=bpy.data.worlds.new('Cool sky / warm afternoon sun')
world.use_nodes=True; world.node_tree.nodes['Background'].inputs[0].default_value=(.38,.53,.75,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.32; scene.world=world
if DARK:
    # Imported circuits have no procedural floodlights: preserve their materials
    # and supply enough rig illumination to retain asphalt/bodywork detail.
    sun.data.energy=.38 if SOURCE_GLB else .18;sun.data.color=(.45,.60,1.)
    sun.data.use_shadow=False
    world.node_tree.nodes['Background'].inputs[0].default_value=(.035,.055,.11,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.16
    if LIGHTING=='twilight':
        sun.data.energy=.65;sun.data.color=(1.,.52,.28)
        sun.rotation_euler=(1.38,-.15,-.7)
        world.node_tree.nodes['Background'].inputs[0].default_value=(.20,.16,.28,1)
        world.node_tree.nodes['Background'].inputs[1].default_value=.28
# Broad softbox supplies a cool edge on carbon/bodywork, not a visible spotlight.
fill=None
if CAMERA=='Follow cars' or NIGHT:
    bpy.ops.object.light_add(type='AREA')
    fill=bpy.context.object; fill.name='Chase rig soft fill'
    fill.data.use_shadow_jitter=False
    fill.data.energy=2400; fill.data.shape='DISK'; fill.data.size=22
    fill.data.color=(.66,.83,1.)
    if DARK:fill.data.energy=1600;fill.data.size=12
    if DARK:
        fill.data.use_custom_distance=True;fill.data.cutoff_distance=45
        fill.data.use_shadow=True
scene.render.engine='BLENDER_EEVEE_NEXT'
scene.eevee.shadow_pool_size=SHADOW_POOL_SIZE
scene.eevee.taa_render_samples=render_samples((CONFIG or {}).get('quality','High'))
if CONFIG and CONFIG.get('benchmark_samples'):scene.eevee.taa_render_samples=CONFIG['benchmark_samples']
scene.render.resolution_x=SIZE[0]; scene.render.resolution_y=SIZE[1]; scene.render.resolution_percentage=100
scene.render.fps=FPS; scene.render.fps_base=1.; scene.frame_step=1
scene.render.image_settings.file_format='PNG'; scene.render.film_transparent=False
# Low-effort lossless compression, retaining savings on temporary disk space.
# Pixels, render samples and final MP4 settings are unchanged.
scene.render.image_settings.compression=10
scene.view_settings.view_transform='AgX'
scene.view_settings.look='AgX - Medium High Contrast'
scene.render.use_file_extension=True
scene.frame_start=1; scene.frame_end=FRAMES
if DARK:
    scene.use_nodes=True
    nodes=scene.node_tree.nodes;nodes.clear()
    source=nodes.new('CompositorNodeRLayers');glare=nodes.new('CompositorNodeGlare');glare.glare_type='FOG_GLOW';glare.quality='MEDIUM';glare.threshold=2.;glare.size=7
    output=nodes.new('CompositorNodeComposite');scene.node_tree.links.new(source.outputs['Image'],glare.inputs['Image']);scene.node_tree.links.new(glare.outputs['Image'],output.inputs['Image'])
markers=[]; labels=[]
if CAMERA=='Full circuit':
    camera.data.type='ORTHO'
    center=path3.mean(axis=0)
    camera.location=center+np.array([0,-1000,1500])
    look_at(camera,center)
    camera.data.ortho_scale=max(np.ptp(path3[:,0]),np.ptp(path3[:,1])*SIZE[0]/SIZE[1])*1.35
    if SIZE[0]>SIZE[1]: camera.data.shift_x=-.1
    # Real-scale cars are subpixel on the overview; add explicitly decorative
    # map markers/labels without changing the car animation or timing.
    for index,lap in enumerate(INPUT['laps']):
        tint=rgb(STYLES[index]['display'])
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=5)
        marker=bpy.context.object; marker.name='Overview marker '+lap['code']
        marker.data.materials.append(material(marker.name,tint,emission=1))
        markers.append(marker)
        curve=bpy.data.curves.new('Overview label '+lap['code'],'FONT')
        curve.body=lap['code']; curve.size=17; curve.align_x='RIGHT' if index==0 else 'LEFT'
        label=bpy.data.objects.new(curve.name,curve); scene.collection.objects.link(label)
        label.rotation_euler=camera.rotation_euler
        label.data.materials.append(material(curve.name,tint,emission=1))
        labels.append(label)

from services.trajectory_spline import RouteSpline
route_spline=RouteSpline(path[:,0],path3) if CINEMATIC else None

def pose_at_progress(p,index):
    if route_spline:pos,tangent=route_spline.pose(p)
    else:pos=np.array([np.interp(p,path[:,0],path3[:,i]) for i in range(3)])
    step=2/(len(path)-1) if DRIVING else .001
    behind=np.array([np.interp(max(0,p-step),path[:,0],path3[:,i]) for i in range(3)])
    ahead=np.array([np.interp(min(1,p+step),path[:,0],path3[:,i]) for i in range(3)])
    if not route_spline:
        tangent=ahead-behind; tangent/=np.linalg.norm(tangent)
    lateral=np.array([-tangent[1],tangent[0],0])
    # Display separation adapts smoothly to the actual asphalt corridor.
    spacing=float(np.interp(p,path[:,0],DRIVING['half_separation'])) if DRIVING else 1.25
    if not NIGHT:pos+=lateral*(ghost_lane_side(index)*spacing)
    ground,_,_,_=surface.ray_cast(Vector((pos[0],pos[1],500)),Vector((0,0,-1)),1000)
    if ground: pos[2]=ground.z
    pos[2]+=.04
    return pos,tangent

def pose(lap,elapsed,index):
    samples=lap['samples']
    return pose_at_progress(float(motion_progress(samples,elapsed)),index)


from services.surface_trail import SurfaceRibbon,DistanceClock

def project_asphalt(xy):
    hit,_,face,_=surface.ray_cast(Vector((float(xy[0]),float(xy[1]),500)),Vector((0,0,-1)),1000)
    if hit is None or (not SOURCE_GLB and road.data.polygons[face].material_index!=0):
        raise RuntimeError('Trajectory ribbon leaves the authoritative asphalt; no export is allowed.')
    # Ray casting supplies height only; never quantize/snap the car's XY query
    # to the BVH's float32 hit coordinates.
    return np.array([float(xy[0]),float(xy[1]),hit.z])

trail_lifetime=.28 if CINEMATIC else 4 if CAMERA=='Full circuit' else 2
trail_width=.12 if CINEMATIC else .16 if NIGHT else .65 if CAMERA=='Full circuit' else .38
ribbon_length=float(np.linalg.norm(np.diff(path3,axis=0),axis=1).sum())
ribbon_geometry=[];trail_clocks=[];trail_objects=[]
debug_markers=[]
for index,lap in enumerate(INPUT['laps']):
    if index and NIGHT:ribbon=ribbon_geometry[0]
    else:ribbon=SurfaceRibbon(lambda p,i=index:pose_at_progress(p,i),project_asphalt,path[:,0],ribbon_length,half_width=trail_width)
    ribbon_geometry.append(ribbon);trail_clocks.append(DistanceClock(lap['samples']))
    mesh=bpy.data.meshes.new(lap['code']+' exact trajectory ribbon')
    obj=bpy.data.objects.new(mesh.name,mesh);scene.collection.objects.link(obj);obj.visible_shadow=False
    # Explicit identity: vertices are already in the road/cars' world space.
    obj.matrix_world=Matrix.Identity(4)
    mat=bpy.data.materials.new(lap['code']+' surface paint');mat.use_nodes=True
    mat.surface_render_method='BLENDED';mat.use_transparent_shadow=False;mat.use_transparency_overlap=False
    nodes=mat.node_tree.nodes;nodes.clear();links=mat.node_tree.links
    output=nodes.new('ShaderNodeOutputMaterial');transparent=nodes.new('ShaderNodeBsdfTransparent')
    color=nodes.new('ShaderNodeVertexColor');color.layer_name='trail_color'
    emission=nodes.new('ShaderNodeEmission');emission.inputs['Strength'].default_value=1.1 if NIGHT else 1.8
    links.new(color.outputs['Color'],emission.inputs['Color'])
    mix=nodes.new('ShaderNodeMixShader');links.new(color.outputs['Alpha'],mix.inputs[0])
    links.new(transparent.outputs[0],mix.inputs[1]);links.new(emission.outputs[0],mix.inputs[2])
    links.new(mix.outputs[0],output.inputs['Surface']);mesh.materials.append(mat);trail_objects.append(obj)

def update_surface_trails_unchecked(scene,*unused):
    frame=min(FRAMES-1,max(0,scene.frame_current-1))
    for index,(obj,lap,ribbon,clock) in enumerate(zip(trail_objects,INPUT['laps'],ribbon_geometry,trail_clocks)):
        vertices,times,alpha=ribbon.frame(clock,float(SOURCE_TIMES[frame]),float(TRAIL_TIMES[frame]),trail_lifetime,layer=index*.001)
        faces=[(i,i+2,i+3,i+1) for i in range(0,len(vertices)-2,2)]
        mesh=obj.data;mesh.clear_geometry();mesh.from_pydata(vertices.tolist(),[],faces);mesh.update()
        if len(vertices):
            colors=np.tile(np.array([*rgb(STYLES[index]['display']),1.]),(len(vertices),1))
            if NIGHT:
                samples=lap['samples'];st=np.asarray(samples['t'])
                k=np.clip(np.searchsorted(st,times,side='right')-1,0,len(st)-1)
                brake=np.asarray(samples['brake'],bool)[k];thr=np.interp(times,st,samples['throttle'])/100
                colors[:,:3]=np.where(brake[:,None],np.array(rgb('#ff344a')),np.array(rgb('#37e3b4'))*(.18+.82*thr[:,None]))
            colors[:,3]=alpha
            attr=mesh.color_attributes.get('trail_color') or mesh.color_attributes.new(name='trail_color',type='FLOAT_COLOR',domain='POINT')
            attr.data.foreach_set('color',colors.astype(np.float32).ravel())
        if debug_markers:debug_markers[index].location=pose(lap,float(SOURCE_TIMES[frame]),index)[0]
    bpy.context.view_layer.update()

def update_surface_trails(scene,*unused):
    try:update_surface_trails_unchecked(scene)
    except Exception as exc:
        (OUTPUT/'trail-error.txt').write_text(str(exc))
        print('TRAIL_ALIGNMENT_ERROR '+str(exc),flush=True)
        raise

trails=trail_objects
if (CONFIG or {}).get('alignment_debug'):
    from trail_alignment_debug import build_debug
    asphalt_polygons=asphalt_triangles if SOURCE_GLB else [tuple(p.vertices) for p in road.data.polygons if p.material_index==0]
    raw_debug=np.array([pose_at_progress(p,0)[0] for p in path[:,0]])
    debug_markers=build_debug(world_verts,asphalt_polygons,raw_debug,ribbon_geometry[0].centers,material,scene)
poses=[ [pose(lap,float(SOURCE_TIMES[frame]),index) for index,lap in enumerate(INPUT['laps'])]
        for frame in range(FRAMES)]
locations_by_frame=np.array([[item[0] for item in frame] for frame in poses])
tangents_by_frame=np.array([[item[1] for item in frame] for frame in poses])
footprint_checks=0
environment_checks=0
environment_surface=None
if SOURCE_GLB:
    verts=[];polys=[]
    for obj in source_objects:
        start=len(verts);verts.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
        obj.data.calc_loop_triangles()
        asphalt_slots={i for i,m in enumerate(obj.data.materials) if m and
                       (m.name.split('.')[0]=='11861Mtl' or '2023 opaque asphalt surface' in m.name)}
        polys.extend(tuple(start+i for i in t.vertices) for t in obj.data.loop_triangles if t.material_index not in asphalt_slots)
    environment_surface=BVHTree.FromPolygons(verts,polys)
if ENVIRONMENT:
    environment_object=bpy.data.objects['Modified Singapore city environment']
    environment_surface=BVHTree.FromPolygons(
        [environment_object.matrix_world @ v.co for v in environment_object.data.vertices],
        [tuple(p.vertices) for p in environment_object.data.polygons])
if DRIVING:
    # Check the whole rendered car, including nose/rear and both wheel edges,
    # against exact source triangles, not the more permissive runoff material.
    body_min=np.min([o['min'] for o in car_info if o['type']=='MESH'],axis=0)
    body_max=np.max([o['max'] for o in car_info if o['type']=='MESH'],axis=0)
    for frame in poses:
        for pos,tangent in frame:
            rotation=Matrix.Rotation(math.atan2(tangent[1],tangent[0])+math.pi/2,4,'Z')
            for x in (body_min[0],0.,body_max[0]):
                for y in (body_min[1],0.,body_max[1]):
                    corner=Vector(pos)+rotation @ Vector((x,y,0))
                    hit,_,face,_=surface.ray_cast(Vector((corner.x,corner.y,500)),Vector((0,0,-1)),1000)
                    if hit is None or (not SOURCE_GLB and road.data.polygons[face].material_index!=0):
                        raise RuntimeError('Car footprint leaves the imported asphalt; no video was published.')
                    footprint_checks+=1
                    if environment_surface:
                        # Scan the body volume above each asphalt footprint point.
                        origin=Vector((corner.x,corner.y,hit.z+.25))
                        blocked,_,_,_=environment_surface.ray_cast(origin,Vector((0,0,1)),1.7)
                        if blocked is not None:
                            raise RuntimeError('Source scenery intersects the animated car at '+str(tuple(origin))+'. The GLB was not changed; no video was published.')
                        environment_checks+=1
    print('ASPHALT_FOOTPRINT_CHECKS',footprint_checks,'ALL_PASS',flush=True)
if CINEMATIC:
    from services.cinematic_camera import cinematic_ghost_rig
    actual_min=np.min([o['min'] for o in car_info if o['type']=='MESH'],axis=0)
    actual_max=np.max([o['max'] for o in car_info if o['type']=='MESH'],axis=0)
    actual_corners=np.array([[x,y,z] for x in (actual_min[0],actual_max[0])
                            for y in (actual_min[1],actual_max[1]) for z in (actual_min[2],actual_max[2])])
    camera_telemetry={key:np.mean([np.interp(SOURCE_TIMES,lap['samples']['t'],lap['samples'][channel]) for lap in INPUT['laps']],axis=0)
                      for key,channel in (('speed','speed'),('braking','brake'))}
    rig_locations,rig_targets,rig_sides,rig_zoom=cinematic_ghost_rig(locations_by_frame,tangents_by_frame,FPS,size=SIZE,
        options=CONFIG.get('camera_options'),overhead=CAMERA=='Classic Broadcast',telemetry=camera_telemetry,local_corners=actual_corners)
elif DIRECTOR:
    from services.social_director import director_rig
    rig_locations,rig_targets,rig_sides,rig_zoom=director_rig(locations_by_frame,tangents_by_frame,FPS,size=SIZE,
        times=SOURCE_TIMES,playback_speed=PLAYBACK_SPEED)
else:
    rig_locations,rig_targets,rig_sides,rig_zoom=(night_chase_rig(locations_by_frame,tangents_by_frame,FPS,size=SIZE,focus=FOCUS)
        if NIGHT else chase_rig(locations_by_frame,tangents_by_frame,FPS,size=SIZE))
previous_rotation=None
previous_car_rotations=[None,None]
lamp_sources=[obj for obj in scene.objects if obj.type=='LIGHT' and obj.get('race_floodlight')]
lamp_fixtures=[(obj.location.copy(),obj.rotation_euler.copy(),obj.data.copy()) for obj in lamp_sources]
for obj in lamp_sources:bpy.data.objects.remove(obj,do_unlink=True)
lamp_pool=[]
if NIGHT and lamp_fixtures:
    for i in range(min(8,len(lamp_fixtures))):
        data=lamp_fixtures[0][2].copy();obj=bpy.data.objects.new('Local floodlight pool '+str(i),data)
        scene.collection.objects.link(obj);lamp_pool.append(obj)
    lamp_xy=np.array([fixture[0][:2] for fixture in lamp_fixtures])
for frame in range(1,scene.frame_end+1):
    elapsed=float(SOURCE_TIMES[frame-1])
    locations=[]; tangents=[]
    if lamp_pool:
        focus=locations_by_frame[frame-1,FOCUS,:2]
        nearest=np.argsort(np.linalg.norm(lamp_xy-focus,axis=1))[:len(lamp_pool)]
        for lamp,index in zip(lamp_pool,nearest):
            location,rotation,data=lamp_fixtures[index]
            lamp.location=location;lamp.rotation_euler=rotation;lamp.data.energy=data.energy
            lamp.keyframe_insert('location',frame=frame);lamp.keyframe_insert('rotation_euler',frame=frame)
    for index,(car,lap) in enumerate(zip(cars,INPUT['laps'])):
        pos,tangent=poses[frame-1][index]; locations.append(pos); tangents.append(tangent)
        car.location=pos
        car.rotation_euler=(-math.atan2(tangent[2],np.linalg.norm(tangent[:2])),0,math.atan2(tangent[1],tangent[0])+math.pi/2)
        if previous_car_rotations[index] is not None:car.rotation_euler.make_compatible(previous_car_rotations[index])
        previous_car_rotations[index]=car.rotation_euler.copy()
        car.keyframe_insert('location',frame=frame); car.keyframe_insert('rotation_euler',frame=frame)
        if markers:
            markers[index].location=pos+np.array([0,0,7])
            labels[index].location=pos+np.array([-15 if index==0 else 15,0,12])
            markers[index].keyframe_insert('location',frame=frame)
            labels[index].keyframe_insert('location',frame=frame)
        samples=lap['samples']; p=float(motion_progress(samples,elapsed))
        distance=p*np.linalg.norm(np.diff(path3,axis=0),axis=1).sum()
        for wheel in wheels[index]:
            wheel.rotation_euler.x=distance/.37
            if NIGHT and wheel.name.startswith(('FL_Wheel','FR_Wheel')):
                wheel.rotation_euler.z=float(np.clip(np.arctan(3.4*np.interp(p,path[:,0],path_curvature)),
                                                     -math.radians(25),math.radians(25)))
            wheel.keyframe_insert('rotation_euler',frame=frame)
    if CAMERA=='Follow cars' or NIGHT:
        if ONBOARD:
            pos=np.asarray(poses[frame-1][FOCUS][0]);forward=np.asarray(poses[frame-1][FOCUS][1])
            camera.location=pos-forward*.45+np.array([0,0,1.55])
            look_at(camera,pos+forward*12+np.array([0,0,-1.8]))
        else:
            camera.location=rig_locations[frame-1]
            look_at(camera,rig_targets[frame-1])
        if previous_rotation is not None: camera.rotation_euler.make_compatible(previous_rotation)
        previous_rotation=camera.rotation_euler.copy()
        camera.keyframe_insert('location',frame=frame); camera.keyframe_insert('rotation_euler',frame=frame)
        fill.location=rig_targets[frame-1]+rig_sides[frame-1]*(3 if NIGHT else 18)+np.array([0,0,12 if NIGHT else 24])
        look_at(fill,rig_targets[frame-1])
        fill.keyframe_insert('location',frame=frame); fill.keyframe_insert('rotation_euler',frame=frame)
for obj in [*cars,camera,*([fill] if fill else []),*[wheel for group in wheels for wheel in group]]:
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for key in fc.keyframe_points: key.interpolation='LINEAR'
framing=None
if (CAMERA=='Follow cars' or NIGHT) and not ONBOARD:
    bounds_min=np.min([o['min'] for o in car_info if o['type']=='MESH'],axis=0)
    bounds_max=np.max([o['max'] for o in car_info if o['type']=='MESH'],axis=0)
    corners=[Vector((x,y,z)) for x in (bounds_min[0],bounds_max[0])
             for y in (bounds_min[1],bounds_max[1]) for z in (bounds_min[2],bounds_max[2])]
    projected=[]
    for frame in range(1,FRAMES+1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        projected.extend(tuple(world_to_camera_view(scene,camera,car.matrix_world @ corner))
                         for car in ([cars[FOCUS]] if NIGHT and not DIRECTOR else cars) for corner in corners)
    projected=np.array(projected)
    framing={'min_xy':projected[:,:2].min(axis=0).tolist(),
             'max_xy':projected[:,:2].max(axis=0).tolist()}
    # Keep the portrait locator/footer below the complete car bounding boxes.
    limits=((.08,.90,.38,.80) if SIZE[1]>SIZE[0] else (.10,.90,.40,.81)) if DIRECTOR else ((.25,.94,.14,.68) if SIZE[1]>SIZE[0] else (.26,.96,.13,.79)) if NIGHT else ((.09,.91,.23,.74) if SIZE[1]>SIZE[0] else (.31,.94,.31,.79))
    if (projected[:,0].min()<limits[0] or projected[:,0].max()>limits[1] or
        projected[:,1].min()<limits[2] or projected[:,1].max()>limits[3] or projected[:,2].min()<=0):
        raise RuntimeError('The cinematic camera could not keep both cars inside the safe frame: '+str(framing))
    print('CAMERA_SAFE_FRAME',framing,flush=True)
scene.frame_set(1)
trail_metrics={'geometry':ribbon_geometry[0].metrics,'same_world_space':True,'shared_car_pose_function':True,
               'exact_per_frame_endpoints':True,'layer_separation_metres':.001,'legacy_paint_lift_metres':.085,
               'frames_checked':FRAMES,'max_head_to_car_xy_error_metres':0.,'max_inverse_clock_error_seconds':0.}
for i,(lap,ribbon,clock) in enumerate(zip(INPUT['laps'],ribbon_geometry,trail_clocks)):
    check_times=np.linspace(clock.t[0],clock.t[-1],2001)
    moving=np.r_[True,np.diff(clock.progress(check_times))>1e-10]
    inverse_error=np.max(np.abs(clock.time(clock.progress(check_times[moving]))-check_times[moving]))
    trail_metrics['max_inverse_clock_error_seconds']=max(trail_metrics['max_inverse_clock_error_seconds'],float(inverse_error))
    for frame,(elapsed,trail_time) in enumerate(zip(SOURCE_TIMES,TRAIL_TIMES)):
        vertices,_,_=ribbon.frame(clock,float(elapsed),float(trail_time),trail_lifetime,layer=i*.001)
        if len(vertices):
            error=np.linalg.norm(vertices[-2:,:2].mean(axis=0)-locations_by_frame[frame,i,:2])
            trail_metrics['max_head_to_car_xy_error_metres']=max(trail_metrics['max_head_to_car_xy_error_metres'],float(error))
    old_mid=(path[:-1,0]+path[1:,0])*.5
    old_centers=np.array([pose_at_progress(p,i)[0] for p in path[:,0]])
    old_actual=np.array([pose_at_progress(p,i)[0] for p in old_mid])
    old_error=np.max(np.linalg.norm((old_actual-(old_centers[:-1]+old_centers[1:])*.5)[:,:2],axis=1))
    trail_metrics['legacy_max_curve_chord_error_metres']=max(trail_metrics.get('legacy_max_curve_chord_error_metres',0),float(old_error))
if trail_metrics['max_head_to_car_xy_error_metres']>1e-8:
    raise RuntimeError('Trail head is not locked to the actual car trajectory.')
(OUTPUT/'trail-alignment.json').write_text(json.dumps(trail_metrics,indent=2))
np.savez_compressed(OUTPUT/'trail-debug.npz',raw_progress=path[:,0],raw_points=path3,
                    interpolated_progress=ribbon_geometry[0].p,interpolated_points=ribbon_geometry[0].centers,
                    painted_edges=ribbon_geometry[0].rows,car_trajectory=locations_by_frame,source_times=SOURCE_TIMES)
update_surface_trails(scene)
bpy.app.handlers.frame_change_post.append(update_surface_trails)
if CINEMATIC:
    np.savez_compressed(OUTPUT/'camera-motion.npz',location=rig_locations,target=rig_targets,
                        zoom=rig_zoom,positions=locations_by_frame,tangents=tangents_by_frame,source_times=SOURCE_TIMES)
for lamp in lamp_pool:
    for curve in lamp.animation_data.action.fcurves:
        for key in curve.keyframe_points:key.interpolation='CONSTANT'
if SOURCE_GLB and source_digest(source_objects)!=original_source_digest:
    raise RuntimeError('Source GLB geometry, UVs, transforms or material assignments changed. No video was published.')
(OUTPUT/'validation.json').write_text(json.dumps({'drivable_surface_coverage':coverage,'fit_scale':scale,
    'circuit':PRESENTATION,'geometry_backend':'Original GLB (no track edits)' if SOURCE_GLB else ('Year-selected Singapore model + telemetry driving corridor' if ENVIRONMENT else ('telemetry-built' if GENERATED else 'licensed asset')),
    'source_glb':SOURCE_GLB,'source_geometry_unchanged':True if SOURCE_GLB else None,
    'source_materials_unchanged':True if SOURCE_GLB else None,
    'replacement_track_geometry':False if SOURCE_GLB else bool(GENERATED),
    'source_geometry_digest':original_source_digest if SOURCE_GLB else None,
    'source_meshes':[{'name':o.name,'vertices':len(o.data.vertices),'faces':len(o.data.polygons)} for o in source_objects],
    'start_seconds':START,'seconds':END-START,'fps':FPS,'frames':scene.frame_end,
    'asphalt_footprint_checks':footprint_checks,
    'environment_clearance_checks':environment_checks,
    'render_performance':{'quality':(CONFIG or {}).get('quality','High'),
                          'samples':scene.eevee.taa_render_samples,'local_floodlight_pool':len(lamp_pool),
                          'shadow_pool_mb':int(scene.eevee.shadow_pool_size)},
    'display_route':{'length_metres':DRIVING['length_metres'],'spacing_range_metres':DRIVING['separation_range']} if DRIVING else None,
    'cornering':DRIVING.get('cornering') if DRIVING else None,
    'front_wheel_steering':'Geometric curvature / 3.4 m wheelbase, max 25 degrees' if NIGHT else None,
    'trail_alignment':trail_metrics,
    'presentation':{'camera':'Damped chase' if CAMERA=='Follow cars' else CAMERA,
                    'trails':'Timed team-colored ground ribbons with fading tails',
                    'car_styles':STYLES,
                    'lighting':LIGHTING if NIGHT else 'day','safe_frame':framing,
                    'night_environment':night_details,'day_environment':day_details},
    'notes':['Generic team-colored concept cars, not official team/year replicas',
             'Overlapping ghosts; original illustrative street scenery' if NIGHT else 'Ghost spacing tapers in narrow asphalt sections',
             'Shared illustrative cornering line; steering is geometric, not measured driver steering' if NIGHT else
             'Smoothed, arc-length display route; no inferred racing lines or overtakes'],
    'credit':PRESENTATION.get('credit','Paul Ricard F1 circuit by narlankaaditya, CC BY 4.0; modified scale/materials. Car by Qvist_designs, CC BY 4.0; modified.')},indent=2))
# Interactive jobs never save a scene containing licensed source geometry.
if not CONFIG and '--validate-only' not in args: bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT/'paul_ricard_ghost_test.blend'))
if '--validate-only' in args:
    print('GEOMETRY_VALIDATION_ONLY_COMPLETE',flush=True)
elif ANIMATE:
    scene.render.filepath=str(OUTPUT/'frames/frame_')
    def mark_frame_ready(scene,*unused):
        # render_write runs only after Blender has finished saving this frame.
        if not (OUTPUT/'trail-error.txt').exists():
            (OUTPUT/'frames'/f'frame_{scene.frame_current:04d}.ready').touch()
    bpy.app.handlers.render_write.append(mark_frame_ready)
    bpy.ops.render.render(animation=True)
else:
    scene.render.filepath=str(OUTPUT/'first_frame.png')
    bpy.ops.render.render(write_still=True)
