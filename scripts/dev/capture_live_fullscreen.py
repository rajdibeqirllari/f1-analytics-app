"""Fullscreen broadcast check on the Live page with a saved recording (São Paulo 2026 race), through headless Chrome.

  .venv\\Scripts\\python.exe scripts\\dev\\capture_live_fullscreen.py --base http://localhost:8002
Opens live_2026-11-08_1804.txt as a replay on the (isolated) engine, rides with ANT, captures the radio card at the
recording time given by --radio-at, then sweeps a pit window at 5x and logs every tower change.
"""
import argparse
import asyncio
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import CDP  # noqa: E402

STATE = r"""(()=>{const e=window.__rhxBroadcast;const sec=document.querySelector('.rhx-b3d');return {fs:sec?.className,focus:e?.focus,mode:e?.mode,
 watched:document.querySelector('.rhx-bt li.on b')?.textContent||null,rows:document.querySelectorAll('.rhx-bt li').length,lap:document.querySelector('.rhx-bt header span')?.innerText||null,
 radio:document.querySelector('.rhx-bradio')?.innerText?.replace(/\n/g,' | ')||null,preview:document.querySelector('.rhx-b3d-preview-tag')?.innerText||null,
 clock:e?.lastD,tower:[...document.querySelectorAll('.rhx-bt li')].map(l=>l.querySelector('button').innerText.replace(/\n/g,' '))}})()"""


def api(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': base}, method='POST')
    return urllib.request.urlopen(req).read()


async def run(base, out, radio_at, mode):
    out = Path(out)
    api(base, '/api/live/open', {'folder': 'live', 'name': 'live_2026-11-08_1804.txt', 'mode': 'replay', 'speed': 1})
    api(base, '/api/live/control', {'seek': radio_at - 8, 'paused': True})
    c = CDP(1920, 1080)
    await c.connect()
    rep = {}
    try:
        await c.goto(f'{base}/hype/live')
        await c.eval(f"localStorage.setItem('rhx-live-view','3d');localStorage.setItem('rhx-b3d-camera','pod');localStorage.setItem('rhx-comm-radio-mode','{mode}');true")
        await c.goto(f'{base}/hype/live')
        await c.eval("(async()=>{for(let i=0;i<240&&!(window.__rhxBroadcast?.info?.ok&&window.__rhxBroadcast?.buf);i++)await new Promise(r=>setTimeout(r,1000));return 1})()", timeout=300)
        await c.eval("(()=>{const s=document.querySelector('.rhx-b3d-pick select');const o=[...s.options].find(o=>/ANT/.test(o.text));const set=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;set.call(s,o.value);s.dispatchEvent(new Event('change',{bubbles:true}));return o.text})()")
        await asyncio.sleep(3)
        await c.eval("document.querySelector('.rhx-b3d-fsbtn').click();true")
        await asyncio.sleep(2)
        rep['enter'] = await c.eval(STATE)
        api(base, '/api/live/control', {'speed': 1, 'paused': False})
        await asyncio.sleep(9.5)
        rep['radio'] = await c.eval(STATE)
        await c.shot(out / f'live_fullscreen_1080p_radio_{mode}.png')

        async def act():
            await asyncio.sleep(5)
            await c.move(400, 400)
            await c.eval("[...document.querySelectorAll('.rhx-bt li button')].find(b=>/HAD/.test(b.textContent))?.click();true")
            await asyncio.sleep(3)
            await c.eval("[...document.querySelectorAll('.rhx-b3d-bar button')].find(b=>b.textContent.trim()==='Broadcast')?.click();true")
        rep['clip_frames'] = await c.record(13, out / f'live_clip_frames_{mode}', act)
        rep['after'] = await c.eval(STATE)
        if mode == 'safe':
            # pit window sweep at 5x: log tower changes (positions, PIT, tyres)
            api(base, '/api/live/control', {'seek': 1500, 'speed': 10, 'paused': False})
            await asyncio.sleep(4)
            prev, changes = None, []
            for _ in range(40):
                st = await c.eval(STATE)
                rows = st['tower']
                if prev is not None and rows != prev:
                    a, b = dict((r.split(' ')[1], r) for r in prev if len(r.split(' ')) > 1), dict((r.split(' ')[1], r) for r in rows if len(r.split(' ')) > 1)
                    diff = [(k, a.get(k), b.get(k)) for k in b if a.get(k) and (a[k].split(' ')[0] != b[k].split(' ')[0] or a[k].split(' ')[-1] != b[k].split(' ')[-1] or ('PIT' in a[k]) != ('PIT' in b[k]))]
                    if diff:
                        changes.append(dict(clock=st['clock'], lap=st['lap'], diff=diff[:6]))
                prev = rows
                await asyncio.sleep(1.5)
            rep['sweep_changes'] = changes[:25]
            api(base, '/api/live/control', {'paused': True})
            await asyncio.sleep(1.5)
            rep['paused'] = await c.eval(STATE)
            await c.shot(out / 'live_fullscreen_paused.png')
            await c.key('Escape')
            await asyncio.sleep(1.2)
            rep['exit'] = await c.eval(STATE)
    finally:
        (out / f'live_report_{mode}.json').write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding='utf-8')
        c.close()
    fr = out / f'live_clip_frames_{mode}'
    if (fr / 'frames.txt').exists():
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(fr / 'frames.txt'), '-vf', 'scale=1920:-2,format=yuv420p',
                        '-r', '30', '-c:v', 'libx264', '-crf', '20', str(out / f'fullscreen_live_clip_{mode}.mp4')], check=False)
    print(json.dumps({k: (v if k != 'enter' else {x: v[x] for x in v if x != 'tower'}) for k, v in rep.items()}, indent=1, ensure_ascii=False)[:7000])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:8002')
    ap.add_argument('--out', default='outputs/v3/fullscreen')
    ap.add_argument('--radio-at', type=float, default=4137.4)
    ap.add_argument('--mode', default='safe')
    a = ap.parse_args()
    asyncio.run(run(a.base, a.out, a.radio_at, a.mode))
