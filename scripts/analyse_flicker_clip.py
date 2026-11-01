"""Local temporal diagnostics; exports adjacent frames, not a visual-quality score."""
import cv2
import numpy as np
from pathlib import Path
import json
from PIL import Image,ImageDraw

SOURCE=Path(r'C:\Users\user\Downloads\2026_LEC_VER_3d_c8ab56c47246_preview.mp4')
OUT=Path('tmp/flicker-audit');OUT.mkdir(exist_ok=True)
cap=cv2.VideoCapture(str(SOURCE));fps=cap.get(cv2.CAP_PROP_FPS)
rows=[]
while True:
    ok,frame=cap.read()
    if not ok:break
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    rows.append([float(gray[700:850,175:365].mean()),float(gray[350:440,170:370].mean()),
                 float(gray[400:450,505:535].mean())])
cap.release()
values=np.array(rows);diff=np.abs(np.diff(values,axis=0));indices=np.argsort(diff[:,0])[-6:][::-1]
canvas=Image.new('RGB',(540*3,480*len(indices)))
cap=cv2.VideoCapture(str(SOURCE))
report=[]
for row,index in enumerate(indices):
    report.append(dict(seconds=float(index/fps),body_jump=float(diff[index,0]),road_jump=float(diff[index,1])))
    for col,offset in enumerate((-1,0,1)):
        number=max(0,int(index)+offset)
        cap.set(cv2.CAP_PROP_POS_FRAMES,number);ok,frame=cap.read()
        if not ok:continue
        im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).resize((270,480))
        ImageDraw.Draw(im).text((160,10),f'{number/fps:.3f}s',fill='yellow')
        canvas.paste(im,(col*540,row*480))
cap.release();canvas.save(OUT/'body-jumps.jpg')
(OUT/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
