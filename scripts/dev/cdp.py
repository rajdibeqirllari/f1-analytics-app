"""Minimal Chrome DevTools Protocol driver for browser captures of the running app (dev tool, no extra installs).

Launches a separate Chrome profile (headless or windowed) with remote debugging, then:
  eval(js)            evaluate in the page (awaits promises), returns the value
  click(x, y)         real mouse click (counts as a user gesture, e.g. for requestFullscreen)
  key(name)           key press (e.g. 'Escape')
  shot(path)          full-resolution screenshot of the viewport (DOM overlays included)
  record(secs, dir)   screencast frames (JPEG) with timestamps -> frames.txt for ffmpeg's concat demuxer
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


class CDP:
    def __init__(self, width=1920, height=1080, port=9333, headless=True):
        self.port, self.w, self.h = port, width, height
        self.profile = tempfile.mkdtemp(prefix='rhx-cdp-')
        args = [CHROME, f'--remote-debugging-port={port}', f'--user-data-dir={self.profile}', f'--window-size={width},{height}',
                '--no-first-run', '--no-default-browser-check', '--autoplay-policy=no-user-gesture-required', '--ignore-gpu-blocklist',
                '--enable-gpu-rasterization', '--use-angle=d3d11', 'about:blank']
        if headless:
            args.insert(1, '--headless=new')
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        self.n = 0
        self.events: list[dict] = []

    async def connect(self):
        for _ in range(60):
            try:
                tabs = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json').read())
                page = next(t for t in tabs if t['type'] == 'page')
                break
            except Exception:
                await asyncio.sleep(0.5)
        self.ws = await websockets.connect(page['webSocketDebuggerUrl'], max_size=64 * 1024 * 1024)
        self.pending, self.queue = {}, asyncio.Queue()
        self.reader = asyncio.create_task(self._reader())
        await self.send('Page.enable')
        await self.send('Runtime.enable')
        await self.send('Emulation.setDeviceMetricsOverride', {'width': self.w, 'height': self.h, 'deviceScaleFactor': 1, 'mobile': False})

    async def _reader(self):
        async for raw in self.ws:
            msg = json.loads(raw)
            fut = self.pending.pop(msg.get('id'), None) if 'id' in msg else None
            if fut is not None and not fut.done():
                fut.set_result(msg)
            elif 'method' in msg:
                await self.queue.put(msg)

    async def send(self, method, params=None):
        self.n += 1
        mid = self.n
        fut = asyncio.get_running_loop().create_future()
        self.pending[mid] = fut
        await self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        msg = await fut
        if 'error' in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg.get('result', {})

    async def eval(self, js, timeout=120):
        r = await asyncio.wait_for(self.send('Runtime.evaluate', {'expression': js, 'awaitPromise': True, 'returnByValue': True, 'userGesture': True}), timeout)
        if r.get('exceptionDetails'):
            raise RuntimeError(r['exceptionDetails'].get('exception', {}).get('description') or r['exceptionDetails'])
        return r.get('result', {}).get('value')

    async def goto(self, url):
        await self.send('Page.navigate', {'url': url})
        await asyncio.sleep(2.5)

    async def click(self, x, y):
        for t in ('mousePressed', 'mouseReleased'):
            await self.send('Input.dispatchMouseEvent', {'type': t, 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})

    async def move(self, x, y):
        await self.send('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y})

    async def key(self, name):
        codes = {'Escape': 27}
        for t in ('keyDown', 'keyUp'):
            await self.send('Input.dispatchKeyEvent', {'type': t, 'key': name, 'code': name, 'windowsVirtualKeyCode': codes.get(name, 0)})

    async def shot(self, path):
        r = await self.send('Page.captureScreenshot', {'format': 'png'})
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(base64.b64decode(r['data']))
        return path

    async def record(self, seconds, out_dir, during=None):
        """Screencast for `seconds` (optionally running coroutine `during` meanwhile). Writes frames + frames.txt."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        while not self.queue.empty():
            self.queue.get_nowait()
        await self.send('Page.startScreencast', {'format': 'jpeg', 'quality': 85, 'maxWidth': self.w, 'maxHeight': self.h, 'everyNthFrame': 1})
        frames = []
        t_end = time.time() + seconds
        task = asyncio.create_task(during()) if during else None
        while time.time() < t_end:
            try:
                msg = await asyncio.wait_for(self.queue.get(), 1.0)
            except asyncio.TimeoutError:
                continue
            if msg.get('method') == 'Page.screencastFrame':
                p = msg['params']
                f = out / f'f{len(frames):05d}.jpg'
                f.write_bytes(base64.b64decode(p['data']))
                frames.append((f.name, p['metadata']['timestamp']))
                asyncio.create_task(self.send('Page.screencastFrameAck', {'sessionId': p['sessionId']}))
        await self.send('Page.stopScreencast')
        if task:
            await task
        with open(out / 'frames.txt', 'w') as fh:
            for i, (name, ts) in enumerate(frames):
                dur = (frames[i + 1][1] - ts) if i + 1 < len(frames) else 0.1
                fh.write(f"file '{name}'\nduration {max(0.01, dur):.4f}\n")
            if frames:
                fh.write(f"file '{frames[-1][0]}'\n")
        return len(frames)

    def close(self):
        try:
            self.proc.terminate()
        except Exception:
            pass
