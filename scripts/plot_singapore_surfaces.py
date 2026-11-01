"""Diagnostic geometry plots for road material identification and calibration."""
import numpy as np,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'tmp/reference_review/singapore_asset'
d=np.load(OUT/'meshes.npz');v=d['mesh_0'];t=d['mesh_0_triangles'];m=d['mesh_0_materials']
tri=v[t];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(n,axis=1)
horizontal=(np.abs(n[:,2])>.97*length)&(tri[:,:,2].mean(axis=1)<55)
fig,axes=plt.subplots(2,3,figsize=(15,10))
for ax,index in zip(axes.flat,[29,30,179,180,182,183]):
    polys=tri[(m==index)&horizontal,:,:2]
    ax.add_collection(PolyCollection(polys,facecolor='#777777',edgecolor='none'))
    ax.autoscale();ax.set_aspect('equal');ax.set_title(f'Material {index}')
fig.tight_layout();fig.savefig(OUT/'road_materials.png');plt.close(fig)
