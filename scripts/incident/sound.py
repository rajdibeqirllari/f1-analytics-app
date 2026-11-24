"""Original soundtrack + sound design for the incident video (all synthesised, no samples, no licensed music).

  .\\.venv\\Scripts\\python.exe scripts\\incident\\sound.py scripts\\incident\\mexico2026_t4.json [--preview] [--video path.mp4]

Builds, on the video's own timeline:
  * engine sound for both cars from their real RPM/throttle trace (pitch-dropped in slow motion),
  * a 140 BPM cinematic trap score that follows the edit (drop at Turn 1, half-time in the slow-mo,
    snare roll into the freeze, impact, drop again, quiet outro under the verdict),
  * whooshes on cuts, a riser into Turn 4, hits on the freeze and verdict, soft UI ticks on captions.
Writes work/audio_mix.wav plus music/sfx/engine stems, and muxes the mix into <video>.sound.mp4.
"""
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
from scipy.io import wavfile

ROOT = Path(__file__).absolute().parents[2]
HERE = Path(__file__).absolute().parent
argv = sys.argv[1:]
CFG = json.loads(Path(argv[0] if argv and not argv[0].startswith('--') else HERE / 'mexico2026_t4.json').read_text(encoding='utf-8'))
PREVIEW = '--preview' in argv
DATA = ROOT / CFG['data_dir']
WORK = DATA / 'work'
VIDEO = Path(argv[argv.index('--video') + 1]) if '--video' in argv else DATA / ('mexico2026_t4.preview.mp4' if PREVIEW else 'mexico2026_t4.mp4')
SR = 48000
FPS = CFG['render']['fps'] if not PREVIEW else max(15, CFG['render']['fps'] // 2)
rng = np.random.default_rng(16)

# ------------------------------------------------------------------ timeline (same rules as build_scene.py)
shots, t_data, spd = [], [], []
for shot in CFG['shots']:
    t0, t1 = shot['t']
    n = int(round(shot['hold'] * FPS)) if shot.get('hold') else int(round((t1 - t0) / shot['speed'] * FPS))
    start = len(t_data)
    for k in range(n):
        t_data.append(t0 if shot.get('hold') else t0 + k * shot['speed'] / FPS)
        spd.append(0.0 if shot.get('hold') else shot['speed'])
    shots.append(dict(id=shot['id'], start=start / FPS, end=(start + n) / FPS, shot=shot))
DUR = len(t_data) / FPS
N = int(DUR * SR)
ts = np.arange(N) / SR
fr = np.minimum((ts * FPS).astype(int), len(t_data) - 1)
T_DATA = np.array(t_data)[fr]          # data time for every audio sample
SPEED = np.array(spd)[fr]              # playback speed (0 = freeze)
SHOT = {s['id']: s for s in shots}


def lp(x, hz, order=2):
    return sosfilt(butter(order, min(hz, SR / 2.2), 'low', fs=SR, output='sos'), x)


def hp(x, hz, order=2):
    return sosfilt(butter(order, hz, 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], 'band', fs=SR, output='sos'), x)


def env(n, a, d, sustain=0.0):
    e = np.ones(n) * sustain
    na = max(1, int(a * SR))
    e[:na] = np.linspace(0, 1, na)
    nd = np.arange(n - na)
    e[na:] = np.maximum(sustain, np.exp(-nd / max(1, d * SR)))
    return e


def place(buf, clip, t, gain=1.0):
    i = int(t * SR)
    if i >= len(buf) or i + len(clip) <= 0:
        return
    j0 = max(0, -i)
    clip = clip[j0:]
    i = max(i, 0)
    m = min(len(clip), len(buf) - i)
    buf[i:i + m] += clip[:m] * gain


def reverb(x, seconds=1.6, mix=.25):
    n = int(seconds * SR)
    ir = rng.normal(0, 1, n) * np.exp(-np.arange(n) / (SR * seconds / 5))
    ir = lp(ir, 6000)
    wet = fftconvolve(x, ir)[:len(x)]
    wet *= np.max(np.abs(x)) / (np.max(np.abs(wet)) + 1e-9)
    return x * (1 - mix) + wet * mix


# ------------------------------------------------------------------ engines from telemetry
def telemetry(num):
    t0 = datetime.fromisoformat(CFG['race_start_utc']).timestamp()
    rows = [(datetime.fromisoformat(r['date']).timestamp() - t0, float(r['rpm'] or 0), float(r['throttle'] or 0), float(r['speed'] or 0))
            for r in csv.DictReader(open(DATA / f'mexico2026_lap1_{num}_car.csv'))]
    return np.array(rows)


def engine(num, pan):
    tl = telemetry(num)
    rpm = np.interp(T_DATA, tl[:, 0], tl[:, 1])
    thr = np.interp(T_DATA, tl[:, 0], tl[:, 2]) / 100
    rpm = lp(rpm, 18, 1)
    thr = np.clip(lp(thr, 25, 1), 0, 1)
    pitch = np.where(SPEED > 0, .55 + .45 * np.clip(SPEED, 0, 1), .35)   # slow motion = lower, heavier
    f0 = rpm / 60 * 3 * pitch                                            # V6 four-stroke firing order
    ph = 2 * np.pi * np.cumsum(f0) / SR
    tone = (np.sin(ph * .5) * .55 + np.sin(ph) * 1.0 + np.sin(ph * 1.5) * .35 + np.sin(ph * 2) * .45 + np.sin(ph * 3) * .22 + np.sin(ph * 4) * .12)
    rough = 1 + .25 * np.sin(ph * .25 + 1.3) * (1 - thr)
    load = .35 + .65 * thr
    noise = bp(rng.normal(0, 1, N), 700, 6000) * (.45 + .7 * thr)
    jitter = 1 + .18 * lp(rng.normal(0, 1, N), 40) / .05      # combustion is never perfectly even
    x = np.tanh((tone * rough * np.clip(jitter, .5, 1.5) + noise * .9) * (1.2 + 1.8 * load)) * load
    # lift-off pops and crackles
    lift = np.r_[0, np.diff(thr)] < -0.0004
    pops = (rng.random(N) < .0009) & lift
    crack = np.convolve(pops.astype(float) * rng.uniform(.4, 1, N), np.exp(-np.arange(400) / 60), 'same')
    x = x + bp(crack, 400, 4000) * 1.6
    x = hp(x, 60)
    x = lp(x, np.where(SPEED.mean() > 0, 9000, 9000))
    gain = np.where(SPEED > 0, 1.0, .25) * np.interp(T_DATA, [0, .4, 1.2], [.25, .6, 1])   # quieter on the grid / in freezes
    x *= gain
    left, right = x * np.sqrt(1 - pan), x * np.sqrt(pan)
    return np.stack([left, right], 1)


# ------------------------------------------------------------------ score
BPM = 140
BEAT = 60 / BPM
ROOTS = [57, 53, 48, 55]                       # A minor: Am  F  C  G (MIDI)
CHORDS = {57: [57, 60, 64], 53: [53, 57, 60], 48: [48, 52, 55], 55: [55, 59, 62]}
hz = lambda m: 440 * 2 ** ((m - 69) / 12)


def kick():
    n = int(.45 * SR)
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t * 32)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, .001, .16) * 1.2


def clap():
    n = int(.25 * SR)
    x = bp(rng.normal(0, 1, n), 900, 6000) * env(n, .002, .05)
    return reverb(x, .6, .3) * .8


def hat(open_=False):
    n = int((.18 if open_ else .05) * SR)
    return hp(rng.normal(0, 1, n), 7000) * env(n, .001, .06 if open_ else .012) * .35


def sub(midi, length):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * hz(midi - 24) * t + .3 * np.sin(2 * np.pi * hz(midi - 24) * t))
    return np.tanh(x * 1.6) * env(n, .005, length * .9, .35) * .55


def pad(midi_list, length, bright=1.0):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for m in midi_list:
        for det in (-.12, 0, .11):
            f = hz(m + det)
            x += 2 * ((t * f) % 1) - 1
    x = lp(x / (len(midi_list) * 3), 900 + 2600 * bright)
    e = np.minimum(1, t / .6) * np.minimum(1, (length - t) / .4)
    return x * np.clip(e, 0, 1) * .22


def pluck(midi, length=.35):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = (2 * ((t * hz(midi)) % 1) - 1) * env(n, .002, .12)
    return lp(x, 3500) * .18


def riser(length, lo=300, hi=6000):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = rng.normal(0, 1, n)
    out = np.zeros(n)
    chunks = 32
    for k in range(chunks):
        a, b = k * n // chunks, (k + 1) * n // chunks
        c = lo * (hi / lo) ** (k / chunks)
        out[a:b] = bp(x[a:b], c * .7, min(c * 1.4, SR / 2.3))
    return out * (t / length) ** 2 * .5


def whoosh(length=.55):
    n = int(length * SR)
    t = np.arange(n) / SR
    x = rng.normal(0, 1, n)
    k = np.sin(np.pi * t / length) ** 2
    lo = bp(x, 200, 1800) * k
    return lp(lo, 2500) * .6


def impact():
    n = int(2.8 * SR)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(35 + 60 * np.exp(-t * 6)) / SR) * env(n, .001, .9)
    crash = hp(rng.normal(0, 1, n), 2500) * env(n, .001, .5) * .25
    return reverb(np.tanh(boom * 1.6) + crash, 2.2, .3) * .9


def tick():
    n = int(.08 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * 1850 * t) * env(n, .0005, .012) * .25


def score():
    mus = np.zeros(N)
    sfx = np.zeros(N)
    bars = int(DUR / (BEAT * 4)) + 2

    def section(t):
        for s in shots:
            if s['start'] <= t < s['end']:
                return s['id']
        return 'verdict'

    for b in range(bars):
        root = ROOTS[(b // 1) % 4]
        bar_t = b * BEAT * 4
        sec = section(bar_t + .01)
        quiet = sec in ('intro', 'verdict', 'freeze')
        half = sec in ('t4_slowmo',)
        mus_pad = pad(CHORDS[root], BEAT * 4 + .3, bright=.35 if half or quiet else 1.0)
        place(mus, mus_pad, bar_t, 1.0)
        for k in range(16):  # 16ths
            t = bar_t + k * BEAT / 4
            sec = section(t)
            if sec in ('intro', 'freeze'):
                continue
            if sec == 'verdict':
                if k == 0:
                    place(mus, sub(root, BEAT * 4), t, .7)
                continue
            if half:
                if k in (0, 10):
                    place(mus, kick(), t, .9)
                if k == 8:
                    place(mus, clap(), t, .7)
                if k % 4 == 2:
                    place(mus, hat(), t, .6)
                if k == 0:
                    place(mus, sub(root, BEAT * 4), t)
                continue
            if k in (0, 6, 10):
                place(mus, kick(), t)
            if k in (4, 12):
                place(mus, clap(), t)
            place(mus, hat(open_=(k % 8 == 6)), t, .8 if k % 2 == 0 else .45)
            if k in (0, 6, 10):
                place(mus, sub(root, BEAT * (1.5 if k == 0 else 1.0)), t)
            if sec in ('t1', 'exit', 'run_t4') and k % 2 == 0:
                arp = CHORDS[root] + [CHORDS[root][0] + 12]
                place(mus, pluck(arp[(k // 2) % 4] + 12), t, .9)
        # tactical: snare roll building into the freeze
    tac, fz = SHOT.get('tactical'), SHOT.get('freeze')
    if tac and fz:
        roll_len = min(3.0, tac['end'] - tac['start'])
        n_hits = 24
        for k in range(n_hits):
            t = fz['start'] - roll_len * (1 - (k / n_hits) ** .6)
            place(mus, clap(), t, .25 + .6 * k / n_hits)
        place(sfx, riser(roll_len), fz['start'] - roll_len, .7)
    # duck the score a little under the slow-mo and tactical explanation
    duck = np.ones(N)
    for sid, g in (('t4_slowmo', .75), ('tactical', .8), ('freeze', .6)):
        if sid in SHOT:
            a, b = int(SHOT[sid]['start'] * SR), int(SHOT[sid]['end'] * SR)
            duck[a:b] = g
    mus *= lp(duck, 3, 1)

    # cuts, risers, hits, caption ticks
    for s in shots[1:]:
        place(sfx, whoosh(), s['start'] - .3, .8)
    if 't1' in SHOT:
        place(sfx, riser(2.2, 500, 9000), SHOT['t1']['start'] - 2.2, .6)
        place(sfx, impact(), SHOT['t1']['start'], .55)
    if 't4_slowmo' in SHOT:
        place(sfx, riser(1.6, 200, 3000), SHOT['t4_slowmo']['start'] - 1.6, .5)
        place(sfx, impact(), SHOT['t4_slowmo']['start'], .45)
    if fz:
        place(sfx, impact(), fz['start'], 1.0)
        for k in range(int(fz['end'] - fz['start'])):  # clock ticks during the freeze
            place(sfx, tick(), fz['start'] + .5 + k, 1.4)
    if 'exit' in SHOT:
        place(sfx, impact(), SHOT['exit']['start'], .5)
    if 'verdict' in SHOT:
        place(sfx, impact(), SHOT['verdict']['start'], .8)
    for s in shots:
        for c in s['shot'].get('captions', []):
            if 'at_t' in c:
                t = s['start'] + (c['at_t'] - s['shot']['t'][0]) / max(s['shot'].get('speed', 1), 1e-6)
            else:
                t = s['start'] + c.get('at', 0)
            place(sfx, tick(), t, 1.0)
    return mus, sfx


def stereo(x, width=0.0):
    if x.ndim == 2:
        return x
    d = int(.012 * SR)
    r = np.r_[np.zeros(d), x[:-d]] if width else x
    return np.stack([x, x * (1 - width) + r * width], 1)


def norm(x, peak=.95):
    return x * peak / (np.max(np.abs(x)) + 1e-9)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    nums = list(CFG['drivers'])
    eng = engine(nums[0], .42) + engine(nums[1], .58)
    eng = norm(eng, .5)
    mus, sfx = score()
    mus = norm(stereo(mus, .5), .55)
    sfx = norm(stereo(sfx, .3), .5)
    # music ducks under loud engine moments (only when engines are on), engines duck in the verdict
    if '--engines' in argv:
        eng_env = lp(np.abs(eng).mean(1), 4, 1)
        mus *= (1 - .35 * np.clip(eng_env / (eng_env.max() + 1e-9), 0, 1))[:, None]
    verdict = SHOT.get('verdict')
    if verdict:
        a = int(verdict['start'] * SR)
        fade = np.ones(N)
        fade[a:] = np.linspace(1, .1, N - a)
        eng *= fade[:, None]
    engine_level = .42 if '--engines' in argv else 0.0   # synthetic engines are off unless asked for
    mix = eng * engine_level + mus * 1.25 + sfx * .8
    mix *= .32 / (np.sqrt(np.mean(mix ** 2)) + 1e-9)    # loudness target (social-media level)
    mix = np.tanh(mix * 1.15) / np.tanh(1.15)          # soft limiter
    mix *= .94 / (np.max(np.abs(mix)) + 1e-9)
    end = int(1.2 * SR)
    mix[-end:] *= np.linspace(1, 0, end)[:, None]
    for name, x in (('audio_mix', mix), ('stem_music', mus), ('stem_sfx', sfx), ('stem_engines', eng)):
        wavfile.write(WORK / f'{name}.wav', SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))
    print('Audio', round(DUR, 1), 's ->', WORK / 'audio_mix.wav')
    if VIDEO.exists():
        out = VIDEO.with_name(VIDEO.stem + '.sound.mp4')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(VIDEO), '-i', str(WORK / 'audio_mix.wav'), '-map', '0:v', '-map', '1:a',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-shortest', str(out)], check=True)
        print('Saved', out)
    else:
        print('Video not found, only the WAV files were written:', VIDEO)


if __name__ == '__main__':
    main()
