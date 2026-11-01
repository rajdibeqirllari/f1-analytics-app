"""Opt-in real historical integration smoke run against the local API."""
import argparse
import json
import time
from pathlib import Path
import requests

parser=argparse.ArgumentParser()
parser.add_argument('--year',type=int,default=2025)
parser.add_argument('--event',default='Austrian Grand Prix')
parser.add_argument('--session',default='Q')
parser.add_argument('--kind',default='catalog,traces,telemetry,chart')
parser.add_argument('--style',choices=['2D','3D'],default='3D')
parser.add_argument('--final',action='store_true')
parser.add_argument('--duration',type=float,default=1)
args=parser.parse_args()
base='http://127.0.0.1:8000'
selection=dict(year=args.year,event=args.event,session=args.session,driver='VER',driver_b='LEC')
report=[]
for kind in args.kind.split(','):
    options=dict(chart='Fastest lap map',source='FastF1',sample_rate=1)
    if kind=='hud': options.update(format='Preview',width=640,height=360,hud_width=200,position='Custom',x=20,y=20)
    if kind=='video': options.update(style=args.style,camera='Night chase A' if args.style=='3D' else 'Follow cars',
        start=5,end=5+args.duration,resolution=720 if args.final else 540,fps=30 if args.final else 24,preview=not args.final,quality='Fast')
    response=requests.post(base+'/api/jobs',json=dict(kind=kind,selection=selection,options=options),timeout=10)
    response.raise_for_status();key=response.json()['id'];began=time.monotonic()
    while True:
        job=requests.get(base+'/api/jobs/'+key,timeout=20).json()
        if job['status'] in ('complete','failed','cancelled'):break
        if time.monotonic()-began>300:job=dict(status='still-running',error='Inspect task '+key);break
        time.sleep(1)
    result=job.get('result') or {}
    summary=dict(kind=kind,id=key,status=job['status'],error=job.get('error',''),seconds=round(time.monotonic()-began,1))
    if kind=='catalog' and job['status']=='complete': summary['drivers']=list(result['drivers'])
    if kind=='traces' and job['status']=='complete': summary['samples']=[len(d['points']) for d in result]
    if isinstance(result,dict):
        for field in ('rows','duration','viewer','file','metadata'):
            if field in result:summary[field]=len(result[field]) if field=='rows' and isinstance(result[field],list) else result[field]
    print(json.dumps(summary),flush=True);report.append(summary)
folder=Path(__file__).resolve().parents[1]/'tmp';folder.mkdir(exist_ok=True)
(folder/f'platform-smoke-{args.kind.replace(",","-")}{"-"+args.style+("-final" if args.final else "-preview") if args.kind=="video" else ""}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
