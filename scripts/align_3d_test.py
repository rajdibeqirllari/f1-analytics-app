"""Fit telemetry to road geometry and output diagnostic, never silently assume alignment."""
from pathlib import Path
import json
import numpy as np
from scipy.spatial import cKDTree
from scipy.optimize import differential_evolution, minimize
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / 'tmp/reference_review'
data = json.loads((folder / 'paul_ricard_3d_input.json').read_text())
track = np.array(data['track'])
mesh = np.load(folder / 'circuit_mesh_vertices.npz')
verts, tris, mats = mesh['Plane'], mesh['Plane_triangles'], mesh['Plane_materials']
centroids = verts[tris].mean(axis=1)
print('MATERIALS', dict(zip(*np.unique(mats, return_counts=True))), 'PATH_RANGE', np.ptp(track[:,1:3], axis=0))
# Export the material geography before fitting: enables identifying road vs runoff.
fig, axes = plt.subplots(1, 2, figsize=(16, 7))
axes[0].scatter(centroids[:,0], centroids[:,1], c=mats, s=2, cmap='tab10')
axes[1].plot(track[:,1], track[:,2], color='#e83f45')
for ax in axes: ax.set_aspect('equal'); ax.grid(alpha=.2)
fig.savefig(folder / '3d_alignment_geography.png', dpi=120)
plt.close(fig)

# Asphalt triangulation samples approximate the finite road surface, not just an edge.
road_tri = verts[tris[mats == 0]]
road_points = np.concatenate([road_tri.mean(axis=1), road_tri[:,0], road_tri[:,1], road_tri[:,2]])
tree = cKDTree(road_points[:,:2])
xy = track[:,1:3]
origin = xy.mean(axis=0)
xy = xy-origin
road_center = road_points[:,:2].mean(axis=0)
def transform(params):
    angle, logscale, dx, dy = params
    rotation = np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    return xy @ rotation.T * np.exp(logscale) + road_center + [dx,dy]
def loss(params):
    distance = tree.query(transform(params))[0]
    return np.mean(np.minimum(distance, 400)**2)
# Asset extents are approximately 2.5 times telemetry metres. Constrain scale so
# an optimizer cannot shrink an entire lap into a small patch of asphalt.
result = differential_evolution(loss, [(-np.pi,np.pi),(.75,1.15),(-1000,1000),(-1000,1000)],
                                seed=7, maxiter=170, popsize=18, tol=.0001)
mapped = transform(result.x)
dist, nearest = tree.query(mapped)
payload = {'parameters': result.x.tolist(), 'telemetry_origin': origin.tolist(),
           'road_origin': road_center.tolist(), 'rms_road_sample_distance': float(np.sqrt(np.mean(dist**2))),
           'p95_road_sample_distance': float(np.percentile(dist,95)),
           'max_road_sample_distance': float(dist.max()), 'mapped_xy': mapped.tolist()}
(folder/'3d_alignment.json').write_text(json.dumps(payload,indent=2))
fig,ax = plt.subplots(figsize=(10,10))
ax.scatter(road_points[:,0],road_points[:,1],s=1,color='#697984')
ax.plot(mapped[:,0],mapped[:,1],color='#ff3e47',linewidth=1)
ax.scatter(*mapped[0],color='lime',s=40)
ax.set_aspect('equal'); ax.set_title(f'Road/telemetry fit RMS {payload["rms_road_sample_distance"]:.2f} model units')
fig.savefig(folder/'3d_alignment_fit.png',dpi=150)
print(json.dumps({k:v for k,v in payload.items() if k!='mapped_xy'},indent=2))
