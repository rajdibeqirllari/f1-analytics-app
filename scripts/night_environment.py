"""Original, procedural night street scenery; no downloaded executable assets.

Illustrative architecture and road furniture, not a surveyed Singapore model.
Executed only inside the existing Blender render worker.
"""
import math
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def build_environment(route, material, scene, active_progress, ground=None):
    # Road furniture follows the road center, not the corner-cutting car line.
    points=np.asarray(route.get('centerline_xy',route['xy']))
    p=np.asarray(route.get('centerline_progress',route['progress']))
    tangent=np.roll(points,-1,axis=0)-np.roll(points,1,axis=0)
    tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],1e-9)
    side=np.column_stack([-tangent[:,1],tangent[:,0]])
    elevation=route.get('elevation_profile')
    terrain=None;road_tree=None
    if ground is not None and elevation:
        terrain=BVHTree.FromPolygons([ground.matrix_world @ v.co for v in ground.data.vertices],
                                    [tuple(p.vertices) for p in ground.data.polygons])
    if elevation:
        road_tree=KDTree(len(elevation['xy']))
        for i,q in enumerate(elevation['xy']):road_tree.insert((q[0],q[1],0.),i)
        road_tree.balance()
    def ground_height(point):
        if terrain is None:return 0.
        hit,_,_,_=terrain.ray_cast(Vector((point[0],point[1],500)),Vector((0,0,-1)),1000)
        return float(hit.z) if hit is not None else 0.
    def road_height(point):
        if road_tree is None:return 0.
        _,i,_=road_tree.find((point[0],point[1],0.))
        return float(elevation['z'][i])
    road_half=7.25
    concrete=material('Night · painted concrete',(.43,.45,.44),rough=.78)
    dark=material('Night · steel',(.023,.033,.048),metallic=.65,rough=.42)
    wire=material('Night · catch fence',(.13,.17,.21),metallic=.6,rough=.4)
    cyan=material('Night · muted green barrier trim',(.025,.12,.075),rough=.65)
    lamp_mat=material('Night · floodlight panels',(.76,.87,1.),emission=9)
    buildings=material('Night · architecture',(.018,.028,.045),metallic=.25,rough=.55)
    windows=material('Night · lit windows',(.28,.31,.34),emission=1.25)
    warm=material('Night · warm windows',(.48,.36,.22),emission=1.4)
    mats=[concrete,dark,wire,cyan,lamp_mat,buildings,windows,warm]
    verts=[];faces=[];indices=[]
    def box(center,size,heading,index,base_z=0.):
        # Components in one building/lamp/gantry share one base. Sampling each
        # window or arm at a different XY would pull the rigid assembly apart.
        center=np.asarray(center,dtype=float).copy();center[2]+=base_z
        a=np.array([math.cos(heading),math.sin(heading),0.]);b=np.array([-a[1],a[0],0.])
        start=len(verts)
        for z in (-1,1):
            for y,x in ((-1,-1),(-1,1),(1,1),(1,-1)):
                verts.append((center+a*x*size[0]/2+b*y*size[1]/2+np.array([0,0,z*size[2]/2])).tolist())
        for face in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            faces.append(tuple(start+i for i in face));indices.append(index)
    def ribbon(xy,z0,z1,index):
        start=len(verts)
        for point in xy:
            z=road_height(point);verts.extend([[*point,z+z0],[*point,z+z1]])
        for i in range(len(xy)-1):faces.append((start+2*i,start+2*i+2,start+2*i+3,start+2*i+1));indices.append(index)
    distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    sample=np.searchsorted(distance,np.arange(0,distance[-1],4.))
    for sign in (-1,1):
        edge=points+side*road_half*sign
        ribbon(edge,0,1.05,0)
        ribbon(edge,.14,.32,3)
        # Fence horizontals plus dense vertical wires in a single curve object.
        curve=bpy.data.curves.new('Night catch fence','CURVE');curve.dimensions='3D';curve.bevel_depth=.012;curve.bevel_resolution=0
        def strand(coords):
            spline=curve.splines.new('POLY');spline.points.add(len(coords)-1)
            for item,co in zip(spline.points,coords):item.co=(co[0],co[1],co[2]+road_height(co),1)
        fence=edge+side*.12*sign
        for z in (1.15,1.65,2.15,2.65,3.15,3.65):strand([[*q,z] for q in fence[::4]])
        for i in sample:
            angle=math.atan2(tangent[i,1],tangent[i,0])
            box([*edge[i],2.0],(.07,.07,4.),angle,1,road_height(edge[i]))
            strand([[*fence[i],1.05],[*(fence[i]-side[i]*.3*sign),3.8]])
        obj=bpy.data.objects.new('Street circuit catch fencing',curve);scene.collection.objects.link(obj);curve.materials.append(wire)
    # No invented highway center stripe through every corner. Street furniture
    # remains illustrative until a licensed venue model is supplied.
    lamp_indices=np.searchsorted(distance,np.arange(0,distance[-1],27.))
    for j,i in enumerate(lamp_indices):
        for sign in (-1,1):
            angle=math.atan2(tangent[i,1],tangent[i,0]);base=points[i]+side[i]*9.0*sign
            fixture_base=ground_height(base)
            box([*base,5.5],(.18,.18,11.),angle,1,fixture_base)
            box([*(base-side[i]*1.5*sign),10.8],(.18,3.2,.18),angle,1,fixture_base)
            fixture=base-side[i]*3.0*sign
            box([*fixture,10.65],(2.2,.85,.16),angle,4,fixture_base)
            # Near lamps illuminate both ghosts; far lamps retain emissive panels.
            separation=np.abs(p[i]-active_progress)
            if np.min(np.minimum(separation,1-separation))*distance[-1]<150 and sign==(-1 if j%2 else 1):
                data=bpy.data.lights.new('Street floodlight','AREA');data.energy=1700;data.shape='RECTANGLE';data.size=5;data.size_y=2
                data.color=(.78,.87,1.)
                data.use_custom_distance=True;data.cutoff_distance=55
                data.use_shadow=False
                obj=bpy.data.objects.new(data.name,data);scene.collection.objects.link(obj)
                obj['race_floodlight']=True
                obj.location=(*fixture,10.4+fixture_base)
                obj.rotation_euler=(Vector((*points[i],road_height(points[i])))-obj.location).to_track_quat('-Z','Y').to_euler()
    rng=np.random.default_rng(2026)
    for block,i in enumerate(np.searchsorted(distance,np.arange(0,distance[-1],48.))):
        for sign in (-1,1):
            center=points[i]+side[i]*rng.uniform(35,92)*sign
            sx,sy=rng.uniform(12,22),rng.uniform(13,23)
            height=rng.uniform(35,80) if block%5==0 else rng.uniform(8,24)
            if np.linalg.norm(points-center,axis=1).min()<max(sx,sy)*.75+12:continue
            angle=math.atan2(tangent[i,1],tangent[i,0])
            building_base=ground_height(center)
            if elevation:
                # A buried foundation meets the lowest footprint corner on a
                # slope; it does not tilt the storeys or let the downhill wall hover.
                a=np.array([math.cos(angle),math.sin(angle)]);b=np.array([-a[1],a[0]])
                bottom=min(ground_height(center+a*x*sx/2+b*y*sy/2)
                           for x in (-1,0,1) for y in (-1,0,1))-.3
                top=building_base+.05
                if top>bottom:box([*center,(top+bottom)/2],(sx,sy,top-bottom),angle,5)
            box([*center,height/2],(sx,sy,height),angle,5,building_base)
            # Lit office rows on all four facades; seeded, reproducible scenery.
            a=np.array([math.cos(angle),math.sin(angle)]);b=np.array([-a[1],a[0]])
            for z in np.arange(4,height-1,4):
                for axis,normal,extent,other in ((a,b,sx,sy),(b,a,sy,sx)):
                    for face_sign in (-1,1):
                        if rng.random()<.25:continue
                        q=center+normal*face_sign*(other/2+.04)
                        if normal is b:box([*q,z],(extent*.78,.06,.75),angle,6 if rng.random()>.2 else 7,building_base)
                        else:box([*q,z],(.06,extent*.78,.75),angle,6 if rng.random()>.2 else 7,building_base)
    # One start-area gantry instead of three invented bridges around the lap.
    for fraction in (.005,):
        i=np.searchsorted(p,fraction);angle=math.atan2(tangent[i,1],tangent[i,0])
        gantry_base=road_height(points[i])
        box([*points[i],8.8],(2.,21.,1.4),angle,1,gantry_base)
        for sign in (-1,1):box([*(points[i]+side[i]*10*sign),4.4],(.65,.65,8.8),angle,1,gantry_base)
        curve=bpy.data.curves.new('RH bridge sign','FONT');curve.body='RACE HYPE';curve.align_x='CENTER';curve.size=1.0;curve.extrude=.005
        obj=bpy.data.objects.new(curve.name,curve);scene.collection.objects.link(obj)
        obj.location=(*points[i],8.55+gantry_base);obj.location-=Vector((*tangent[i],0))*1.03
        obj.rotation_euler=Vector((*tangent[i],0)).to_track_quat('-Z','Y').to_euler();curve.materials.append(lamp_mat)
    mesh=bpy.data.meshes.new('Original night street environment');mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(mesh.name,mesh);scene.collection.objects.link(obj)
    for mat in mats:mesh.materials.append(mat)
    for face,index in zip(mesh.polygons,indices):face.material_index=index
    return {'scenery':'Original procedural streetscape','lamps':len(lamp_indices),'mesh_faces':len(faces)}
