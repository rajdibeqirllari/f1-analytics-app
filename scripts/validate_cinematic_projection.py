"""Blender/NumPy projection agreement using the actual concept-car bounds."""
from pathlib import Path
import sys,json,math
import bpy
import numpy as np
from mathutils import Vector,Euler,Matrix
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.cinematic_math import project_cars
from services.cinematic_camera import cinematic_ghost_rig
from scripts.cinematic_math import motion_progress
from services.trajectory_spline import RouteSpline
from mathutils.bvhtree import BVHTree

bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera
camera.data.lens=40;camera.data.sensor_width=36;camera.data.sensor_fit='AUTO'
camera.data.shift_x=0;camera.data.shift_y=-.1
metadata=json.loads((ROOT/'assets/3d/cars/qvist/metadata.json').read_text())[0]
objects=[o for o in metadata['objects'] if o['type']=='MESH']
low=np.min([o['min'] for o in objects],axis=0);high=np.max([o['max'] for o in objects],axis=0)
corners=np.array([[x,y,z] for x in (low[0],high[0]) for y in (low[1],high[1]) for z in (low[2],high[2])])
t=np.arange(180)/60;yaw=t*1.8;grade=.34*np.sin(t*5)
heading=np.column_stack([np.cos(yaw)*np.cos(grade),np.sin(yaw)*np.cos(grade),np.sin(grade)])
center=np.cumsum(heading*.9,axis=0)
positions=np.stack([center,center-heading*(3+4*np.sin(t*2)**2)[:,None]],axis=1)
tangents=np.stack([heading,heading],axis=1)
case_path=None;telemetry=None
if '--case' in sys.argv:
    case_path=Path(sys.argv[sys.argv.index('--case')+1]);case=json.loads(case_path.read_text())
    route=case['route'];mesh=case['mesh'];xy=np.asarray(route['xy']);progress=np.asarray(route['progress'])
    surface=BVHTree.FromPolygons([Vector(v) for v in mesh['vertices']],mesh['faces'])
    heights=[surface.ray_cast(Vector((float(x),float(y),500)),Vector((0,0,-1)),1000)[0].z for x,y in xy]
    spline=RouteSpline(progress,np.column_stack([xy,heights]))
    times=np.asarray(case['timeline']['source_times']);t=np.arange(len(times))/60
    positions=[];tangents=[]
    for elapsed in times:
        pp=[];tt=[]
        for lap in case['laps']:
            p=float(motion_progress(lap['samples'],elapsed));point,tangent=spline.pose(p)
            ground=surface.ray_cast(Vector((float(point[0]),float(point[1]),500)),Vector((0,0,-1)),1000)[0]
            point[2]=ground.z+.04;pp.append(point);tt.append(tangent)
        positions.append(pp);tangents.append(tt)
    positions=np.asarray(positions);tangents=np.asarray(tangents)
    telemetry={key:np.mean([np.interp(times,lap['samples']['t'],lap['samples'][channel]) for lap in case['laps']],axis=0)
               for key,channel in (('speed','speed'),('braking','brake'))}
results=[]
for size in (((540,960),(960,540)) if case_path else ((540,960),(960,540),(1080,1920),(1920,1080))):
    scene.render.resolution_x=size[0];scene.render.resolution_y=size[1];scene.render.resolution_percentage=100
    for overhead in (False,True):
        location,target,_,zoom=cinematic_ghost_rig(positions,tangents,60,size,
            options=None if case_path else dict(zoom=.75,framing=1.3,smoothness=.15,intensity=1),overhead=overhead,local_corners=corners,telemetry=telemetry)
        predicted=project_cars(positions,tangents,location,target,size,local_corners=corners)
        if size[0]>size[1]:predicted[:,:,:,0]-=.1
        predicted[:,:,:,1]+=.1*max(1,size[0]/size[1])
        actual=[]
        for frame in range(len(t)):
            camera.location=location[frame]
            camera.rotation_euler=(Vector(target[frame])-camera.location).to_track_quat('-Z','Y').to_euler()
            bpy.context.view_layer.update()
            row=[]
            for index in (0,1):
                tangent=tangents[frame,index]
                rotation=Euler((-math.atan2(tangent[2],np.linalg.norm(tangent[:2])),0,math.atan2(tangent[1],tangent[0])+math.pi/2),'XYZ')
                transform=Matrix.Translation(Vector(positions[frame,index])) @ rotation.to_matrix().to_4x4()
                row.append([tuple(world_to_camera_view(scene,camera,transform @ Vector(c))) for c in corners])
            actual.append(row)
        actual=np.asarray(actual)
        error=float(np.abs(actual[:,:,:,:2]-predicted[:,:,:,:2]).max())
        minimum=actual[:,:,:,:2].min(axis=(0,1,2));maximum=actual[:,:,:,:2].max(axis=(0,1,2))
        limits=(.08,.90,.38,.80) if size[1]>size[0] else (.10,.90,.40,.81)
        # Blender stores kilometre-scale world transforms in float32. Allow
        # <0.05px at 960px; this is NOT the HUD safe-frame acceptance margin.
        if error>(5e-5 if case_path else 2e-6):raise RuntimeError('Projection pipeline mismatch: '+str(error))
        if minimum[0]<limits[0] or maximum[0]>limits[1] or minimum[1]<limits[2] or maximum[1]>limits[3]:
            raise RuntimeError('Actual Blender framing failed: '+str((minimum,maximum)))
        results.append(dict(size=size,overhead=overhead,max_projection_error=error,min_xy=minimum.tolist(),max_xy=maximum.tolist()))
destination=case_path.with_suffix('.validation.json') if case_path else ROOT/'tmp/camera-projection-validation.json'
destination.write_text(json.dumps(results,indent=2))
print('EXACT_CINEMATIC_PROJECTION_PASS',json.dumps(results),flush=True)
