"""Presentation-only motion/camera/trail math; never modifies source lap samples."""
import numpy as np


def ghost_lane_side(index):
    """A takes track-left, B track-right, matching cards in the rear chase view.

    Only a presentation offset; it must never change lap progress or timing.
    """
    return 1 - 2 * index


def motion_progress(samples,elapsed):
    """Integrate interpolated speed for continuous, always-forward motion.

    Matches the source progress anchors and official lap endpoints. Interpolating
    cumulative distance directly otherwise introduces velocity discontinuities.
    """
    times=np.asarray(samples['t'],dtype=float)
    speeds=np.asarray(samples['speed'],dtype=float)/3.6
    interval=np.diff(times)
    distance=np.r_[0.,np.cumsum((speeds[:-1]+speeds[1:])*.5*interval)]
    time=np.clip(elapsed,times[0],times[-1])
    index=np.clip(np.searchsorted(times,time,side='right')-1,0,len(times)-2)
    dt=time-times[index]
    acceleration=(speeds[index+1]-speeds[index])/interval[index]
    return (distance[index]+speeds[index]*dt+.5*acceleration*dt*dt)/distance[-1]


def smooth_signal(values, fps, seconds):
    """Symmetric damping for an offline render: no camera-follow phase lag."""
    values = np.asarray(values, dtype=float)
    if not len(values) or fps <= 0 or seconds <= 0 or not np.isfinite(values).all():
        raise ValueError("Camera samples must be finite and smoothing rates positive.")
    alpha = 1 - np.exp(-1 / (fps * seconds))
    padding = max(1, int(np.ceil(6 * fps * seconds)))
    padded = np.pad(values, [(padding, padding)] + [(0, 0)] * (values.ndim - 1), mode="edge")
    for index in range(1, len(padded)):
        padded[index] = padded[index - 1] + alpha * (padded[index] - padded[index - 1])
    for index in range(len(padded) - 2, -1, -1):
        padded[index] = padded[index + 1] + alpha * (padded[index] - padded[index + 1])
    return padded[padding:-padding]


def project_cars(positions, tangents, location, target, size,local_corners=None):
    """Conservative car boxes in image coordinates (bottom-left origin).

    Matches the renderer's 40 mm / 36 mm AUTO-fit camera and landscape shift.
    """
    forward=target-location
    forward/=np.linalg.norm(forward,axis=1)[:,None]
    right=np.cross(forward,np.array([0.,0.,1.]))
    right/=np.linalg.norm(right,axis=1)[:,None]
    up=np.cross(right,forward)
    heading=tangents.copy()
    if local_corners is not None:
        # Match the rendered root's Rz(yaw+pi/2) @ Rx(-road_pitch):
        # local -Y is the car nose, local X is track-left. The old proxy
        # flattened road pitch and guessed the model's longitudinal extent.
        heading/=np.linalg.norm(heading,axis=2)[:,:,None]
        horizontal=np.maximum(np.linalg.norm(heading[:,:,:2],axis=2),1e-9)
        side=np.stack([-heading[:,:,1]/horizontal,heading[:,:,0]/horizontal,np.zeros(heading.shape[:2])],axis=2)
        roof=np.cross(side,-heading)
        corners=np.asarray(local_corners,float)
        if corners.ndim!=2 or corners.shape[1]!=3 or not np.isfinite(corners).all():
            raise ValueError('Car bounds must be finite local XYZ corners.')
        world=positions[:,:,None,:]+side[:,:,None,:]*corners[None,None,:,0,None]
        world-=heading[:,:,None,:]*corners[None,None,:,1,None]
        world+=roof[:,:,None,:]*corners[None,None,:,2,None]
    else:
        world=None
    heading[:,:,2]=0
    heading/=np.linalg.norm(heading,axis=2)[:,:,None]
    side=np.stack([-heading[:,:,1],heading[:,:,0],np.zeros(heading.shape[:2])],axis=2)
    corners=np.array([[along,lateral,height] for along in (-2.3,3.)
                      for lateral in (-1.15,1.15) for height in (0.,1.5)])
    if world is None:
        world=positions[:,:,None,:]+heading[:,:,None,:]*corners[None,None,:,0,None]
        world+=side[:,:,None,:]*corners[None,None,:,1,None]
        world[:,:,:,2]+=corners[None,None,:,2]
    relative=world-location[:,None,None,:]
    depth=np.einsum('ncvi,ni->ncv',relative,forward)
    aspect=size[0]/size[1]
    half_x=.45*min(1.,aspect); half_y=.45/max(1.,aspect)
    x=.5+np.einsum('ncvi,ni->ncv',relative,right)/(2*half_x*depth)
    y=.5+np.einsum('ncvi,ni->ncv',relative,up)/(2*half_y*depth)
    if aspect>1: x+=.1
    return np.stack([x,y,depth],axis=-1)


def chase_rig(positions, tangents, fps, size=(540,960)):
    """Damped heading and framing, with a hard separation safety floor."""
    positions = np.asarray(positions, dtype=float)
    tangents = np.asarray(tangents, dtype=float)
    middle = smooth_signal(positions.mean(axis=1), fps, .075)
    heading = tangents.mean(axis=1)
    ambiguous=np.linalg.norm(heading[:,:2],axis=1)<.15
    heading[ambiguous]=tangents[ambiguous,0]
    # Unwrapping before damping avoids a full camera spin at +/- pi.
    yaw = smooth_signal(np.unwrap(np.arctan2(heading[:, 1], heading[:, 0])), fps, .24)
    direction = np.column_stack([np.cos(yaw), np.sin(yaw), np.zeros(len(yaw))])
    side = np.column_stack([-direction[:, 1], direction[:, 0], np.zeros(len(yaw))])
    separation = np.linalg.norm(positions[:, 0] - positions[:, 1], axis=1)
    required_zoom = np.maximum(1., separation / 12.)
    offset=-direction*23+side*9+np.array([0.,0.,14.])
    target = middle + direction * 2 + np.array([0., 0., 1.])
    # Both complete car boxes must fit between the telemetry panels and footer.
    limits=(.10,.90,.24,.73) if size[1]>size[0] else (.32,.93,.32,.78)
    for _ in range(60):
        projected=project_cars(positions,tangents,middle+offset*required_zoom[:,None],target,size)
        unsafe=np.any((projected[:,:,:,0]<limits[0]) | (projected[:,:,:,0]>limits[1]) |
                      (projected[:,:,:,1]<limits[2]) | (projected[:,:,:,1]>limits[3]) |
                      (projected[:,:,:,2]<=0),axis=(1,2))
        if not unsafe.any(): break
        required_zoom[unsafe]*=1.08
    else:
        raise ValueError("Could not frame both ghost cars safely.")
    zoom = smooth_signal(required_zoom, fps, .45)
    # A constant safety pad preserves damping instead of hard-clamping each
    # frame (which would reintroduce little jumps at framing thresholds).
    zoom += max(0.,float(np.max(required_zoom-zoom)))
    location = middle + offset * zoom[:, None]
    return location, target, side, zoom


def trail_opacity(sample_seconds, elapsed, lifetime=2.):
    """Reference for the shader: soft tail, no future path visible."""
    age = elapsed - np.asarray(sample_seconds, dtype=float)
    return np.where(age >= 0, np.clip(1 - age / lifetime, 0, 1) ** 2, 0.)
