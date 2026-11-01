"""Rebuilt, height-following road furniture around the adapted corridor."""
import bpy,math
import numpy as np
from mathutils import Vector


def build_furniture(route,path3,material,scene,active):
    xy=np.asarray(route.get('centerline_xy',route['xy']))
    p=np.asarray(route.get('centerline_progress',route['progress']))
    z=np.interp(p,route['progress'],path3[:,2])
    heading=np.roll(xy,-1,axis=0)-np.roll(xy,1,axis=0)
    heading/=np.maximum(np.linalg.norm(heading,axis=1)[:,None],1e-9)
    side=np.column_stack([-heading[:,1],heading[:,0]])
    distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
    steel=material('Adapted Singapore · steel',(.08,.09,.10),metallic=.7,rough=.6)
    concrete=material('Adapted Singapore · concrete',(.48,.49,.48),rough=.8)
    glow=material('Adapted Singapore · floodlights',(.88,.91,1.),emission=8)
    vertices=[];faces=[];indices=[]
    def box(center,size,angle,mat):
        start=len(vertices);a=np.array([np.cos(angle),np.sin(angle),0]);b=np.array([-a[1],a[0],0])
        for dz in (-1,1):
            for dy,dx in ((-1,-1),(-1,1),(1,1),(1,-1)):
                vertices.append((np.asarray(center)+a*dx*size[0]/2+b*dy*size[1]/2+[0,0,dz*size[2]/2]).tolist())
        for f in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            faces.append(tuple(start+j for j in f));indices.append(mat)
    for sign in (-1,1):
        curve=bpy.data.curves.new('Adapted Singapore fence','CURVE');curve.dimensions='3D';curve.bevel_depth=.014;curve.bevel_resolution=0
        edge=xy+side*7.8*sign
        for dz in (1.2,1.8,2.4,3.,3.6):
            spline=curve.splines.new('POLY');sample=np.arange(0,len(xy),4);spline.points.add(len(sample)-1)
            for item,i in zip(spline.points,sample):item.co=(*edge[i],z[i]+dz,1)
        for i in np.searchsorted(distance,np.arange(0,distance[-1],4.)):
            angle=math.atan2(heading[i,1],heading[i,0])
            box([*edge[i],z[i]+.55],(4.1,.35,1.1),angle,1)
            box([*edge[i],z[i]+2.4],(.07,.07,3),angle,0)
        obj=bpy.data.objects.new(curve.name,curve);scene.collection.objects.link(obj);curve.materials.append(steel)
    for j,i in enumerate(np.searchsorted(distance,np.arange(0,distance[-1],28.))):
        sign=1 if j%2 else -1;point=xy[i]+side[i]*9*sign;angle=math.atan2(heading[i,1],heading[i,0])
        box([*point,z[i]+5.5],(.2,.2,11),angle,0)
        fixture=point-side[i]*3*sign
        box([*(point-side[i]*1.5*sign),z[i]+10.7],(.18,3.2,.18),angle,0)
        box([*fixture,z[i]+10.7],(2.4,1,.15),angle,2)
        delta=np.abs(p[i]-active)
        if np.min(np.minimum(delta,1-delta))*distance[-1]<140:
            data=bpy.data.lights.new('Adapted floodlight','AREA');data.energy=2100;data.size=5
            data.use_custom_distance=True;data.cutoff_distance=55
            data.use_shadow=False
            obj=bpy.data.objects.new(data.name,data);scene.collection.objects.link(obj)
            obj['race_floodlight']=True
            obj.location=(*fixture,z[i]+10.5)
            obj.rotation_euler=(Vector((*xy[i],z[i]))-obj.location).to_track_quat('-Z','Y').to_euler()
    mesh=bpy.data.meshes.new('Adapted modern road furniture');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(mesh.name,mesh);scene.collection.objects.link(obj)
    for mat in (steel,concrete,glow):mesh.materials.append(mat)
    for face,index in zip(mesh.polygons,indices):face.material_index=index
    return {'scenery':'Supplied Singapore model · '+route.get('singapore_layout','adapted layout')+' · telemetry driving corridor',
            'source_provenance_verified':False,'adapted_furniture_faces':len(faces)}
