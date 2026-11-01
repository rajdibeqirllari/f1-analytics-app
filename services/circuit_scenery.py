"""Lightweight venue-inspired scenery plans, not surveyed circuit replicas.

All decoration is original. Road geometry and telemetry motion are untouched.
Objects are kept clear of every part of the circuit, including nearby hairpins.
"""
import numpy as np
from scipy.spatial import cKDTree

VERSION = 'venue-surroundings-v11-telemetry-relative-elevation'


def scenery_profile(event):
    if event in ('Australian Grand Prix', 'Canadian Grand Prix'):
        return dict(kind='parkland', ground=(.115,.145,.072), trees=650,
                    lake=event=='Australian Grand Prix', skyline=True, runoff=(.25,.26,.24))
    if event in ('Belgian Grand Prix','Emilia Romagna Grand Prix','German Grand Prix',
                 'Eifel Grand Prix','Austrian Grand Prix','Styrian Grand Prix'):
        return dict(kind='woodland',ground=(.10,.13,.055),trees=850,lake=False,
                    skyline=False,runoff=(.38,.32,.22))
    if event in ('Bahrain Grand Prix','Sakhir Grand Prix','Qatar Grand Prix','Abu Dhabi Grand Prix'):
        return dict(kind='desert',ground=(.42,.34,.22),trees=35,lake=False,
                    skyline=False,runoff=(.40,.36,.29))
    if event in ('Singapore Grand Prix','Monaco Grand Prix','Azerbaijan Grand Prix','Las Vegas Grand Prix'):
        return dict(kind='city',ground=(.18,.18,.17),trees=65,lake=False,
                    skyline=True,runoff=(.22,.23,.23))
    if event in ('Saudi Arabian Grand Prix','Miami Grand Prix'):
        return dict(kind='coastal',ground=(.30,.30,.19),trees=100,lake=False,
                    skyline=True,runoff=(.31,.32,.30))
    return dict(kind='circuit',ground=(.17,.18,.075),trees=270,lake=False,
                skyline=False,runoff=(.39,.34,.24))


def scenery_plan(route, event):
    points=np.asarray(route.get('centerline_xy',route['xy']),dtype=float)
    points=points[np.r_[True,np.linalg.norm(np.diff(points,axis=0),axis=1)>1e-6]]
    if len(points)<10 or not np.isfinite(points).all():
        raise ValueError('Scenery requires a finite circuit centerline.')
    profile=scenery_profile(event)
    tree=cKDTree(points)
    elevation=route.get('elevation_profile',{})
    road_heights=np.zeros(len(points));terrain_height=lambda xy:0.
    if elevation.get('metadata',{}).get('status')=='telemetry-estimated':
        from scipy.interpolate import LinearNDInterpolator
        from services.procedural_circuit import strip_mesh,terrain_mesh
        source=np.asarray(elevation['xy']);z=np.asarray(elevation['z'])
        road_heights=z[cKDTree(source).query(points)[1]]
        # Same deterministic mesh as the render terrain: tree/stand bases must
        # touch the actual triangulated ground, not a different height estimate.
        terrain=terrain_mesh(strip_mesh(source,half_width=float(route.get('road_half_width',6.)),heights=z))
        vertices=np.asarray(terrain['vertices']);sample=LinearNDInterpolator(vertices[:,:2],vertices[:,2])
        def terrain_height(xy):
            value=float(np.asarray(sample(np.asarray(xy))).reshape(-1)[0])
            return value if np.isfinite(value) else float(z[cKDTree(source).query(xy)[1]])-.18
    tangent=np.roll(points,-1,axis=0)-np.roll(points,1,axis=0)
    tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],1e-9)
    normals=np.column_stack([-tangent[:,1],tangent[:,0]])
    distances=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    # Stable seed, independent of Python hash randomisation and render range.
    rng=np.random.default_rng(sum((i+1)*ord(c) for i,c in enumerate(event)))
    half=float(route.get('road_half_width',6.))
    lake=None
    if profile['lake']:
        # Select a clear infield pocket, never put a decorative lake over asphalt.
        from matplotlib.path import Path
        lo=points.min(axis=0);hi=points.max(axis=0)
        gx,gy=np.meshgrid(np.linspace(lo[0],hi[0],35),np.linspace(lo[1],hi[1],35))
        candidates=np.column_stack([gx.ravel(),gy.ravel()])
        candidates=candidates[Path(points).contains_points(candidates)]
        if len(candidates):
            clear=tree.query(candidates)[0];best=int(np.argmax(clear))
            radius=min(95.,float(clear[best])-half-18)
            if radius>32:lake=dict(center=candidates[best].tolist(),radius=radius,
                                   base_z=terrain_height(candidates[best]))
    trees=[]
    for _ in range(profile['trees']*5):
        if len(trees)>=profile['trees']:break
        i=int(rng.integers(len(points)));sign=int(rng.choice([-1,1]))
        center=points[i]+normals[i]*sign*rng.uniform(20,145)
        radius=float(rng.uniform(3.2,6.0));height=float(rng.uniform(8,16))
        if tree.query(center)[0]<half+radius+7:continue
        if lake and np.linalg.norm(center-np.array(lake['center']))<lake['radius']+radius+5:continue
        trees.append(dict(center=center.tolist(),radius=radius,height=height,tone=int(rng.integers(3)),
                          base_z=terrain_height(center)))
    structures=[]
    for fraction in (.015,.28,.58,.80):
        i=min(len(points)-1,int(np.searchsorted(distances,distances[-1]*fraction)))
        for sign in (-1,1):
            center=points[i]+normals[i]*sign*32
            # A circular footprint bound covers the complete grandstand/roof.
            if tree.query(center)[0]<half+23:continue
            structures.append(dict(center=center.tolist(),heading=float(np.arctan2(tangent[i,1],tangent[i,0])),
                                   kind='stand',base_z=terrain_height(center)))
    if profile['skyline']:
        for i in np.linspace(0,len(points)-1,45).astype(int):
            center=points[i]+normals[i]*rng.choice([-1,1])*rng.uniform(250,600)
            if tree.query(center)[0]<100:continue
            structures.append(dict(center=center.tolist(),heading=0.,kind='building',
                height=float(rng.uniform(15,65)),width=float(rng.uniform(13,30)),base_z=terrain_height(center)))
    if elevation.get('metadata',{}).get('status')=='telemetry-estimated':
        for item in structures:
            angle=item['heading'];a=np.array([np.cos(angle),np.sin(angle)])
            b=np.array([-a[1],a[0]]);center=np.asarray(item['center'])
            width=item.get('width',30.);depth=width*.7 if item['kind']=='building' else 9.
            item['foundation_bottom_z']=min(terrain_height(center+a*x*width/2+b*y*depth/2)
                for x in (-1,0,1) for y in (-1,0,1))-.3
    return dict(profile=profile,points=points.tolist(),normals=normals.tolist(),distances=distances.tolist(),
                heights=road_heights.tolist(),trees=trees,lake=lake,structures=structures,road_half=half,version=VERSION)
