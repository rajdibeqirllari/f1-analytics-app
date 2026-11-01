"""Local QA comparison; never use the legacy side to audit the new cadence."""
import argparse
from pathlib import Path
import subprocess
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont


def frame(path,seconds=None,index=None):
    cap=cv2.VideoCapture(str(path))
    if index is not None:cap.set(cv2.CAP_PROP_POS_FRAMES,int(index))
    else:cap.set(cv2.CAP_PROP_POS_MSEC,float(seconds)*1000)
    ok,array=cap.read();cap.release()
    if not ok:raise RuntimeError(f'Could not decode {path} at {seconds or index}')
    return Image.fromarray(cv2.cvtColor(array,cv2.COLOR_BGR2RGB))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path)
    p.add_argument('--motion',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--same-timeline',action='store_true')
    p.add_argument('--before-label',default='BEFORE: 24fps motion / 30fps file')
    p.add_argument('--after-label',default='AFTER: Native 60fps / dynamic pacing')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',15)
    data=np.load(args.motion);source,first=np.unique(data['source_times'],return_index=True)
    def output_time(t):return float(np.interp(t,source,first/60))
    sheet=Image.new('RGB',(1080,4*504),'#080e15');draw=ImageDraw.Draw(sheet)
    for pair,t in enumerate((0,10,25,45,70,90,float(source[-1]))):
        hold=.5 if t==source[-1] else 0
        before_time=output_time(t)+hold if args.same_timeline else min(t/3+hold,33.1)
        for side,path,seconds in ((0,args.before,before_time),(1,args.after,output_time(t)+hold)):
            tile=pair*2+side;x=(tile%4)*270;y=(tile//4)*504
            image=frame(path,seconds=seconds);image.thumbnail((270,480))
            sheet.paste(image,(x,y+24));draw.text((x+5,y+3),f'{"BEFORE" if side==0 else "NATIVE60"} | lap {t:.2f}s',font=font,fill='white')
    sheet.save(args.output/'matched-source-comparison.jpg',quality=94)
    for moment in (10,42,90):
        start=int(np.searchsorted(data['source_times'],moment));contact=Image.new('RGB',(1080,680),'#080e15')
        d=ImageDraw.Draw(contact)
        for j in range(12):
            image=frame(args.after,index=start+j);image.thumbnail((180,320));x=j%6*180;y=j//6*340
            contact.paste(image,(x,y+20));d.text((x+3,y+2),f'#{start+j} | {data["source_times"][start+j]:.3f}s',font=font,fill='white')
        contact.save(args.output/f'corner-{moment}-consecutive.jpg',quality=94)
    frame(args.after,seconds=34).save(args.output/'final-result.jpg',quality=95)
    # Side-by-side plays each original output clock: pacing intentionally differs.
    # The old side necessarily repeats at60fps; this diagnostic is NOT the
    # deliverable's cadence proof and is never fed into the main renderer.
    header=Image.new('RGB',(1080,48),'#080e15');d=ImageDraw.Draw(header)
    title=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',22)
    d.text((12,10),args.before_label,font=title,fill='white')
    d.text((552,10),args.after_label,font=title,fill='white')
    header.save(args.output/'comparison-header.png')
    filters='[0:v]scale=540:960,setsar=1,tpad=stop_mode=clone:stop_duration=2[old];[1:v]scale=540:960,setsar=1[new];[old][new]hstack=inputs=2:shortest=1,pad=1080:1008:0:48[body];[body][2:v]overlay=0:0:shortest=1[v]'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(args.before),'-i',str(args.after),'-loop','1','-i',str(args.output/'comparison-header.png'),
        '-filter_complex',filters,'-map','[v]','-an','-t','35','-r','60','-fps_mode','cfr',
        '-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',
        str(args.output/'before-after-comparison.mp4')],check=True)
