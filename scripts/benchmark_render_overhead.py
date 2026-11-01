"""Measure CPU-only locator optimization, requiring byte-identical compositions."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import time
import json
import numpy as np
from PIL import Image,ImageDraw,ImageColor
from services.video_minimap import TrackMap
from services.video_3d_overlay import font
from test_video_comparison import comparison_fixture
from scripts.cinematic_math import motion_progress,ghost_lane_side


def old_position(m,index,elapsed):
    p=motion_progress(m.comparison.laps[index].samples,elapsed)
    point=np.array([np.interp(p,m.progress,m.route[:,axis]) for axis in (0,1)])
    step=2/(len(m.route)-1)
    tangent=np.array([np.interp(min(1,p+step),m.progress,m.route[:,axis])-
                      np.interp(max(0,p-step),m.progress,m.route[:,axis]) for axis in (0,1)])
    tangent/=max(np.linalg.norm(tangent),1e-9)
    return point+np.array([-tangent[1],tangent[0]])*np.interp(p,m.progress,m.separation)*ghost_lane_side(index)


def old_draw(m,layer,elapsed):
    layer.alpha_composite(m.static);d=ImageDraw.Draw(layer);s=m.scale
    for index,color in enumerate(m.colors):
        tail=m.project(np.array([old_position(m,index,t) for t in np.linspace(max(0,elapsed-3),elapsed,18)]))
        d.line([tuple(p) for p in tail],fill=color,width=max(1,round(2*s)),joint='curve')
        x,y=m.project(old_position(m,index,elapsed));r=(4.5 if index==0 else 3)*s
        d.ellipse((x-r-3*s,y-r-3*s,x+r+3*s,y+r+3*s),fill=(*ImageColor.getrgb(color),45))
        d.ellipse((x-r,y-r,x+r,y+r),fill=color,outline='#ffffff',width=max(1,round(s)))


if __name__=='__main__':
    m=TrackMap(comparison_fixture(),None,(320,120,150,170),1,font)
    times=np.linspace(0,22,240)
    for t in times:
        a=Image.new('RGBA',(540,960));b=a.copy()
        old_draw(m,a,t);m.draw(b,t)
        if a.tobytes()!=b.tobytes():raise AssertionError(f'Locator pixels changed at {t}')
    timings={}
    for name,draw in [('before',lambda image,t:old_draw(m,image,t)),('after',m.draw)]:
        started=time.perf_counter()
        for t in times:draw(Image.new('RGBA',(540,960)),t)
        timings[name]=time.perf_counter()-started
    result=dict(frames=len(times),pixel_identical=True,locator_seconds=timings,
                locator_speedup=timings['before']/timings['after'])
    print(json.dumps(result,indent=2))
    Path('tmp/render-overhead-benchmark.json').write_text(json.dumps(result,indent=2))
