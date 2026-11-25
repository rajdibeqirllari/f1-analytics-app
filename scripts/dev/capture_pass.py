"""Close-pass clips (reconstructed racing lines) from TV Pod and Broadcast: 2025 Abu Dhabi GP race, VER passing PIA.

  .venv\\Scripts\\python.exe scripts\\dev\\capture_pass.py --base http://localhost:8002 --t0 3615 --secs 14
"""
import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import CDP  # noqa: E402
from capture_fullscreen import HELP  # noqa: E402


async def run(base, out, t0, secs, driver):
    out = Path(out)
    c = CDP(1920, 1080)
    await c.connect()
    try:
        url = f'{base}/hype/replay?year=2025&event=Abu+Dhabi+Grand+Prix&session=R'
        await c.goto(url)
        await c.eval("localStorage.setItem('rhx-replay-view','3d');localStorage.setItem('rhx-b3d-preview-models','1');localStorage.setItem('rhx-b3d-lines','recon');true")
        await c.goto(url)
        await c.eval(HELP + 'true')
        await c.eval("(async()=>{for(let i=0;i<40&&!__btn('load replay');i++)await new Promise(r=>setTimeout(r,250));__btn('load replay')?.click();return true})()")
        await c.eval("(async()=>{for(let i=0;i<240&&!(window.__rhxBroadcast?.info?.ok);i++)await new Promise(r=>setTimeout(r,1000));return 1})()", timeout=300)
        await c.eval(HELP + 'true')
        for cam in ('TV Pod', 'Broadcast'):
            await c.eval(f"__driver('{driver}');__cam('{cam}');__btn('^pause$')?.click();__seek({t0});true")
            await asyncio.sleep(5)
            if not await c.eval("document.querySelector('.rhx-b3d').classList.contains('is-fs')"):
                await c.eval("__q('.rhx-b3d-fsbtn').click();true")
                await asyncio.sleep(1.5)
            await c.eval("__btn('^1×$')?.click();__btn('^play$')?.click();true")
            tag = cam.replace(' ', '').lower()
            n = await c.record(secs, out / f'pass_{tag}_frames')
            await c.eval("__btn('^pause$')?.click();true")
            print(cam, n, 'frames')
            fr = out / f'pass_{tag}_frames'
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(fr / 'frames.txt'), '-vf', 'scale=1920:-2,format=yuv420p',
                            '-r', '30', '-c:v', 'libx264', '-crf', '21', str(out / f'pass_VER_PIA_abudhabi2025_{tag}.mp4')], check=False)
    finally:
        c.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:8002')
    ap.add_argument('--out', default='outputs/v3/pass')
    ap.add_argument('--t0', type=float, default=3615)
    ap.add_argument('--secs', type=float, default=14)
    ap.add_argument('--driver', default='VER')
    a = ap.parse_args()
    asyncio.run(run(a.base, a.out, a.t0, a.secs, a.driver))
