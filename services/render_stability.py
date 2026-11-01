"""Depth-stable ground geometry for EEVEE animation; no giant horizon triangles."""
import numpy as np


def ground_mesh(road_vertices, margin=1200., spacing=80.):
    road=np.asarray(road_vertices,dtype=float)
    if road.ndim!=2 or road.shape[1]!=3 or not np.isfinite(road).all():
        raise ValueError('Ground requires finite 3D road vertices.')
    lo=np.floor((road[:,:2].min(axis=0)-margin)/spacing)*spacing
    hi=np.ceil((road[:,:2].max(axis=0)+margin)/spacing)*spacing
    x=np.arange(lo[0],hi[0]+spacing*.5,spacing)
    y=np.arange(lo[1],hi[1]+spacing*.5,spacing)
    gx,gy=np.meshgrid(x,y)
    z=float(road[:,2].min())-.12
    vertices=np.column_stack([gx.ravel(),gy.ravel(),np.full(gx.size,z)])
    n=len(x)
    faces=[(j*n+i,j*n+i+1,(j+1)*n+i+1,(j+1)*n+i) for j in range(len(y)-1) for i in range(n-1)]
    return vertices.tolist(),faces
