"""2026 field check on a real 2026 race (Replay page, 2026 Las Vegas GP): every entrant's resolved chassis/livery/number,
a browser-rendered contact sheet of all constructors with HUD labels hidden, and teammate close-ups.

  .venv\\Scripts\\python.exe scripts\\dev\\capture_field.py --base http://localhost:8002
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import CDP  # noqa: E402

SHOOT = r"""(async(code,view)=>{const e=window.__rhxBroadcast;const T=window.THREE_NS;
 cancelAnimationFrame(e.raf);e.disposed=true;
 const car=e.cars.get(code);if(!car)return 'missing';
 for(const [k,c] of e.cars){c.group.visible=(k===code);c.label.visible=false}
 const g=car.group;g.updateMatrixWorld(true);
 const P=(x,y,z)=>g.localToWorld(new g.position.constructor(x,y,z));
 const views={front34:[[4.6,1.25,-3.6],[0.4,0.45,0]],side:[[0.2,0.9,-6.2],[0.0,0.45,0]],rear34:[[-4.8,1.4,-3.2],[-0.6,0.55,0]],
  num_side:[[-1.1,1.05,-2.6],[-1.3,0.48,0]],num_side_r:[[-1.1,1.05,2.6],[-1.3,0.48,0]],nose:[[3.6,1.3,0.0],[1.6,0.35,0]]};
 const [p,t]=views[view];const cam=e.camera;cam.position.copy(P(...p));cam.fov=view.startsWith('num')?32:30;cam.near=0.05;cam.updateProjectionMatrix();cam.lookAt(P(...t));
 if(car.lod&&car.lod[0]){car.lod[0].visible=true;if(car.lod[1])car.lod[1].visible=false}
 e.renderer.setPixelRatio(1);e.renderer.setSize(1920,1080,false);cam.aspect=16/9;cam.updateProjectionMatrix();
 e.renderer.render(e.scene,cam);await new Promise(r=>requestAnimationFrame(()=>r()));e.renderer.render(e.scene,cam);return 'ok'})"""


async def run(base, out):
    out = Path(out)
    c = CDP(1920, 1080)
    await c.connect()
    rep = {}
    try:
        url = f'{base}/hype/replay?year=2026&event=Las+Vegas+Grand+Prix&session=R'
        await c.goto(url)
        await c.eval("localStorage.setItem('rhx-replay-view','3d');localStorage.setItem('rhx-b3d-preview-models','1');true")   # preview switch on: must stay unused on 2026 data
        await c.goto(url)
        await c.eval("(async()=>{for(let i=0;i<40;i++){const b=[...document.querySelectorAll('button')].find(b=>/load replay/i.test(b.textContent));if(b){b.click();return 1}await new Promise(r=>setTimeout(r,250))}})()")
        await c.eval("(async()=>{for(let i=0;i<300&&!(window.__rhxBroadcast?.info?.ok);i++)await new Promise(r=>setTimeout(r,1000));return 1})()", timeout=330)
        await c.eval("(()=>{const el=document.querySelector('input[aria-label=\"Replay position\"]');const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(el,String(Number(el.min)+3));el.dispatchEvent(new Event('input',{bubbles:true}));return 1})()")
        await c.eval("(async()=>{for(let i=0;i<60;i++){const e=window.__rhxBroadcast;if([...e.cars.values()].filter(c=>'model' in c).length>=Object.keys(e.info.drivers).length)break;await new Promise(r=>setTimeout(r,1000))}return 1})()", timeout=80)
        await asyncio.sleep(3)
        rep['session'] = await c.eval("(()=>{const e=window.__rhxBroadcast;return {meeting:e.info.session,label:e.info.label,drivers:Object.keys(e.info.drivers).length,preview:document.querySelector('.rhx-b3d-preview-tag')?.innerText||null}})()")
        rep['entrants'] = await c.eval("(()=>{const e=window.__rhxBroadcast;return Object.entries(e.info.drivers).map(([k,m])=>{const c=e.cars.get(k);return {code:m.code,team:m.team,number:m.number,model:c?.model||'GENERIC',chassis:c?.chassis||null,carNumber:c?.number||null,numberMat:c?.numberMats?.map(x=>x.name)||[]}})})()")
        # shared-material check: number textures must be distinct objects per car
        rep['number_textures_unique'] = await c.eval("(()=>{const e=window.__rhxBroadcast;const maps=[];for(const c of e.cars.values())if(c.numberMats)for(const m of c.numberMats)maps.push(m.map);return {count:maps.length,unique:new Set(maps).size}})()")
        await c.eval("document.querySelector('.rhx-b3d-fsbtn').click();true")
        await asyncio.sleep(1.5)
        await c.eval("(()=>{const s=document.createElement('style');s.textContent='.rhx-b3d-stage>*:not(.rhx-b3d-canvas){display:none!important}.rhx-b3d-bar{display:none!important}';document.head.appendChild(s);return 1})()")
        teams = {}
        for row in rep['entrants']:
            teams.setdefault(row['model'], []).append(row['code'])
        rep['teams'] = teams
        code_to_key = await c.eval("(()=>{const e=window.__rhxBroadcast;return Object.fromEntries(Object.entries(e.info.drivers).map(([k,m])=>[m.code,k]))})()")
        shots = []
        for model, codes in sorted(teams.items()):
            for view in ('front34', 'rear34'):
                r = await c.eval(SHOOT + f"('{code_to_key[codes[0]]}','{view}')")
                p = out / f'field_{model}_{view}.png'
                await c.shot(p)
                shots.append((model, codes[0], view, p, r))
        mates = []
        for model in ('mercedes', 'williams', 'red_bull', 'ferrari'):
            for code in teams.get(model, [])[:2]:
                await c.eval(SHOOT + f"('{code_to_key[code]}','num_side')")
                p = out / f'mate_{model}_{code}_num_side.png'
                await c.shot(p)
                await c.eval(SHOOT + f"('{code_to_key[code]}','num_side_r')")
                p2 = out / f'mate_{model}_{code}_num_side_right.png'
                await c.shot(p2)
                mates.append((model, code, p, p2))
        rep['shots'] = len(shots)
    finally:
        (out / 'field_report.json').write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding='utf-8')
        c.close()
    # contact sheet: one row per constructor (front 3/4 + rear 3/4)
    W, H = 640, 360
    font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 20)
    rows = sorted({s[0] for s in shots})
    sheet = Image.new('RGB', (W * 2, H * len(rows)), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for i, model in enumerate(rows):
        for j, view in enumerate(('front34', 'rear34')):
            s = next(x for x in shots if x[0] == model and x[2] == view)
            im = Image.open(s[3]).convert('RGB').resize((W, H))
            sheet.paste(im, (j * W, i * H))
            d.text((j * W + 10, i * H + 8), f'{model}  {s[1]}  {view}', fill=(255, 230, 80), font=font)
    sheet.save(out / 'contact_sheet_2026_constructors.jpg', quality=88)
    ms = Image.new('RGB', (W * 2, H * len(mates)), (0, 0, 0))
    d = ImageDraw.Draw(ms)
    for i, (model, code, p, p2) in enumerate(mates):
        for j, q in enumerate((p, p2)):
            ms.paste(Image.open(q).convert('RGB').resize((W, H)), (j * W, i * H))
            d.text((j * W + 10, i * H + 8), f'{model} {code} {"left" if j == 0 else "right"} side', fill=(255, 230, 80), font=font)
    ms.save(out / 'teammates_numbers.jpg', quality=88)
    print(json.dumps({k: v for k, v in rep.items() if k != 'entrants'}, indent=1, ensure_ascii=False))
    print('\n'.join(f"{e['code']:4} #{e['number']:>3} {e['team']:24} -> {e['model']:13} car#{e['carNumber']}" for e in rep.get('entrants', [])))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:8002')
    ap.add_argument('--out', default='outputs/v3/field')
    a = ap.parse_args()
    asyncio.run(run(a.base, a.out))
