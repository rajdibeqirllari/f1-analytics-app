"""Predictive, continuous broadcast-drone framing without editorial cuts."""
import numpy as np
from scripts.cinematic_math import smooth_signal,project_cars
from services.cinematic_timeline import validate_options


def damp(values,fps,seconds):
    # Two zero-phase exponential passes are a critically-damped equivalent
    # offline filter: continuous momentum without accumulating follow lag.
    return smooth_signal(smooth_signal(values,fps,seconds*.55),fps,seconds*.55)


def maximum_filter1d(values,size,mode='nearest'):
    # Blender ships NumPy, not SciPy; keep the scene script self-contained.
    padded=np.pad(values,(size//2,size//2),mode='edge')
    return np.lib.stride_tricks.sliding_window_view(padded,size).max(axis=-1)


def cinematic_ghost_rig(positions,tangents,fps,size=(540,960),options=None,overhead=False,telemetry=None,local_corners=None):
    settings=validate_options(camera_options=options)
    positions=np.asarray(positions,float);tangents=np.asarray(tangents,float)
    if positions.ndim!=3 or positions.shape[1:]!=(2,3) or tangents.shape!=positions.shape or not len(positions) or not np.isfinite(positions).all() or not np.isfinite(tangents).all():
        raise ValueError('Cinematic camera needs two finite poses/headings per frame.')
    n=len(positions);smooth=settings['smoothness'];intensity=settings['intensity']
    center=positions.mean(axis=1)
    anchor=damp(center,fps,smooth*.23)
    heading=tangents.mean(axis=1);weak=np.linalg.norm(heading[:,:2],axis=1)<.15;heading[weak]=tangents[weak,0]
    yaw=np.unwrap(np.arctan2(heading[:,1],heading[:,0]))
    prediction=np.interp(np.arange(n)+fps*settings['lookahead']*.45,np.arange(n),yaw)
    yaw=damp(.55*yaw+.45*prediction,fps,smooth)
    forward=np.column_stack([np.cos(yaw),np.sin(yaw),np.zeros(n)])
    side=np.column_stack([-forward[:,1],forward[:,0],np.zeros(n)])
    turn=np.gradient(yaw)*fps if n>1 else np.zeros(n)
    turn=damp(np.tanh(turn*.7),fps,.5)
    separation=np.linalg.norm(positions[:,0]-positions[:,1],axis=1)
    # Tiny angle adjustments follow the corner; never spin or swap sides.
    radius=(23-2.5*settings['dynamic_zoom']*np.abs(turn))*settings['zoom']/settings['framing']
    if telemetry is not None:
        braking=damp(np.asarray(telemetry['braking'],float),fps,.45)
        high_speed=damp(np.clip((np.asarray(telemetry['speed'],float)-240)/100,0,1),fps,.55)
        radius+=(1.5*high_speed-1.2*braking)*settings['dynamic_zoom']
    offset=-forward*radius[:,None]+side*(9+turn*3*intensity)[:,None]
    offset[:,2]=18-2*np.abs(turn)*settings['dynamic_zoom']
    if overhead:offset=(-forward*9+side*4+np.array([0,0,34.]))*settings['zoom']/settings['framing']
    offset=damp(offset,fps,smooth*.45)
    target=anchor+forward*(1.2+settings['lookahead']*3.2)+[0,0,.8]
    zoom=np.maximum(1.,separation/14.)
    # An interior margin protects against float32 projection/keyframe rounding;
    # the final exact Blender check retains its original HUD boundaries.
    portrait=size[1]>size[0];limits=(.12,.88,.395,.765) if portrait else (.13,.87,.415,.765)
    def unsafe(z):
        q=project_cars(positions,tangents,anchor+offset*z[:,None],target,size,local_corners=local_corners)
        if not portrait:q[:,:,:,0]-=.1
        q[:,:,:,1]+=.1*max(1.,size[0]/size[1])
        return np.any((q[:,:,:,0]<limits[0])|(q[:,:,:,0]>limits[1])|(q[:,:,:,1]<limits[2])|
                      (q[:,:,:,1]>limits[3])|(q[:,:,:,2]<=0),axis=(1,2))
    for _ in range(80):
        bad=unsafe(zoom)
        if not bad.any():break
        zoom[bad]*=1.045
    else:raise ValueError('Cannot safely frame both cars with this camera.')
    # Anticipatory local envelope: a distant ghost does not force the entire
    # lap to use the single widest zoom, unlike a global correction.
    envelope=maximum_filter1d(zoom,size=max(3,int(fps*.8)|1),mode='nearest')
    for _ in range(12):
        eased=damp(envelope,fps,.22)
        deficit=np.maximum(zoom-eased,0)
        if deficit.max()<1e-7:break
        envelope+=maximum_filter1d(deficit,size=max(3,int(fps*.8)|1),mode='nearest')*1.02
    eased=np.maximum(eased,zoom)  # hard framing safety wins over cosmetic zoom
    return anchor+offset*eased[:,None],target,side,eased
