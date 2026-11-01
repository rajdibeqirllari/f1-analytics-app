"""Same-input old/new rig comparison; excludes finish holds, not racing data."""
import argparse
import json
from pathlib import Path
import numpy as np
from services.social_director import director_rig


def metrics(location,target,zoom,fps):
    direction=target-location;direction/=np.linalg.norm(direction,axis=1)[:,None]
    angular=np.degrees(np.arccos(np.clip(np.sum(direction[1:]*direction[:-1],axis=1),-1,1)))*fps
    jerk=np.linalg.norm(np.diff(location,n=3,axis=0),axis=1)*fps**3
    return dict(max_position_step_metres=float(np.linalg.norm(np.diff(location,axis=0),axis=1).max()),
                angular_speed_p95_degrees_per_second=float(np.percentile(angular,95)),
                angular_speed_max_degrees_per_second=float(angular.max()),
                jerk_p95_metres_per_output_second_cubed=float(np.percentile(jerk,95)),
                jerk_max_metres_per_output_second_cubed=float(jerk.max()),
                max_zoom_step=float(np.abs(np.diff(zoom)).max()))


def audit(path,fps):
    data=np.load(path);times=data['source_times'];moving=np.r_[True,np.diff(times)>1e-10]
    positions=data['positions'][moving];tangents=data['tangents'][moving];times=times[moving]
    before=director_rig(positions,tangents,fps,times=times,playback_speed=3)
    old=metrics(before[0],before[1],before[3],fps)
    new=metrics(data['location'][moving],data['target'][moving],data['zoom'][moving],fps)
    return dict(method='Same real car poses and output timestamps; old Social director vs new cinematic rig. Not a measurement of the old encoded camera.',
                fps=fps,active_frames=len(times),nonadvancing_source_timestamps=int(np.sum(np.diff(times)<=0)),
                repeated_car_pose_steps=int(np.sum(np.linalg.norm(np.diff(positions,axis=0),axis=(1,2))<1e-8)),
                max_source_step_seconds=float(np.diff(times).max()),min_source_step_seconds=float(np.diff(times).min()),
                before=old,after=new,jerk_p95_reduction_percent=100*(1-new['jerk_p95_metres_per_output_second_cubed']/old['jerk_p95_metres_per_output_second_cubed']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('path',type=Path);p.add_argument('--fps',type=int,default=60);p.add_argument('--output',type=Path)
    args=p.parse_args();result=json.dumps(audit(args.path,args.fps),indent=2);print(result)
    if args.output:args.output.write_text(result,encoding='utf8')
