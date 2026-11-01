"""One deterministic source clock for all scene and HUD consumers."""
import math
import numpy as np
from services.video_timeline import validate_playback_speed, frame_count

PACING_MODES=('Constant','Dynamic cinematic')


def validate_options(pacing='Constant',target_duration=35,camera_options=None):
    if pacing not in PACING_MODES:raise ValueError('Choose Constant or Dynamic cinematic pacing.')
    try:duration=float(target_duration)
    except (TypeError,ValueError):raise ValueError('Target duration must be between 30 and 40 seconds.') from None
    if isinstance(target_duration,bool) or not math.isfinite(duration) or not 30<=duration<=40:
        raise ValueError('Target duration must be between 30 and 40 seconds.')
    if camera_options is not None and not isinstance(camera_options,dict):raise ValueError('Camera adjustments must be an object.')
    defaults=dict(smoothness=.55,lookahead=.35,zoom=1.,dynamic_zoom=.35,intensity=.35,framing=1.)
    limits=dict(smoothness=(.15,1.2),lookahead=(0.,1.),zoom=(.75,1.5),dynamic_zoom=(0.,1.),intensity=(0.,1.),framing=(.75,1.3))
    for key,value in (camera_options or {}).items():
        if key not in defaults:raise ValueError('Unknown camera adjustment: '+key)
        try:numeric=float(value)
        except (TypeError,ValueError):raise ValueError('Camera adjustment out of range: '+key) from None
        if isinstance(value,bool) or not math.isfinite(numeric) or not limits[key][0]<=numeric<=limits[key][1]:
            raise ValueError('Camera adjustment out of range: '+key)
        defaults[key]=float(value)
    return defaults


def cinematic_timeline(comparison,start,end,fps,speed=3,pacing='Constant',target_duration=35,full=False):
    from scipy.ndimage import gaussian_filter1d
    validate_options(pacing,target_duration);speed=validate_playback_speed(speed)
    if fps not in (24,30,60):raise ValueError('Choose 24, 30 or 60 fps.')
    if pacing=='Constant':
        count=frame_count(start,end,fps,speed,hold=full)
        raw=start+np.arange(count)*speed/fps
        return dict(source_times=np.minimum(end,raw).tolist(),trail_times=raw.tolist(),
                    pacing=pacing,action_seconds=(end-start)/speed,output_seconds=count/fps,fps=fps)
    # Allocate more output time to measured braking, close gaps and advantage
    # changes. Integration/inversion stays strictly monotone for both drivers.
    source=np.linspace(0,comparison.duration,int(np.ceil(comparison.duration*120))+1)
    a,b=comparison.laps
    def channel(lap,key):return np.interp(source,lap.samples.t,lap.samples[key])
    pa,pb=channel(a,'progress'),channel(b,'progress');p=np.minimum(pa,pb)
    delta=np.interp(p,b._distance_progress,b._distance_times)-np.interp(p,a._distance_progress,a._distance_times)
    braking=np.maximum(channel(a,'brake'),channel(b,'brake'))
    speed_kmh=(channel(a,'speed')+channel(b,'speed'))/2
    changes=np.abs(np.gradient(delta,source))
    interest=.55*braking+.30*np.exp(-np.abs(delta)/.12)+.45*np.clip(changes/.07,0,1)
    interest+=.2*np.clip((190-speed_kmh)/140,0,1)
    density=gaussian_filter1d(1+interest,120*.65,mode='nearest')
    cumulative=np.r_[0.,np.cumsum((density[:-1]+density[1:])*.5*np.diff(source))]
    full_action=float(target_duration)-2-1/fps
    clock=cumulative/cumulative[-1]*full_action
    first,last=np.interp([start,end],source,clock);action=last-first
    count=int(np.ceil(action*fps))+(1+2*fps if full else 0)
    output=np.arange(count)/fps
    source_times=np.interp(np.minimum(first+output,last),clock,source)
    end_rate=(source[-1]-source[-2])/(clock[-1]-clock[-2])
    trail_times=source_times+np.maximum(0,output-action)*end_rate
    return dict(source_times=source_times.tolist(),trail_times=trail_times.tolist(),pacing=pacing,
                action_seconds=float(action),output_seconds=count/fps,fps=fps)
