"""Fullscreen broadcast check on the Replay page through a real (headless) Chrome: screenshots, a clip, state checks.

  .venv\\Scripts\\python.exe scripts\\dev\\capture_fullscreen.py --base http://localhost:8002 --out outputs/v3/fullscreen
"""
import argparse
import asyncio
import json
import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import CDP  # noqa: E402

HELP = r"""
window.__q=(s)=>document.querySelector(s);
window.__seek=(t)=>{const el=document.querySelector('input[aria-label="Replay position"]');const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(el,String(t));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return Number(el.value)};
window.__driver=(code)=>{const s=document.querySelector('.rhx-b3d-pick select');const o=[...s.options].find(o=>o.value===code||new RegExp('\\b'+code+'\\b').test(o.text));const set=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;set.call(s,o?o.value:'');s.dispatchEvent(new Event('change',{bubbles:true}));return o?.text};
window.__cam=(label)=>{[...document.querySelectorAll('.rhx-b3d-bar button')].find(b=>b.textContent.trim()===label)?.click()};
window.__btn=(re)=>[...document.querySelectorAll('button')].find(b=>new RegExp(re,'i').test(b.textContent.trim()));
window.__rect=(sel)=>{const el=(typeof sel==='string'?document.querySelector(sel):sel);el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]};
window.__state=()=>{const e=window.__rhxBroadcast;const sec=document.querySelector('.rhx-b3d');return {fs:sec?.className,native:document.fullscreenElement===sec,clock:document.querySelector('input[aria-label="Replay position"]')?.value,
 focus:e?.focus,mode:e?.mode,watched:document.querySelector('.rhx-bt li.on b')?.textContent||null,rows:document.querySelectorAll('.rhx-bt li').length,
 radio:document.querySelector('.rhx-bradio')?.innerText||null,preview:document.querySelector('.rhx-b3d-preview-tag')?.innerText||null,
 tower:[...document.querySelectorAll('.rhx-bt li')].slice(0,6).map(l=>l.innerText.replace(/\n/g,' ')),canvasSame:e?.renderer?.domElement===window.__canvas0}};
"""


async def run(base, out):
    out = Path(out)
    c = CDP(1920, 1080)
    await c.connect()
    report = {}
    try:
        await c.goto(f'{base}/hype/replay?year=2025&event=Abu+Dhabi+Grand+Prix&session=R')
        await c.eval("localStorage.setItem('rhx-replay-view','3d');localStorage.setItem('rhx-b3d-camera','pod');localStorage.setItem('rhx-b3d-preview-models','1');localStorage.setItem('rhx-comm-radio-mode','safe');localStorage.setItem('rhx-b3d-lines','recon');true")
        await c.goto(f'{base}/hype/replay?year=2025&event=Abu+Dhabi+Grand+Prix&session=R')
        await c.eval(HELP + 'true')
        await c.eval("(async()=>{for(let i=0;i<40&&!__btn('load replay');i++)await new Promise(r=>setTimeout(r,250));__btn('load replay')?.click();return true})()")
        await c.eval("(async()=>{for(let i=0;i<240&&!(window.__rhxBroadcast?.info?.ok);i++)await new Promise(r=>setTimeout(r,1000));return !!window.__rhxBroadcast?.info?.ok})()", timeout=300)
        await c.eval(HELP + 'window.__canvas0=window.__rhxBroadcast.renderer.domElement;true')
        radio_url = await c.eval("window.__rhxBroadcast.samplesBase.replace(/\\/scene\\/samples$/,'/radio')")
        ev = await c.eval(f"(async()=>{{for(let i=0;i<20;i++){{const d=await (await fetch('{radio_url}')).json();if(!d.loading)return d;await new Promise(r=>setTimeout(r,1500))}}return null}})()", timeout=60)
        events = (ev or {}).get('events') or []
        report['radio_events'] = len(events)
        # a radio event in the race (after lap 2), preferring Antonelli's
        pick = next((e for e in events if e['code'] == 'ANT' and e['t'] > 300), None) or next((e for e in events if e['t'] > 300), None)
        report['radio_pick'] = pick
        t0 = (pick['t'] - 4) if pick else 1500
        await c.eval(f"__driver('ANT');__cam('TV Pod');__seek({t0});true")
        await asyncio.sleep(5)
        await c.eval("__q('.rhx-b3d-fsbtn').click();true")
        await asyncio.sleep(2.5)
        report['enter'] = await c.eval('__state()')
        # play at 1x through the radio event
        await c.eval("__btn('^1×$')?.click();__btn('^play$')?.click();true")
        await asyncio.sleep(5.5)
        report['radio_shown'] = await c.eval('__state()')
        await c.shot(out / 'fullscreen_1080p_radio.png')

        async def actions():
            await asyncio.sleep(3)
            await c.move(300, 300)
            await c.eval("[...document.querySelectorAll('.rhx-bt li button')].find(b=>/HAD/.test(b.textContent)).click();true")   # Hadjar from the tower
            await asyncio.sleep(3)
            await c.move(960, 1000)
            await c.eval("__cam('Broadcast');true")
            await asyncio.sleep(4)
        n = await c.record(14, out / 'clip_frames', actions)
        report['clip_frames'] = n
        report['after_switch'] = await c.eval('__state()')
        # pause, backward seek, exit + re-enter
        await c.eval("__btn('^pause$')?.click();true")
        await asyncio.sleep(1)
        report['paused'] = await c.eval('__state()')
        await c.shot(out / 'fullscreen_1080p_paused_broadcast.png')
        await c.eval(f"__seek({t0 - 60});true")
        await asyncio.sleep(3)
        report['seek_back'] = await c.eval('__state()')
        await c.key('Escape')
        await asyncio.sleep(1.5)
        report['exit1'] = await c.eval('__state()')
        for i in range(2):
            await c.eval("__q('.rhx-b3d-fsbtn').click();true")
            await asyncio.sleep(1.5)
            report[f'reenter{i}'] = await c.eval('__state()')
            await c.key('Escape')
            await asyncio.sleep(1.2)
        # 720p compact layout
        await c.send('Emulation.setDeviceMetricsOverride', {'width': 1280, 'height': 720, 'deviceScaleFactor': 1, 'mobile': False})
        await c.eval("__q('.rhx-b3d-fsbtn').click();true")
        await asyncio.sleep(2)
        await c.eval(f"__seek({t0 + 2});true")
        await asyncio.sleep(3)
        report['p720'] = await c.eval('__state()')
        await c.shot(out / 'fullscreen_720p.png')
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
        c.close()
    fr = out / 'clip_frames'
    if (fr / 'frames.txt').exists():
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(fr / 'frames.txt'), '-vf', 'scale=1920:-2,format=yuv420p',
                        '-r', '30', '-c:v', 'libx264', '-crf', '20', str(out / 'fullscreen_replay_clip.mp4')], check=False)
    print(json.dumps(report, indent=1)[:6000])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:8002')
    ap.add_argument('--out', default='outputs/v3/fullscreen')
    a = ap.parse_args()
    asyncio.run(run(a.base, a.out))
