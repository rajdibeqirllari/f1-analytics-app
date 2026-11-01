"""Decoded scene-only cadence/optical-flow audit, excluding HUD and result holds.

No synthetic noise, frame interpolation or resampling is used. The decoder reads
each original frame; report thresholds are explicit and reproducible.
"""
import argparse
import json
from pathlib import Path
import subprocess
import cv2
import numpy as np


def audit(path, active_end=None):
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=width,height,avg_frame_rate,nb_frames:format=duration:format_tags',
        '-of','json',str(path)]))
    stream=info['streams'][0];a,b=map(int,stream['avg_frame_rate'].split('/'));fps=a/b
    cap=cv2.VideoCapture(str(path));previous=None;diffs=[];flow=[];count=0
    # Central racing image only: never count a ticking timer as scene motion.
    while True:
        ok,frame=cap.read()
        if not ok or (active_end is not None and count/fps>=active_end):break
        gray=cv2.cvtColor(cv2.resize(frame,(180,320)),cv2.COLOR_BGR2GRAY)[80:185,12:168]
        if previous is not None:
            diffs.append(float(np.abs(gray.astype(float)-previous).mean()))
            if count%5==0:
                field=cv2.calcOpticalFlowFarneback(previous,gray,None,.5,3,15,3,5,1.2,0)
                flow.append(float(np.median(np.linalg.norm(field,axis=2))))
        previous=gray;count+=1
    cap.release();d=np.asarray(diffs);median=float(np.median(d))
    threshold=min(.35,median*.12)
    repeated=np.where(d<threshold)[0]+1
    pts_info=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','frame=best_effort_timestamp_time','-of','json',str(path)]))
    pts=np.array([float(frame['best_effort_timestamp_time']) for frame in pts_info['frames']])
    intervals=np.diff(pts)
    return dict(path=str(path),fps=fps,dimensions=[stream['width'],stream['height']],
        duration=float(info['format']['duration']),analyzed_frames=count,scene_roi=[12,80,168,185],
        adjacent_scene_mad_median=median,near_duplicate_threshold=threshold,
        near_duplicate_frames=len(repeated),near_duplicate_fraction=float(len(repeated)/max(1,len(d))),
        first_repeated_indices=repeated[:45].tolist(),
        repeat_residue_mod5=np.bincount(repeated%5,minlength=5).tolist(),
        pts_interval_min=float(intervals.min()),pts_interval_max=float(intervals.max()),
        pts_max_cadence_error=float(np.max(np.abs(intervals-1/fps))),
        optical_flow_median_pixels=float(np.median(flow)) if flow else None,
        tags=info['format'].get('tags',{}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('paths',nargs='+',type=Path)
    parser.add_argument('--active-end',type=float);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=[audit(path,args.active_end) for path in args.paths]
    rendered=json.dumps(result,indent=2);print(rendered)
    if args.output:args.output.write_text(rendered,encoding='utf8')
