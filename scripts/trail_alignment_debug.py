"""Optional world-space diagnostics; no geometry is projected in HUD space."""
import bpy
import numpy as np
from mathutils import Matrix


def build_debug(world_vertices,polygons,raw_points,curve_points,material,scene):
    def mesh(name,verts,faces,color):
        data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update()
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.matrix_world=Matrix.Identity(4)
        data.materials.append(material(name,color,emission=1));obj.visible_shadow=False
        return obj
    def strokes(name,pairs,width,color):
        verts=[];faces=[]
        for a,b in pairs:
            a=np.asarray(a,float).copy();b=np.asarray(b,float).copy();d=b-a
            normal=np.array([-d[1],d[0],0]);normal*=width/max(1e-9,np.linalg.norm(normal))
            i=len(verts);verts.extend([a-normal,a+normal,b+normal,b-normal]);faces.append((i,i+1,i+2,i+3))
        return mesh(name,verts,faces,color)
    edges={}
    for polygon in polygons:
        for a,b in zip(polygon,np.roll(polygon,-1)):
            key=tuple(sorted((int(a),int(b))));edges[key]=edges.get(key,0)+1
    boundary=[]
    for (a,b),count in edges.items():
        if count==1:boundary.append((world_vertices[a]+[0,0,.006],world_vertices[b]+[0,0,.006]))
    strokes('DEBUG green authoritative asphalt edges',boundary,.025,(.08,1.,.2))
    curve=np.asarray(curve_points).copy();curve[:,2]-=.035
    strokes('DEBUG cyan actual interpolated car route',zip(curve[:-1],curve[1:]),.025,(0.,.75,1.))
    verts=[];faces=[]
    for q in np.asarray(raw_points)[::10]:
        q=q.copy();q[2]-=.034;i=len(verts)
        verts.extend([q+[-.1,0,0],q+[0,.1,0],q+[.1,0,0],q+[0,-.1,0]]);faces.append((i,i+1,i+2,i+3))
    mesh('DEBUG white raw route knots (every tenth)',verts,faces,(1.,1.,1.))
    markers=[]
    for i in range(2):
        marker=strokes('DEBUG yellow car root '+str(i),[(np.array([-.25,0,1.7]),np.array([.25,0,1.7])),
            (np.array([0,-.25,1.7]),np.array([0,.25,1.7]))],.025,(1.,.85,.02))
        markers.append(marker)
    return markers
