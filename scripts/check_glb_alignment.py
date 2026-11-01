"""Read-only alignment diagnostic; does not modify source or car timing."""
from pathlib import Path
import sys,json
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.singapore_asset import reference,aligned_reference
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
year=int(sys.argv[1]) if len(sys.argv)>1 else 2026
p=json.loads((ROOT/f'tmp/reference_review/singapore_{year}/input.json').read_text())
comparison=SimpleNamespace(year=year,track=np.asarray(p['track']))
data,profile=reference(year);xy=aligned_reference(comparison,data,profile)
distance,index=data['tree'].query(xy)
print('FIT_DISTANCE',np.percentile(distance,[0,50,90,95,100]),flush=True)
print('WORST',[(int(i),xy[i].tolist(),round(distance[i],2)) for i in np.argsort(distance)[-10:]],flush=True)
fig,ax=plt.subplots(figsize=(12,10))
ax.add_collection(PolyCollection(data['vertices'][data['triangles']][:,:,:2],facecolors='#657178',edgecolors='none'))
ax.plot(xy[:,0],xy[:,1],color='red',lw=1)
ax.scatter(xy[distance>8,0],xy[distance>8,1],s=12,color='orange');ax.autoscale();ax.axis('equal')
fig.savefig(ROOT/f'tmp/reference_review/singapore_speed/glb-alignment-{year}.png')
