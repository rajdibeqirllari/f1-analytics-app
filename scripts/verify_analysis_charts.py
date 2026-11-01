"""Exercise every exported calculation on a cached historical race."""
import json
from pathlib import Path
import time
from api.engines import chart,CHARTS
from api.main import Selection

s=Selection(year=2024,event='Monaco Grand Prix',session='R',driver='LEC',driver_b='VER',lap=40)
rows=[]
for name in sum(CHARTS.values(),[]):
    start=time.monotonic()
    try:
        result=chart(s,dict(chart=name),lambda *args:None)
        row=dict(chart=name,status='complete',file=result['file']['name'])
    except Exception as exc: row=dict(chart=name,status='failed',error=str(exc))
    row['seconds']=round(time.monotonic()-start,1);rows.append(row)
    print(json.dumps(row),flush=True)
root=Path(__file__).resolve().parents[1]
(root/'tmp'/'platform-analysis-verification.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
