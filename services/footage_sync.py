"""Sync a user's onboard clip to real telemetry from its engine sound, then burn the HUD in.

How the sync works
------------------
An engine's firing note rises and falls with RPM, and every upshift is a sudden drop in pitch.
1. Track the dominant harmonic ridge of the engine note through the clip (harmonic summation
   over a log-frequency grid, then a Viterbi path so the track stays on one ridge).
2. Coarse: slide the clip's log-pitch along log-RPM from the session car data. Working in logs
   makes the match independent of which engine order the tracker locked onto. The search is
   limited to offsets where the clip covers most of the selected lap, so a different lap of
   the same circuit can't win.
3. Fine: match upshifts heard in the audio to gear increases in the telemetry and take the
   median offset. Car data arrives at roughly 4 Hz, so each shift is only known to about
   ±0.12 s; the median of many shifts is much tighter.

The result is expressed as "the selected lap starts N seconds into your clip", which the user
can nudge before rendering. Nothing here changes lap times or telemetry values.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

SR = 22050
HOP = 256
WIN = 2048
GRID_HZ = 20.0  # common resampling rate for coarse correlation
F0_MIN, F0_MAX, F0_BINS = 40.0, 1000.0, 300
HARMONICS = 6
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}
MAX_ANALYSIS_SEC = 15 * 60
ID_RE = re.compile(r'^[0-9a-f]{32}$')


# ---------------------------------------------------------------- media helpers

def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, **kw)


def probe(path: Path) -> dict[str, Any]:
    out = _run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', str(path)], timeout=60)
    if out.returncode != 0:
        raise ValueError('This file could not be read as a video.')
    info = json.loads(out.stdout or b'{}')
    video = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
    audio = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), None)
    if not video:
        raise ValueError('This file has no video stream.')
    rate = video.get('avg_frame_rate') or video.get('r_frame_rate') or '30/1'
    try:
        fps = Fraction(rate)
        if fps <= 0 or fps > 240:
            raise ValueError
    except (ValueError, ZeroDivisionError):
        fps = Fraction(30, 1)
    width, height = int(video.get('width') or 0), int(video.get('height') or 0)
    # Phones store portrait clips as landscape plus a rotation flag.
    rotation = 0
    for side in video.get('side_data_list', []) or []:
        if 'rotation' in side:
            rotation = int(float(side['rotation']))
    rotation = rotation or int(float((video.get('tags') or {}).get('rotate', 0) or 0))
    if abs(rotation) % 180 == 90:
        width, height = height, width
    duration = float(info.get('format', {}).get('duration') or video.get('duration') or 0)
    if not width or not height or duration <= 0:
        raise ValueError('The video size or length could not be read.')
    return dict(width=width, height=height, fps=float(fps), fps_rational=f'{fps.numerator}/{fps.denominator}',
                duration=duration, has_audio=bool(audio))


def poster(path: Path, out: Path, at: float = 1.0) -> Path:
    r = _run(['ffmpeg', '-y', '-ss', f'{max(0.0, at):.2f}', '-i', str(path), '-frames:v', '1', '-q:v', '3', str(out)], timeout=60)
    if r.returncode != 0 or not out.exists():
        r = _run(['ffmpeg', '-y', '-i', str(path), '-frames:v', '1', '-q:v', '3', str(out)], timeout=60)
    if not out.exists():
        raise ValueError('Could not read a frame from this video.')
    return out


def extract_audio(path: Path, limit: float = MAX_ANALYSIS_SEC) -> np.ndarray:
    r = _run(['ffmpeg', '-v', 'error', '-i', str(path), '-t', f'{limit:.1f}', '-vn', '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], timeout=600)
    if r.returncode != 0:
        raise ValueError('The clip has no readable audio, so it can only be synced by hand.')
    audio = np.frombuffer(r.stdout, dtype=np.float32)
    if audio.size < SR * 5:
        raise ValueError('The clip needs at least five seconds of engine sound to sync automatically.')
    return audio


# ---------------------------------------------------------------- pitch tracking

def _harmonic_matrix(shift: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    f0 = np.geomspace(F0_MIN, F0_MAX, F0_BINS)
    bins = WIN // 2 + 1
    bin_hz = SR / WIN
    m = np.zeros((F0_BINS, bins), dtype=np.float32)
    for i, f in enumerate(f0):
        for k in range(1, HARMONICS + 1):
            pos = (k + shift) * f / bin_hz
            lo = int(pos)
            if lo + 1 >= bins:
                break
            w = 0.86 ** (k - 1)
            frac = pos - lo
            m[i, lo] += w * (1 - frac)
            m[i, lo + 1] += w * frac
    return f0, m


_F0, _HM = _harmonic_matrix()


_RATIOS = np.log(np.array([2.0, 3.0, 1.5, 4.0, 4 / 3, 2.5, 5 / 3, 6.0]))


def _unwrap_harmonic_jumps(logf: np.ndarray) -> np.ndarray:
    """Undo sudden switches between engine harmonics (×2, ×1.5, ×3 …).

    A real onboard has a dense harmonic stack, so the tracker sometimes hops to another harmonic for a few
    seconds, often on long straights. A gear change moves pitch by at most ~25% in one step, so any
    instant jump close to a simple harmonic ratio is treated as a hop and folded back.
    """
    out = logf.copy()
    k = max(1, int(round(0.02 * SR / HOP)))
    offset = 0.0
    i = k
    while i < len(out):
        d = logf[i] - logf[i - k]
        if abs(d) > 0.3:
            j = int(np.argmin(np.abs(np.abs(d) - _RATIOS)))
            if abs(abs(d) - _RATIOS[j]) < 0.08:
                offset -= np.sign(d) * _RATIOS[j]
                at = i - k + 1 + int(np.argmax(np.abs(np.diff(logf[i - k:i + 1]))))  # the frame where it hops
                out[at:] = logf[at:] + offset
                i += k
                continue
        out[i] = logf[i] + offset
        i += 1
    return out


def pitch_track(audio: np.ndarray) -> dict[str, np.ndarray]:
    """Return per-frame times, log-pitch of the tracked engine ridge and a 0–1 clarity score."""
    n = 1 + (len(audio) - WIN) // HOP
    if n < 50:
        raise ValueError('The clip is too short to analyse.')
    window = np.hanning(WIN).astype(np.float32)

    def whitened(idx: np.ndarray) -> np.ndarray:
        frames = audio[idx[:, None] * HOP + np.arange(WIN)[None, :]] * window
        logm = np.log1p(np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32) * 50)
        # Whiten: remove each frame's broadband floor so harmonic peaks stand out.
        logm -= np.median(logm, axis=1, keepdims=True)
        return np.maximum(logm, 0)

    sal = np.empty((n, F0_BINS), dtype=np.float32)
    for start in range(0, n, 2048):  # chunked to keep memory flat for long clips
        idx = np.arange(start, min(n, start + 2048))
        sal[idx] = whitened(idx) @ _HM.T
    # Viterbi: stay on one ridge; small moves are free, big jumps (shifts) cost a little,
    # octave flips cost a lot.
    steps = np.arange(F0_BINS)
    d = np.abs(steps[:, None] - steps[None, :]).astype(np.float32)
    trans = np.where(d <= 2, 0, (d - 2) * 0.06).astype(np.float32)
    norm = sal / (sal.max(axis=1, keepdims=True) + 1e-6)
    score = norm[0].copy()
    back = np.empty((n, F0_BINS), dtype=np.int16)
    for t in range(1, n):
        cand = score[None, :] - trans  # rows: to, cols: from
        best = cand.argmax(axis=1)
        back[t] = best
        score = cand[steps, best] + norm[t]
    path = np.empty(n, dtype=np.int32)
    path[-1] = int(score.argmax())
    for t in range(n - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    times = (np.arange(n) * HOP + WIN / 2) / SR
    logf = _unwrap_harmonic_jumps(np.log(_F0[path]))
    # Clarity: how sharply the harmonic sum peaks at the tracked pitch. Detuning by ~4% knocks the
    # upper harmonics off their peaks for a real engine note. (Loudness-based measures fail on rich
    # onboard audio, where every candidate collects energy.)
    rows = np.arange(n)
    on = sal[rows, path]
    off = (sal[rows, np.clip(path - 4, 0, F0_BINS - 1)] + sal[rows, np.clip(path + 4, 0, F0_BINS - 1)]) / 2
    clarity = np.clip((on - off) / (on + 1e-6) * 2.5, 0, 1)
    return dict(t=times, logf=logf, clarity=clarity)


# ---------------------------------------------------------------- telemetry tracks

def time_axis(frame: pd.DataFrame) -> np.ndarray:
    """Absolute seconds shared by lap telemetry and session car data (UTC date preferred)."""
    if 'date' in frame:
        dates = pd.to_datetime(frame['date'], errors='coerce', utc=True, format='ISO8601')
        if dates.notna().mean() > .9:
            return (dates - pd.Timestamp('2000-01-01', tz='UTC')).dt.total_seconds().to_numpy(dtype=float)
    if 'session_time' in frame and pd.to_numeric(frame['session_time'], errors='coerce').notna().mean() > .9:
        return pd.to_numeric(frame['session_time'], errors='coerce').to_numpy(dtype=float)
    raise ValueError('This telemetry source has no shared clock, so the clip cannot be synced to it.')


@dataclass
class Telemetry:
    t: np.ndarray       # absolute axis seconds
    rpm: np.ndarray
    gear: np.ndarray
    speed: np.ndarray
    throttle: np.ndarray
    brake: np.ndarray
    lap_start: float
    lap_end: float


def build_telemetry(lap: pd.DataFrame, full: pd.DataFrame) -> Telemetry:
    lap_axis = time_axis(lap)
    lap_axis = lap_axis[np.isfinite(lap_axis)]
    if lap_axis.size < 2:
        raise ValueError('The selected lap has no usable timestamps.')
    src = full if full is not None and not full.empty else lap
    t = time_axis(src)
    df = pd.DataFrame(dict(t=t, rpm=pd.to_numeric(src['rpm'], errors='coerce'),
                           gear=pd.to_numeric(src['gear'], errors='coerce'),
                           speed=pd.to_numeric(src['speed_kmh'], errors='coerce'),
                           throttle=pd.to_numeric(src['throttle_pct'], errors='coerce'),
                           brake=src['brake_active'].map(lambda v: 100.0 if bool(v) and not pd.isna(v) else 0.0)))
    df = df.dropna(subset=['t', 'speed']).sort_values('t').drop_duplicates('t')
    df['rpm'] = df['rpm'].interpolate(limit_direction='both')
    df['gear'] = df['gear'].ffill().bfill()
    df['throttle'] = df['throttle'].fillna(0)
    if df['rpm'].isna().all() or (df['rpm'] > 0).sum() < 20:
        raise ValueError('This telemetry has no RPM channel, which the engine-sound sync needs.')
    return Telemetry(df.t.to_numpy(float), df.rpm.to_numpy(float), df.gear.to_numpy(float), df.speed.to_numpy(float),
                     df.throttle.to_numpy(float), df.brake.to_numpy(float), float(lap_axis[0]), float(lap_axis[-1]))


def _resample(t: np.ndarray, v: np.ndarray, grid: np.ndarray) -> np.ndarray:
    return np.interp(grid, t, v, left=np.nan, right=np.nan)


# ---------------------------------------------------------------- offset search

def _ncc_scan(clip: np.ndarray, clip_w: np.ndarray, tel: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Weighted normalised cross-correlation of clip against tel for integer sample offsets."""
    n = len(clip)
    out = np.full(len(offsets), -1.0)
    for i, o in enumerate(offsets):
        seg = tel[o:o + n]
        if len(seg) < n:
            continue
        w = clip_w * np.isfinite(seg)
        if w.sum() < 0.5 * clip_w.sum():
            continue
        s = np.nan_to_num(seg)
        mc = (w * clip).sum() / w.sum()
        ms = (w * s).sum() / w.sum()
        a, b = clip - mc, s - ms
        den = np.sqrt((w * a * a).sum() * (w * b * b).sum())
        if den > 0:
            out[i] = (w * a * b).sum() / den
    return out


def _audio_shifts(track: dict[str, np.ndarray]) -> np.ndarray:
    """Clip times of sharp pitch drops (upshifts)."""
    t, f, c = track['t'], track['logf'], track['clarity']
    k = max(1, int(round(0.035 * SR / HOP)))
    drop = f[2 * k:] - f[:-2 * k]          # change over ~70 ms
    tt = t[k:-k]
    cc = np.minimum(c[2 * k:], c[:-2 * k])
    cand = np.where((drop < -0.07) & (drop > -0.6) & (cc > 0.15))[0]
    events = []
    for i in cand:
        if events and tt[i] - events[-1][0] < 0.25:
            if drop[i] < events[-1][1]:
                events[-1] = (tt[i], drop[i])
            continue
        events.append((tt[i], drop[i]))
    return np.array([e[0] for e in events])


def _telemetry_shifts(tel: Telemetry) -> np.ndarray:
    g = tel.gear
    i = np.where((g[1:] > g[:-1]) & (g[1:] - g[:-1] <= 2))[0]
    return (tel.t[i] + tel.t[i + 1]) / 2


def estimate_offset(track: dict[str, np.ndarray], tel: Telemetry, clip_duration: float) -> dict[str, Any]:
    lap_len = tel.lap_end - tel.lap_start
    # Clip grid
    D = min(clip_duration, track['t'][-1])
    g_clip = np.arange(0, D, 1 / GRID_HZ)
    lf = np.interp(g_clip, track['t'], track['logf'])
    cl = np.interp(g_clip, track['t'], track['clarity'])
    w = np.clip(cl, 0, 1) ** 1.5
    if w.sum() < GRID_HZ * 5 * 0.3:
        raise ValueError("The engine note isn't clear enough in this clip to sync automatically.")
    # Telemetry grid over the window the clip could possibly cover
    need = 0.7 * min(D, lap_len)
    lo = tel.lap_start + need - D
    hi = tel.lap_end - need
    g_tel = np.arange(lo, hi + D + 1 / GRID_HZ, 1 / GRID_HZ)
    rpm = _resample(tel.t, np.where(tel.rpm > 1500, tel.rpm, np.nan), g_tel)
    lr = np.log(rpm)
    offsets = np.arange(0, max(1, int(round((hi - lo) * GRID_HZ)) + 1))
    # Detrend both with a ~4 s high-pass so slow differences (engine order, mic EQ) don't matter.
    def hp(x: np.ndarray) -> np.ndarray:
        s = pd.Series(x)
        return (s - s.rolling(int(4 * GRID_HZ), center=True, min_periods=5).mean()).to_numpy()
    r = _ncc_scan(hp(lf), w, hp(lr), offsets)
    best = int(np.argmax(r))
    r1 = float(r[best])
    far = np.abs(offsets - offsets[best]) > 2 * GRID_HZ
    r2 = float(r[far].max()) if far.any() else -1.0
    coarse = lo + offsets[best] / GRID_HZ   # axis time at clip t=0
    # Fine: every upshift in the data happened somewhere between two telemetry samples. Slide the clip and
    # count how many of those windows contain an upshift heard in the audio; the centre of the best plateau
    # wins. This uses the samples exactly as recorded, with no interpolation bias.
    a_sh = _audio_shifts(track)
    g = tel.gear
    iu = np.where((g[1:] > g[:-1]) & (g[1:] - g[:-1] <= 2))[0]
    lo_ax, hi_ax = tel.t[iu], tel.t[iu + 1]
    fine, spread, matched, in_clip = coarse, None, 0, 0
    if a_sh.size and iu.size:
        cands = np.arange(coarse - 0.5, coarse + 0.5 + 1e-9, 0.005)
        counts = np.zeros(len(cands), dtype=int)
        totals = np.zeros(len(cands), dtype=int)
        for k, z in enumerate(cands):
            lo, hi = lo_ax - z - 0.03, hi_ax - z + 0.03
            m = (lo > 0) & (hi < D)
            totals[k] = m.sum()
            if m.any():
                counts[k] = ((a_sh[None, :] >= lo[m, None]) & (a_sh[None, :] <= hi[m, None])).any(axis=1).sum()
        top = counts.max()
        plateau = cands[counts == top]
        in_clip = int(totals[int(np.argmax(counts))])
        if top >= max(6, 0.35 * in_clip):
            fine = float(np.median(plateau))
            spread = max(0.005, float((plateau.max() - plateau.min()) / 2))
            matched = int(top)
    # Confidence from correlation strength, how unique the peak is, and shift agreement.
    uniq = max(0.0, r1 - r2)
    # Matched gear changes are the strongest evidence on real audio, so they carry the most weight.
    score = 100 * (0.30 * np.clip((r1 - 0.25) / 0.6, 0, 1) + 0.25 * np.clip(uniq / 0.25, 0, 1)
                   + 0.45 * (np.clip(matched / max(in_clip, 1) / 0.6, 0, 1) * np.clip(matched / 10, 0, 1) if spread is not None else 0))
    score = int(round(float(score)))
    level = 'strong' if score >= 70 else 'check' if score >= 45 else 'weak'
    lap_in_clip = tel.lap_start - fine
    # Curves for the page: clip pitch vs RPM at the chosen alignment (decimated).
    step = max(1, len(g_clip) // 900)
    gc = g_clip[::step]
    tel_rpm = _resample(tel.t, tel.rpm, gc + fine)
    return dict(lap_start_in_clip=round(float(lap_in_clip), 3), axis_at_clip_zero=float(fine),
                coarse_lap_start_in_clip=round(float(tel.lap_start - coarse), 3),
                correlation=round(r1, 3), runner_up=round(r2, 3), score=score, level=level,
                shifts=dict(matched=matched, heard=int(a_sh.size), in_data=in_clip,
                            spread_ms=None if spread is None else round(spread * 1000)),
                lap_length=round(lap_len, 3),
                curve=dict(t=np.round(gc, 2).tolist(),
                           pitch=np.round(np.exp(np.interp(gc, track['t'], track['logf'])), 1).tolist(),
                           clarity=np.round(np.interp(gc, track['t'], track['clarity']), 2).tolist(),
                           rpm=[None if not np.isfinite(v) else round(float(v)) for v in tel_rpm]),
                audio_shifts=np.round(a_sh, 3).tolist())


def telemetry_for_page(tel: Telemetry, lap_in_clip: float, clip_duration: float) -> dict[str, list]:
    """Telemetry around the clip, in clip-relative seconds at the auto-sync result, for live checking."""
    zero = tel.lap_start - lap_in_clip
    m = (tel.t >= zero - 30) & (tel.t <= zero + clip_duration + 30)
    rel = tel.t[m] - tel.lap_start
    return dict(t_from_lap_start=np.round(rel, 3).tolist(), speed=np.round(tel.speed[m]).tolist(),
                rpm=np.round(tel.rpm[m]).tolist(), gear=[int(g) for g in tel.gear[m]],
                throttle=np.round(tel.throttle[m]).tolist(), brake=np.round(tel.brake[m]).tolist())


# ---------------------------------------------------------------- burn-in render

def hud_position(preset: str, canvas: tuple[int, int], hud: tuple[int, int], x: int, y: int) -> tuple[int, int]:
    W, H = canvas
    hw, hh = hud
    mx, mb = round(W * 0.04), round(H * 0.05)
    if preset == 'Custom':
        px, py = x, y
    elif preset == 'Bottom center':
        px, py = (W - hw) // 2, H - hh - mb
    elif preset == 'Bottom right':
        px, py = W - hw - mx, H - hh - mb
    else:
        px, py = mx, H - hh - mb
    return int(np.clip(px, 0, max(0, W - hw))), int(np.clip(py, 0, max(0, H - hh)))


def render_burn_in(footage: Path, info: dict[str, Any], tel: Telemetry, lap_in_clip: float, *, assets_dir: Path,
                   out_path: Path, hud_width: int, position: str, x: int, y: int, hud_year: int | None,
                   progress: Callable[[float, str], None]) -> dict[str, Any]:
    from PIL import Image
    from services.hud_renderer import SpriteHUD
    hud = SpriteHUD(assets_dir)
    bw, bh = hud.base_size
    hw = int(hud_width) - int(hud_width) % 2
    hh = int(round(bh * hw / bw)); hh -= hh % 2
    W, H = info['width'], info['height']
    if hw > W or hh > H:
        raise ValueError('The HUD is larger than the video. Choose a smaller HUD size.')
    px, py = hud_position(position, (W, H), (hw, hh), x, y)
    fps = Fraction(info['fps_rational'])
    n = int(round(info['duration'] * float(fps)))
    zero = tel.lap_start - lap_in_clip
    times = zero + np.arange(n) / float(fps)
    inside = (times >= tel.t[0]) & (times <= tel.t[-1])
    speed = np.interp(times, tel.t, tel.speed)
    rpm = np.interp(times, tel.t, tel.rpm)
    thr = np.interp(times, tel.t, tel.throttle)
    brk = np.interp(times, tel.t, tel.brake)
    gi = np.clip(np.searchsorted(tel.t, times, side='right') - 1, 0, len(tel.t) - 1)
    gear = tel.gear[gi]
    blank = bytes(hw * hh * 4)
    tmp = out_path.with_name(out_path.stem + '.partial' + out_path.suffix)
    cmd = ['ffmpeg', '-y', '-v', 'error', '-i', str(footage),
           '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{hw}x{hh}', '-framerate', info['fps_rational'], '-i', 'pipe:0',
           '-filter_complex', f'[0:v][1:v]overlay={px}:{py}:eof_action=pass:format=auto[v]',
           '-map', '[v]', '-map', '0:a?', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    last_key = None
    last_bytes = blank
    try:
        for i in range(n):
            if inside[i]:
                row = dict(speed_kmh=speed[i], rpm=rpm[i], throttle=thr[i], brake=brk[i], gear=int(gear[i]))
                key = (int(round(speed[i])), int(round(rpm[i])), int(round(thr[i])), int(round(brk[i])), int(gear[i]))
                if key != last_key:  # identical readouts reuse the previous frame
                    img = Image.fromarray(hud.render_rgba(row, hud_year=hud_year), 'RGBA').resize((hw, hh), Image.Resampling.LANCZOS)
                    last_bytes, last_key = img.tobytes(), key
                proc.stdin.write(last_bytes)
            else:
                proc.stdin.write(blank)
            if i % 30 == 0:
                progress(0.12 + 0.83 * i / max(1, n), f'Drawing the HUD on frame {i:,} of {n:,}')
        proc.stdin.close()
        err = proc.stderr.read().decode(errors='replace')
        code = proc.wait(timeout=600)
        if code != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            raise RuntimeError('FFmpeg could not finish the video.\n' + err[-1500:])
        tmp.replace(out_path)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        tmp.unlink(missing_ok=True)
        raise
    return dict(frames=n, hud=dict(x=px, y=py, width=hw, height=hh), lap_in_clip=lap_in_clip)


def remove_upload(folder: Path, key: str) -> None:
    if ID_RE.match(key):
        for p in folder.glob(key + '*'):
            p.unlink(missing_ok=True)


__all__ = ['probe', 'poster', 'extract_audio', 'pitch_track', 'build_telemetry', 'estimate_offset',
           'telemetry_for_page', 'render_burn_in', 'hud_position', 'VIDEO_EXT', 'ID_RE']
