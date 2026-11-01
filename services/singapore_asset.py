"""Unmodified, year-selected Singapore GLBs; telemetry moves cars, not roads.

Not surveyed year-specific replicas. Source asset provenance is unverified; never serve
the source files from Streamlit or label their commercial rights as cleared.
"""
from pathlib import Path
from functools import lru_cache
import json
import numpy as np
from scipy.spatial import cKDTree
from scipy.optimize import minimize
from services.driving_path import RoadGuide

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'assets/3d/circuits/singapore'
CALIBRATION=ROOT/'assets/3d/circuits/marina-bay-street-circuit/prepared/profile.json'
SOURCE_URL='https://sketchfab.com/3d-models/marina-bay-street-circuit-e665d831c57546609d4c15287a6107b7'
CREDIT='Track: Dave (@Tyler_Dave) · listed CC BY 4.0 · GLB geometry/materials unchanged; provenance unverified'


def layout_for(year):
    """One year boundary shared by UI, preview, export and asset preparation."""
    modern=int(year)>=2023
    filename='singapore-2023.glb' if modern else 'singapore.glb'
    prepared=FOLDER/'prepared'/('source-2023-onward' if modern else 'source-pre-2023')
    return {'key':'2023-onward' if modern else 'pre-2023',
            'label':'2023+ layout' if modern else 'Pre-2023 layout',
            'source':FOLDER/filename,'environment':FOLDER/filename,
            'reference':prepared/'road_reference.npz','profile':prepared/'profile.json'}


# Compatibility for local diagnostic scripts written for the modern model.
ENVIRONMENT=layout_for(2023)['environment']
REFERENCE=layout_for(2023)['reference']
PROFILE=layout_for(2023)['profile']


def available(year,event):
    if event!='Singapore Grand Prix':return False
    layout=layout_for(year)
    if not all(layout[key].is_file() for key in ('source','environment','reference','profile')):return False
    try:
        profile=json.loads(layout['profile'].read_text())
        stat=layout['source'].stat()
        return (profile.get('mode')=='unmodified-glb' and profile['source_size']==stat.st_size
                and profile['source_mtime_ns']==stat.st_mtime_ns)
    except (OSError,ValueError,KeyError):return False


@lru_cache(maxsize=4)
def _reference(path,profile_path,reference_modified,profile_modified):
    with np.load(path) as d:
        data={key:d[key].copy() for key in d.files}
    data['tree']=cKDTree(data['points'][:,:2])
    data['guide']=RoadGuide(data['vertices'],data['triangles'])
    return data,json.loads(Path(profile_path).read_text())


def reference(year):
    layout=layout_for(year)
    return _reference(str(layout['reference']),str(layout['profile']),
                      layout['reference'].stat().st_mtime_ns,layout['profile'].stat().st_mtime_ns)


def aligned_reference(comparison,data,profile):
    tree=data['tree']
    original=np.asarray(comparison.track,dtype=float)
    origin=np.asarray(profile['telemetry_origin']);initial=np.asarray(profile['parameters'])
    xy=original[:,1:3]-origin
    def mapped(params):
        a=params[0];r=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
        return xy @ r.T*np.exp(params[1])+params[2:]
    def loss(params):
        distances=tree.query(mapped(params))[0]
        # Trim telemetry outliers without warping either era's venue geometry.
        return float(np.mean(np.sort(distances**2)[:int(len(distances)*.9)]))
    bounds=[(initial[0]-.025,initial[0]+.025),(initial[1]-.015,initial[1]+.015),
            (initial[2]-18,initial[2]+18),(initial[3]-18,initial[3]+18)]
    result=minimize(loss,initial,method='Powell',bounds=bounds,options={'maxiter':35,'ftol':1e-5})
    params=result.x if loss(result.x)<loss(initial) else initial
    fitted=mapped(params);distances=tree.query(fitted)[0]
    if np.percentile(distances,90)>12 or np.mean(distances<12)<.88:
        raise ValueError('This session cannot be aligned safely with the original Singapore GLB. The track was not changed; choose another lap or use 2D.')
    return fitted


def model_route(comparison,*,overlap=True):
    year=getattr(comparison,'year',2023)
    layout=layout_for(year)
    data,profile=reference(year)
    fitted=aligned_reference(comparison,data,profile)
    # Constrain only the animated car route to existing model asphalt. No road
    # mesh, kerbs, barriers, ground, scenery or replacement width is generated.
    route=data['guide'].route(fitted,max_separation=0. if overlap else 1.25,max_correction=35.)
    route.update(source_glb=str(layout['source']),unmodified_glb=True,
                 source_model=str(layout['source']),singapore_layout=layout['label'],
                 environment_credit=CREDIT,environment_source=SOURCE_URL,
                 adaptation=layout['label']+' · '+layout['source'].name+' · unmodified GLB track/scenery',
                 provenance_verified=False)
    return route
