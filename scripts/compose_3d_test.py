"""Add accurate telemetry graphics to the Blender test and encode an H.264 MP4."""
from pathlib import Path
import json
import subprocess
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'output/video_studio/3d_test'
DATA=json.loads((ROOT/'tmp/reference_review/paul_ricard_3d_input.json').read_text())
VALIDATION=json.loads((FOLDER/'validation.json').read_text())
FPS=VALIDATION['fps']; START=VALIDATION['start_seconds']
FONT=Path('C:/Windows/Fonts')
WHITE='#f5f7fa'; MUTED='#96a9bc'; RED='#ff4555'; CYAN='#37d9ee'

def font(size,bold=False):
    return ImageFont.truetype(str(FONT/('segoeuib.ttf' if bold else 'segoeui.ttf')),size)

def overlay(source,elapsed):
    image=source.convert('RGBA')
    layer=Image.new('RGBA',image.size)
    draw=ImageDraw.Draw(layer)
    for y in range(255): draw.line((0,y,540,y),fill=(7,13,22,max(0,round(247*(1-y/255)**.38))))
    for y in range(780,960): draw.line((0,y,540,y),fill=(7,13,22,round(235*((y-780)/180)**.35)))
    draw.line((28,30,43,30),fill=RED,width=5)
    draw.text((54,19),'RACE HYPE',font=font(17,True),fill=WHITE)
    draw.text((508,23),'3D / TEST 01',font=font(11),fill=MUTED,anchor='ra')
    draw.text((28,51),'PAUL RICARD',font=font(28,True),fill=WHITE)
    draw.text((29,87),'2022 QUALIFYING  /  Q3  /  GHOST LAPS',font=font(11),fill=MUTED)
    states=[]
    for index,lap in enumerate(DATA['laps']):
        samples=lap['samples']; t=samples['t']
        progress=float(np.interp(elapsed,t,samples['progress']))
        idx=max(0,int(np.searchsorted(t,elapsed,side='right'))-1)
        speed=float(np.interp(elapsed,t,samples['speed']))
        states.append((lap,progress))
        x=28+index*260; color=[RED,CYAN][index]
        draw.rounded_rectangle((x,118,x+224,208),radius=9,fill=(12,20,30,235),outline=(56,70,84,170))
        draw.line((x+13,130,x+13,152),fill=color,width=3)
        draw.text((x+23,127),lap['code'],font=font(22,True),fill=WHITE)
        draw.text((x+207,134),f"L{lap['number']}",font=font(12),fill=MUTED,anchor='ra')
        draw.text((x+14,164),str(round(speed)),font=font(27,True),fill=WHITE)
        draw.text((x+75,181),'KM/H',font=font(10),fill=MUTED)
        draw.text((x+146,175),'GEAR',font=font(10),fill=MUTED)
        draw.text((x+203,163),str(samples['gear'][idx]),font=font(27,True),fill=color,anchor='ra')
    # Delta compares arrival times at the same distance, NOT visual car separation.
    progress=min(s[1] for s in states)
    arrivals=[float(np.interp(progress,lap['samples']['progress'],lap['samples']['t'])) for lap in DATA['laps']]
    delta=arrivals[1]-arrivals[0]
    winner=DATA['laps'][0 if delta>=0 else 1]['code']
    draw.text((28,813),'TIME GAIN  /  MATCHED DISTANCE',font=font(11),fill=MUTED)
    draw.text((28,833),f'{winner}  {abs(delta):.3f}s',font=font(30,True),fill=RED if delta>=0 else CYAN)
    draw.text((508,842),f'{elapsed:05.2f}s',font=font(20,True),fill=WHITE,anchor='ra')
    draw.line((28,887,508,887),fill=(80,95,112,180),width=2)
    fraction=(elapsed-START)/VALIDATION['seconds']
    draw.line((28,887,28+480*fraction,887),fill=RED,width=2)
    draw.text((28,901),'Real lap timing · generic cars · separated ghost paths',font=font(10),fill=MUTED)
    draw.text((28,922),'Circuit: narlankaaditya / CC BY 4.0 · Car: BGRT-Studio',font=font(9),fill=MUTED)
    return Image.alpha_composite(image,layer).convert('RGB')

if __name__=='__main__':
    first=overlay(Image.open(FOLDER/'first_frame.png'),START)
    first.save(FOLDER/'poster.png')
    if '--poster-only' in sys.argv: sys.exit(0)
    frames=sorted((FOLDER/'frames').glob('frame_*.png'))
    if len(frames)!=VALIDATION['frames']: raise RuntimeError(f'Incomplete render: {len(frames)} frames')
    destination=FOLDER/'paul_ricard_LEC_VER_3d_test.mp4'
    partial=destination.with_suffix('.partial.mp4')
    process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
       '-s','540x960','-r',str(FPS),'-i','-','-an','-c:v','libx264','-crf','18','-preset','fast',
       '-pix_fmt','yuv420p','-movflags','+faststart',str(partial)],stdin=subprocess.PIPE)
    try:
        for number,path in enumerate(frames):
            elapsed=START+number/FPS
            composed=overlay(Image.open(path),elapsed)
            if number in (len(frames)//2,len(frames)-1): composed.save(FOLDER/f'check_{number+1:04}.png')
            process.stdin.write(composed.tobytes())
        process.stdin.close()
        if process.wait()!=0: raise RuntimeError('FFmpeg failed')
        partial.replace(destination)
    finally:
        if process.poll() is None: process.kill(); process.wait()
    print('VIDEO_READY',destination)
