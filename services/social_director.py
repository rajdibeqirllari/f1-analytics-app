"""Deterministic multi-angle editorial camera; never changes racing data."""
import numpy as np
from scripts.cinematic_math import smooth_signal,project_cars


def director_rig(positions,tangents,fps,size=(540,960),times=None,playback_speed=1.):
    positions=np.asarray(positions,dtype=float);tangents=np.asarray(tangents,dtype=float)
    if positions.ndim!=3 or positions.shape[1:]!=(2,3) or not len(positions) or not np.isfinite(positions).all():
        raise ValueError('Director needs two finite car poses per frame.')
    if tangents.shape!=positions.shape or not np.isfinite(tangents).all() or fps<=0 or playback_speed<=0:
        raise ValueError('Director needs finite matching headings and positive timing rates.')
    n=len(positions)
    if times is None:times=np.arange(n)/fps*playback_speed
    editorial=np.asarray(times)/playback_speed
    if editorial.shape!=(n,) or not np.isfinite(editorial).all() or np.any(np.diff(editorial)<0):
        raise ValueError('Director source times must be finite and ordered.')
    center=positions.mean(axis=1)
    heading=tangents.mean(axis=1)
    weak=np.linalg.norm(heading[:,:2],axis=1)<.15;heading[weak]=tangents[weak,0]
    actual=np.unwrap(np.arctan2(heading[:,1],heading[:,0]))
    # Anticipate the next few output frames, then ease heading changes. The
    # camera never has to whip around solely to match an accelerated hairpin.
    lookahead=np.interp(np.arange(n)+fps*.10,np.arange(n),actual)
    yaw=smooth_signal(actual*.6+lookahead*.4,fps,.18)
    max_step=np.deg2rad(110)/fps
    for i in range(1,n):yaw[i]=yaw[i-1]+np.clip(yaw[i]-yaw[i-1],-max_step,max_step)
    forward=np.column_stack([np.cos(yaw),np.sin(yaw),np.zeros(n)])
    side=np.column_stack([-forward[:,1],forward[:,0],np.zeros(n)])
    turn_rate=np.abs(np.gradient(actual))*fps if n>1 else np.zeros(n)
    # Hold the current viewpoint longer through fast turns, changing angles on
    # calmer stretches. Output-time cadence works at 1x and accelerated speeds.
    pace=np.clip(1/(1+turn_rate**2*1.6),.35,1.)
    clock=editorial[0]+np.r_[0.,np.cumsum(np.diff(editorial)*(pace[:-1]+pace[1:])*.5)]
    shots=np.array([[-21,-11,23],[-12,18,16],[-9,6,34],[-18,-15,16]],dtype=float)
    phase=clock/5.;index=np.floor(phase).astype(int)
    transition=np.clip((phase%1-.64)/.36,0,1)
    # Quintic easing has zero velocity and acceleration at the ends of a shot.
    blend=transition**3*(10-15*transition+6*transition**2)
    current=shots[index%len(shots)];following=shots[(index+1)%len(shots)]
    a=np.arctan2(current[:,1],current[:,0]);b=np.arctan2(following[:,1],following[:,0])
    angle=a+np.arctan2(np.sin(b-a),np.cos(b-a))*blend
    radius=np.linalg.norm(current[:,:2],axis=1)*(1-blend)+np.linalg.norm(following[:,:2],axis=1)*blend
    # Follow an orbital arc, not a straight line that cuts across the cars.
    offset=np.column_stack([np.cos(angle)*radius,np.sin(angle)*radius,
                            current[:,2]*(1-blend)+following[:,2]*blend])
    world_offset=forward*offset[:,0,None]+side*offset[:,1,None]+np.array([0,0,1])*offset[:,2,None]
    travel=np.linalg.norm(np.gradient(center,axis=0),axis=1)*fps/playback_speed if n>1 else np.zeros(n)
    lead=np.clip(travel*.025,.4,2.)/(1+turn_rate*.65)
    target=center+forward*lead[:,None]+np.array([0,0,.7])
    separation=np.linalg.norm(positions[:,0]-positions[:,1],axis=1)
    zoom=np.maximum(1.,separation/13.)
    portrait=size[1]>size[0]
    limits=(.12,.86,.41,.77) if portrait else (.15,.85,.43,.77)
    for _ in range(65):
        projected=project_cars(positions,tangents,center+world_offset*zoom[:,None],target,size)
        if not portrait:projected[:,:,:,0]-=.1
        projected[:,:,:,1]+=.10*max(1.,size[0]/size[1])
        unsafe=np.any((projected[:,:,:,0]<limits[0])|(projected[:,:,:,0]>limits[1])|
            (projected[:,:,:,1]<limits[2])|(projected[:,:,:,1]>limits[3])|
            (projected[:,:,:,2]<=0),axis=(1,2))
        if not unsafe.any():break
        zoom[unsafe]*=1.07
    else:raise ValueError('Director could not safely frame both cars.')
    smoothed=smooth_signal(zoom,fps,.30)
    smoothed+=max(0.,float(np.max(zoom-smoothed)))
    return center+world_offset*smoothed[:,None],target,side,smoothed
