"""Rigid/scale-only telemetry-to-model fit. Never warp a venue to fit a lap."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.optimize import minimize
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'tmp/reference_review/singapore_asset'
d=np.load(OUT/'meshes.npz');v=d['mesh_0'];t=d['mesh_0_triangles'];m=d['mesh_0_materials']
road=v[t[m==29]]
points=np.concatenate([road.reshape(-1,3),road.mean(axis=1)])[:,:2]
tree=cKDTree(points)
c=json.loads((ROOT/'tmp/reference_review/night_chase_singapore_input.json').read_text())
original=np.asarray(c['track'])[:,1:3];origin=original.mean(axis=0);xy=original-origin
center=(points.min(axis=0)+points.max(axis=0))/2
def rotation(angle):return np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
def mapped(params):return xy @ rotation(params[0]).T*np.exp(params[1])+params[2:]
def loss(params):
    distances=tree.query(mapped(params))[0]
    return float(np.mean(np.minimum(distances,80)**2))
best=[]
for angle in np.linspace(-np.pi,np.pi,48,endpoint=False):
    initial=np.r_[angle,0,center]
    result=minimize(loss,initial,method='Powell',bounds=[(angle-.2,angle+.2),(-.06,.06),
                    (center[0]-350,center[0]+350),(center[1]-350,center[1]+350)],
                    options={'maxiter':80,'ftol':1e-5})
    best.append((loss(result.x),result.x))
score,params=min(best,key=lambda item:item[0]);fit=mapped(params);dist=tree.query(fit)[0]
report={'parameters':params.tolist(),'telemetry_origin':origin.tolist(),'road_material':29,
        'rms_metres':float(np.sqrt(np.mean(dist**2))),'p95_metres':float(np.percentile(dist,95)),
        'max_metres':float(dist.max()),'coverage_within_6m':float(np.mean(dist<6)),
        'mapped_xy':fit.tolist()}
(OUT/'alignment_diagnostic.json').write_text(json.dumps(report,indent=2))
fig,ax=plt.subplots(figsize=(12,8));ax.scatter(points[::8,0],points[::8,1],s=.1,c='#777777',label='Model asphalt')
ax.plot(fit[:,0],fit[:,1],c='red',lw=1,label='Selected Singapore telemetry, rigid fit')
ax.scatter(fit[dist>6,0],fit[dist>6,1],c='orange',s=8,label='Outside 6 m tolerance')
ax.axis('equal');ax.legend();fig.tight_layout();fig.savefig(OUT/'alignment_diagnostic.png')
print({k:value for k,value in report.items() if k!='mapped_xy'},flush=True)
