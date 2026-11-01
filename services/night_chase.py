"""Presentation math for a close rear camera. Source telemetry stays untouched."""
import numpy as np
from scripts.cinematic_math import smooth_signal, project_cars


def night_chase_rig(positions, tangents, fps, size=(540,960), focus=0):
    if focus not in (0,1):
        raise ValueError('Choose driver A or B for the chase camera.')
    positions=np.asarray(positions,dtype=float)
    tangents=np.asarray(tangents,dtype=float)
    anchor=smooth_signal(positions[:,focus],fps,.055)
    actual=np.unwrap(np.arctan2(tangents[:,focus,1],tangents[:,focus,0]))
    # A little heading follow-through makes the car's turn-in visible instead
    # of rotating the entire world in perfect lockstep with its nose.
    yaw=actual.copy();alpha=1-np.exp(-1/(fps*.32))
    for i in range(1,len(yaw)):
        yaw[i]=yaw[i-1]+alpha*(actual[i]-yaw[i-1])
        yaw[i]=np.clip(yaw[i],actual[i]-np.deg2rad(14),actual[i]+np.deg2rad(14))
    direction=np.column_stack([np.cos(yaw),np.sin(yaw),np.zeros(len(yaw))])
    side=np.column_stack([-direction[:,1],direction[:,0],np.zeros(len(yaw))])
    offset=-direction*10.8+np.array([0.,0.,4.3])
    forward=np.column_stack([np.cos(actual),np.sin(actual),np.zeros(len(actual))])
    target=anchor+forward*6.5+np.array([0.,0.,.85])
    zoom=np.ones(len(anchor))
    # This camera follows one chosen driver, like a racing-game chase camera.
    # The other ghost may leave the view; its location remains on the mini-map.
    selected=positions[:,focus:focus+1]
    heading=tangents[:,focus:focus+1]
    limits=(.27,.92,.16,.66) if size[1]>size[0] else (.28,.94,.15,.77)
    for _ in range(45):
        projected=project_cars(selected,heading,anchor+offset*zoom[:,None],target,size)
        unsafe=np.any((projected[:,:,:,0]<limits[0])|(projected[:,:,:,0]>limits[1])|
                      (projected[:,:,:,1]<limits[2])|(projected[:,:,:,1]>limits[3])|
                      (projected[:,:,:,2]<=0),axis=(1,2))
        if not unsafe.any():break
        zoom[unsafe]*=1.06
    else:raise ValueError('Could not frame the selected chase car.')
    damped=smooth_signal(zoom,fps,.25)
    damped+=max(0.,float(np.max(zoom-damped)))
    return anchor+offset*damped[:,None],target,side,damped
