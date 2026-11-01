"""Compare decoded source frames against the suspected rate-converted export."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np


def read(path,seconds):
    cap=cv2.VideoCapture(str(path));fps=cap.get(cv2.CAP_PROP_FPS);frames=[]
    for _ in range(int(seconds*fps)):
        ok,frame=cap.read()
        if not ok:break
        gray=cv2.cvtColor(cv2.resize(frame,(180,320)),cv2.COLOR_BGR2GRAY)
        frames.append(gray[80:185,12:168].astype(np.int16))
    cap.release();return fps,np.array(frames)


def compare(source,export,seconds=10):
    source_fps,a=read(source,seconds);export_fps,b=read(export,seconds)
    expected=np.floor(np.arange(len(b))*source_fps/export_fps+1e-9).astype(int)
    valid=expected<len(a);expected=expected[valid];b=b[valid]
    candidates=np.clip(expected[:,None]+np.arange(-2,3),0,len(a)-1)
    errors=np.mean(np.abs(b[:,None]-a[candidates]),axis=(2,3))
    minimum=np.min(errors,axis=1)
    # Edge clipping can make several candidates the same first/last frame.
    matches=np.isclose(errors[:,2],minimum,atol=.00001)
    return dict(source=str(source),export=str(export),source_fps=source_fps,export_fps=export_fps,
        frames_compared=len(b),expected_mapping='source_index=floor(export_index*source_fps/export_fps)',
        matching_frames=int(matches.sum()),matching_fraction=float(matches.mean()),
        expected_match_scene_mad_median=float(np.median(errors[:,2])),
        neighbour_scene_mad_median=float(np.median(np.c_[errors[:,:2],errors[:,3:]])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('export',type=Path)
    p.add_argument('--output',type=Path);args=p.parse_args()
    result=json.dumps(compare(args.source,args.export),indent=2);print(result)
    if args.output:args.output.write_text(result,encoding='utf8')
