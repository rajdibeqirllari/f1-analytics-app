"""Illustrative, shared cornering geometry, never measured driver racing lines.

The lap clocks and speed channels are not changed. Both ghosts use exactly the
same asphalt-constrained line; no driver-specific lateral advantage is invented.
"""
import numpy as np


def curvature(points):
    points=np.asarray(points,dtype=float)
    ring=points[:-1]
    before=ring-np.roll(ring,1,axis=0)
    after=np.roll(ring,-1,axis=0)-ring
    angle=np.arctan2(before[:,0]*after[:,1]-before[:,1]*after[:,0],
                     np.sum(before*after,axis=1))
    ds=(np.linalg.norm(before,axis=1)+np.linalg.norm(after,axis=1))*.5
    value=angle/np.maximum(ds,1e-6)
    return np.r_[value,value[0]]


def steering_angle(progress,points,p,wheelbase=3.4):
    """Geometric bicycle steering, not a recorded steering sensor channel."""
    bend=float(np.interp(p,progress,curvature(points)))
    return float(np.clip(np.arctan(wheelbase*bend),-np.deg2rad(25),np.deg2rad(25)))


def cornering_route(route,mesh,max_offset=2.4):
    from scipy.optimize import minimize
    from scipy.ndimage import gaussian_filter1d
    from services.driving_path import arc_route,directions,RoadGuide
    center=np.asarray(route['xy'],dtype=float)
    # Optimize at corner scale, not thousands of sub-metre offsets. The old
    # dense second-difference problem converged mostly to a centred line.
    _,coarse,_=arc_route(center,spacing=8.)
    tangent=directions(coarse)[:-1]
    side=np.column_stack([-tangent[:,1],tangent[:,0]])
    base=coarse[:-1]
    # Reduce curvature with bounded lateral movement. This gives a shared
    # corner-cutting display line rather than two rigid parallel lanes.
    def objective(offset):
        q=base+side*offset[:,None]
        second=np.roll(q,1,axis=0)-2*q+np.roll(q,-1,axis=0)
        gradient=2*(np.roll(second,1,axis=0)-2*second+np.roll(second,-1,axis=0))
        return float(np.sum(second**2)+1e-7*np.sum(offset**2)),np.sum(gradient*side,axis=1)+2e-7*offset
    result=minimize(objective,np.zeros(len(base)),jac=True,method='L-BFGS-B',
                    bounds=[(-max_offset,max_offset)]*len(base),options={'maxiter':300,'ftol':1e-12,'gtol':1e-10})
    coarse_offset=gaussian_filter1d(result.x,1.,mode='wrap')
    coarse_distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(coarse,axis=0),axis=1))]
    dense_distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(center,axis=0),axis=1))]
    offset=np.interp(dense_distance[:-1],coarse_distance,np.r_[coarse_offset,coarse_offset[0]])
    base=center[:-1]
    tangent=directions(center)[:-1]
    side=np.column_stack([-tangent[:,1],tangent[:,0]])
    vertices=np.asarray(mesh['vertices']);faces=np.asarray(mesh['faces'])
    quads=faces[np.asarray(mesh['materials'])==0]
    triangles=np.vstack([quads[:,[0,1,2]],quads[:,[0,2,3]]])
    guide=RoadGuide(vertices,triangles)
    # Tight corners constrain their own offsets, not the entire lap. Previously
    # a single hairpin reduced every other corner's excursion by the same factor.
    for _ in range(14):
        ring=base+side*offset[:,None]
        closed=np.vstack([ring,ring[0]])
        heading=directions(closed)[:-1];normal=np.column_stack([-heading[:,1],heading[:,0]])
        allowed=np.ones(len(ring),dtype=bool)
        for along in (-2.3,0.,3.):
            for lateral in (-1.15,0.,1.15):
                allowed &= guide.clearance(ring+heading*along+normal*lateral)>=.7
        if allowed.all():break
        offset[~allowed]*=.8
        offset=gaussian_filter1d(offset,2.,mode='wrap')
    # Validate the complete car body. Reduce the *whole* lateral offset if
    # needed, never snap one frame sideways onto the road.
    for factor in (1.,.8,.6,.4,.2,0.):
        ring=base+side*offset[:,None]*factor
        progress,points,length=arc_route(np.vstack([ring,ring[0]]))
        heading=directions(points);normal=np.column_stack([-heading[:,1],heading[:,0]])
        safe=all(guide.clearance(points+heading*along+normal*lateral).min()>=.65
                 for along in (-2.3,0.,3.) for lateral in (-1.15,0.,1.15))
        if safe:break
    else:raise ValueError('No safe cornering route fits the available asphalt.')
    return dict(route,progress=progress.tolist(),xy=points.tolist(),length_metres=length,
                centerline_xy=center.tolist(),centerline_progress=route['progress'],
                half_separation=[0.]*len(progress),separation_range=[0.,0.],
                cornering={'kind':'Shared illustrative minimum-curvature line',
                           'max_offset_metres':float(np.max(np.abs(offset*factor))),
                           'measured_racing_lines':False})
