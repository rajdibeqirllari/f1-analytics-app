"""Builds the Lusail venue in Blender from assets/3d/qatar/lusail_layout.json, saves the .blend and exports the GLB.

Run (from C:\\f1hud_app):
  tools\\blender\\blender-4.5.9-windows-x64\\blender.exe --background --factory-startup --python-exit-code 1 ^
      --python scripts\\qatar\\build_lusail_blend.py

Coordinates: Blender X east, Y north, Z up, metres = the Lusail frame minus ORIGIN (stored in the manifest).
glTF's +Y-up export turns (x, y, z) into (x, z, -y), the same mapping the browser engine uses for the track plane.

What is measured and what is reconstructed is written next to each layer below and repeated in the manifest.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / 'assets/3d/qatar/lusail_layout.json'
TEX = ROOT / 'assets/3d/qatar/textures'
BLEND = ROOT / 'assets/3d/qatar/blender/lusail.blend'
GLB = ROOT / 'frontend/public/venues/lusail/lusail.glb'
MANIFEST = ROOT / 'frontend/public/venues/lusail/manifest.json'
CHUNK = 100   # stations per chunk (~200 m)

D = json.loads(LAYOUT.read_text(encoding='utf-8'))
CX, CY = np.array(D['centre']['x']), np.array(D['centre']['y'])
ORIGIN = (round(float(CX.mean()), 1), round(float(CY.mean()), 1))
C = np.c_[CX - ORIGIN[0], CY - ORIGIN[1]]
Z = np.array(D['centre']['z'])
N_ST = len(C)
STEP = D['step']
LEN = D['length']
T = np.roll(C, -3, 0) - np.roll(C, 3, 0)
T /= np.linalg.norm(T, axis=1)[:, None]
NL = np.c_[-T[:, 1], T[:, 0]]                      # unit normal to the left of the driving direction
EL, ER = np.array(D['edges']['left']), np.array(D['edges']['right'])
LINE = np.array(D['driven_line'])
KAPPA = np.array(D['curvature'])
LM = D['landmarks']
CORNERS = LM['corners']
PIT = np.c_[np.array(D['pit']['x']) - ORIGIN[0], np.array(D['pit']['y']) - ORIGIN[1]]
S = np.arange(N_ST) * STEP


def wrap(i):
    return i % N_ST


def st_of(m):
    return int(round((m % LEN) / STEP)) % N_ST


def P(i, off, dz=0.0):
    i = wrap(i)
    return (float(C[i, 0] + NL[i, 0] * off), float(C[i, 1] + NL[i, 1] * off), float(Z[i] + dz))


def ground_z(x, y):
    """Height of the ground under a point: the nearest centreline station's height (track is flat across)."""
    i = int(np.argmin((C[:, 0] - x) ** 2 + (C[:, 1] - y) ** 2))
    return float(Z[i]), i


# ------------------------------------------------------------------ scene + materials
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0


_img_cache = {}


def img(name, non_color=False):
    if name not in _img_cache:
        im = bpy.data.images.load(str(TEX / name))
        if non_color:
            im.colorspace_settings.name = 'Non-Color'
        _img_cache[name] = im
    return _img_cache[name]


def material(name, color=(0.5, 0.5, 0.5, 1), rough=0.8, metal=0.0, albedo=None, normal=None, orm=None, alpha=None,
             emissive=None, emit_strength=1.0, emit_color=None, vcol=False, nscale=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if albedo or alpha:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img(albedo or alpha)
        if vcol:
            ca = nt.nodes.new('ShaderNodeVertexColor')
            mix = nt.nodes.new('ShaderNodeMix')
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs['Factor'].default_value = 1.0
            nt.links.new(t.outputs['Color'], mix.inputs['A'])
            nt.links.new(ca.outputs['Color'], mix.inputs['B'])
            nt.links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
        else:
            nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
        if alpha:
            nt.links.new(t.outputs['Alpha'], bsdf.inputs['Alpha'])
            m.blend_method = 'CLIP' if hasattr(m, 'blend_method') else None
    elif vcol:
        ca = nt.nodes.new('ShaderNodeVertexColor')
        nt.links.new(ca.outputs['Color'], bsdf.inputs['Base Color'])
    if normal:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img(normal, True)
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = nscale
        nt.links.new(t.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    if orm:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img(orm, True)
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(t.outputs['Color'], sep.inputs['Color'])
        nt.links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
        nt.links.new(sep.outputs['Blue'], bsdf.inputs['Metallic'])
    if emissive:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img(emissive)
        nt.links.new(t.outputs['Color'], bsdf.inputs['Emission Color'])
        bsdf.inputs['Emission Strength'].default_value = emit_strength
    elif emit_color:
        bsdf.inputs['Emission Color'].default_value = emit_color
        bsdf.inputs['Emission Strength'].default_value = emit_strength
    return m


MATS = {}


def mats():
    MATS['asphalt'] = material('LUS_asphalt', albedo='asphalt_albedo.jpg', normal='asphalt_normal.png', orm='asphalt_orm.png', vcol=True, nscale=0.6)
    MATS['paint'] = material('LUS_paint', albedo='paint_mask.jpg', normal='paint_normal.png', rough=0.62, vcol=True, nscale=0.5)
    MATS['kerb'] = material('LUS_kerb', albedo='kerb_wear.jpg', normal='kerb_normal.png', rough=0.55, vcol=True)
    MATS['concrete'] = material('LUS_concrete', albedo='concrete_albedo.jpg', normal='concrete_normal.png', rough=0.85)
    MATS['boards'] = material('LUS_boards', color=(0.32, 0.05, 0.13, 1), rough=0.5)       # maroon boards, no text
    MATS['fence'] = material('LUS_fence', alpha='fence_rgba.png', rough=0.4, metal=0.8)
    MATS['metal'] = material('LUS_metal', color=(0.55, 0.57, 0.6, 1), rough=0.35, metal=0.9)
    MATS['dark_metal'] = material('LUS_dark_metal', color=(0.12, 0.13, 0.14, 1), rough=0.45, metal=0.7)
    MATS['white_clad'] = material('LUS_white_cladding', color=(0.82, 0.83, 0.84, 1), rough=0.4, metal=0.1)
    MATS['facade'] = material('LUS_facade', albedo='facade_albedo.jpg', emissive='facade_emissive.jpg', emit_strength=2.0, rough=0.15, metal=0.3)
    MATS['garage'] = material('LUS_garage_interior', color=(0.8, 0.82, 0.86, 1), rough=0.5, emit_color=(0.92, 0.95, 1.0, 1), emit_strength=1.6)
    MATS['purple'] = material('LUS_led_purple', color=(0.3, 0.05, 0.35, 1), emit_color=(0.62, 0.12, 0.85, 1), emit_strength=6.0)
    MATS['lamp'] = material('LUS_lamp', color=(1, 1, 1, 1), emit_color=(1.0, 0.97, 0.9, 1), emit_strength=25.0)
    MATS['seats'] = material('LUS_seats', albedo='seats_albedo.jpg', rough=0.6)
    MATS['crowd'] = material('LUS_crowd', albedo='crowd_albedo.jpg', rough=0.9)
    MATS['sand'] = material('LUS_sand', albedo='sand_albedo.jpg', rough=0.95)
    MATS['turf'] = material('LUS_turf', albedo='turf_albedo.jpg', rough=0.9)
    MATS['roof'] = material('LUS_roof', color=(0.88, 0.88, 0.86, 1), rough=0.35, metal=0.2)
    MATS['tecpro'] = material('LUS_tecpro', vcol=True, rough=0.6)
    MATS['board_face'] = material('LUS_brake_board', color=(0.92, 0.92, 0.9, 1), rough=0.5)


def mesh_obj(name, verts, faces, mat, uvs=None, cols=None, parent=None, coll=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate(clean_customdata=False)
    if uvs is not None:
        uv = me.uv_layers.new(name='UVMap')
        flat = []
        for f in me.polygons:
            for li in f.loop_indices:
                flat.extend(uvs[me.loops[li].vertex_index])
        uv.data.foreach_set('uv', flat)
    if cols is not None:
        ca = me.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
        flat = []
        for c in cols:
            flat.extend((c[0], c[1], c[2], 1.0))
        ca.data.foreach_set('color', flat)
        me.color_attributes.active_color = ca
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    (coll or bpy.context.scene.collection).objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


# ------------------------------------------------------------------ strips along the circuit
def strip(i0, i1, offs, lift, uv_scale=(4.0, 4.0), color=None, zfun=None):
    """Quads between consecutive stations i0..i1 (inclusive) across lateral offsets offs(i) (right -> left).
    UV: u = lateral metres / uv_scale[0], v = lap metres / uv_scale[1]. color(i, lateral) -> rgb per vertex."""
    verts, faces, uvs, cols = [], [], [], []
    k = None
    for s in range(i0, i1 + 1):
        i = wrap(s)
        o = offs(i)
        if k is None:
            k = len(o)
        for j, off in enumerate(o):
            dz = lift if zfun is None else zfun(i, j, off)
            verts.append(P(i, off, dz))
            uvs.append((off / uv_scale[0], (s * STEP) / uv_scale[1]))
            if color:
                cols.append(color(i, off))
    rows = i1 - i0 + 1
    for r in range(rows - 1):
        for j in range(k - 1):
            a = r * k + j
            faces.append((a, a + k, a + k + 1, a + 1))
    return verts, faces, uvs, (cols if color else None)


def flat_strip(i0, i1, offs, lift, uv_scale, colorq, zfun=None):
    """Like strip(), but every quad has its own four vertices and one colour colorq(i, j) (j = lateral band index):
    painted stripes and kerb blocks keep hard edges instead of blending between stations."""
    verts, faces, uvs, cols = [], [], [], []
    for s_ in range(i0, i1):
        i, k = wrap(s_), wrap(s_ + 1)
        oi, ok_ = offs(i), offs(k)
        for j in range(len(oi) - 1):
            c = colorq(i, j)
            base = len(verts)
            for (st, o_, jj, ss) in ((i, oi[j], j, s_), (k, ok_[j], j, s_ + 1), (k, ok_[j + 1], j + 1, s_ + 1), (i, oi[j + 1], j + 1, s_)):
                dz = lift if zfun is None else zfun(st, jj, o_)
                verts.append(P(st, o_, dz))
                uvs.append((o_ / uv_scale[0], (ss * STEP) / uv_scale[1]))
                cols.append(c)
            faces.append((base, base + 1, base + 2, base + 3))
    return verts, faces, uvs, cols


def build_road(coll):
    """Asphalt between the OSM edges (measured). Vertex colour: rubbered line along the measured median driven
    line (darker, slightly glossier in the browser), dust towards the edges (reconstructed look)."""
    def offs(i):
        r, l = -ER[i], EL[i]
        return list(np.linspace(r, l, 9))

    def col(i, off):
        d = off - LINE[i]
        rub = 0.80 + 0.20 * (1 - math.exp(-(d * d) / (2 * 1.1 ** 2)))       # 20 % darker on the line
        edge = min(EL[i] - off, off + ER[i])
        dust = 0.08 * max(0.0, 1 - edge / 1.2)
        v = min(1.0, rub + dust)
        return (v, v, v * 1.01)
    out = []
    for c0 in range(0, N_ST, CHUNK):
        v, f, uv, cl = strip(c0, min(c0 + CHUNK, N_ST), offs, 0.0, (4.0, 4.0), col)
        out.append(mesh_obj(f'road.{c0 // CHUNK:02d}', v, f, MATS['asphalt'], uv, cl, coll=coll))
    return out


def kerb_spans():
    """Where kerbs sit (reconstructed from photos and corner geometry; per-corner lengths are estimates):
    inside of every corner around the apex, outside on exit, outside on entry of the slow corners."""
    spans = []   # (side, s0, s1)  side +1 left / -1 right, s in metres
    for c in CORNERS:
        inside = 1 if c['dir'] == 'L' else -1
        r = c['radius']
        a = min(60, max(18, 0.45 * r))
        b = min(45, max(14, 0.30 * r))
        spans.append((inside, c['station'] - a, c['station'] + b))
        e0 = c['station'] + min(40, 0.25 * r)
        spans.append((-inside, e0, e0 + min(70, max(30, 0.5 * r))))
        if r < 80:
            spans.append((-inside, c['station'] - 0.9 * r - 30, c['station'] - 0.6 * r))
    return spans


def kerb_mask():
    m = {1: np.zeros(N_ST, bool), -1: np.zeros(N_ST, bool)}
    for side, s0, s1 in kerb_spans():
        for s in np.arange(s0, s1, STEP):
            m[side][st_of(s)] = True
    return m


def runs(mask):
    """Contiguous True runs of a circular mask as (start, end) station indices (end inclusive, may exceed N)."""
    idx = np.where(mask)[0]
    if not len(idx):
        return []
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i != prev + 1:
            out.append((start, prev))
            start = i
        prev = i
    out.append((start, prev))
    if len(out) > 1 and out[0][0] == 0 and out[-1][1] == N_ST - 1:
        s, e = out.pop()
        out[0] = (s, out[0][1] + N_ST)
    return out


KW = 1.4   # kerb width (m)


def build_kerbs(coll, km):
    red, white = (0.62, 0.05, 0.06), (0.93, 0.93, 0.92)
    objs = []
    for side in (1, -1):
        for n_, (a, b) in enumerate(runs(km[side])):
            def offs(i, side=side):
                e = EL[i] if side > 0 else -ER[i]
                return [e, e + side * KW * 0.5, e + side * KW] if side > 0 else [e - KW, e - KW * 0.5, e][::1]

            def offs2(i, side=side):
                e = EL[i] if side > 0 else -ER[i]
                o = [e, e + 0.35 * side, e + 0.9 * side, e + KW * side]
                return sorted(o)

            def col(i, off):
                return red if int((S[i]) / 2.0) % 2 == 0 else white

            def zf(i, j, off, side=side, a=a, b=b):
                e = EL[i] if side > 0 else -ER[i]
                d = abs(off - e)
                # flat kerb rising 4 cm, rounded inner lip; tapered at the ends of the run
                k = min(1.0, (min(i - a % N_ST if i >= a % N_ST else i + N_ST - a % N_ST, 1e9)) / 4 + 0.2)
                return 0.012 + 0.035 * min(1.0, d / 0.35)
            v, f, uv, cl = flat_strip(a, b, offs2, 0.0, (1.0, 1.0), lambda i, j: red if int(S[i] / 2.0 + 0.01) % 2 == 0 else white, zf)
            objs.append(mesh_obj(f'kerb.{"L" if side > 0 else "R"}{n_:02d}', v, f, MATS['kerb'], uv, cl, coll=coll))
    return objs


def free_distance(side):
    """How far the run-off may extend on one side before another part of the circuit (or the pit lane) is near."""
    from scipy.spatial import cKDTree  # noqa: F401  (Blender's numpy has no scipy; fall back below)


def reach(side):
    """Distance from the centreline to the nearest other part of the circuit along the normal, per station."""
    out = np.full(N_ST, 200.0)
    sub = np.arange(0, N_ST, 3)
    for i in range(0, N_ST, 2):
        for o in range(10, 200, 4):
            x, y = C[i] + NL[i] * side * o
            d2 = (C[sub, 0] - x) ** 2 + (C[sub, 1] - y) ** 2
            gap = np.abs(S[sub] - S[i])
            gap = np.minimum(gap, LEN - gap)
            near = (gap > 120) & (d2 < (14) ** 2)
            if near.any():
                out[i] = o - 14
                break
        if i + 1 < N_ST:
            out[i + 1] = out[i]
    return np.maximum(out, 0)


def pit_lateral():
    """Lateral position (right negative) of the pit lane centre beside each station, NaN where it is away."""
    lat = np.full(N_ST, np.nan)
    for p in PIT:
        i = int(np.argmin(((C - p) ** 2).sum(1)))
        lat[i] = float((p - C[i]) @ NL[i])
    ok = ~np.isnan(lat)
    idx = np.where(ok)[0]
    filled = lat.copy()
    for a, b in zip(idx[:-1], idx[1:]):
        if 0 < b - a < 12:
            filled[a:b + 1] = np.interp(np.arange(a, b + 1), [a, b], [lat[a], lat[b]])
    return filled


def corner_weight():
    """0..1 bump around each corner's outside (where run-off is deep), from the apex to well past it."""
    w = {1: np.zeros(N_ST), -1: np.zeros(N_ST)}
    for c in CORNERS:
        outside = -1 if c['dir'] == 'L' else 1
        for k in range(-60, 120):
            i = st_of(c['station'] + k * STEP * 0.5)
            g = math.exp(-((k * STEP * 0.5 - 25) / 55) ** 2)
            w[outside][i] = max(w[outside][i], g * min(1, 120 / max(40, c['radius'])))
    return w


def build_runoff(coll, km, pitlat):
    """Painted asphalt run-off (reconstructed from 2024-25 photos: maroon paint, a pale-blue/white striped band beyond
    the line on the straights). Depth: 4 m base, deeper on corner outsides, limited by other track parts / pit wall."""
    cw = corner_weight()
    maroon, blue, white = (0.42, 0.07, 0.19), (0.45, 0.62, 0.78), (0.9, 0.9, 0.9)
    widths = {}
    objs = []
    for side in (1, -1):
        rch = reach(side)
        width = 4.0 + 20.0 * cw[side]
        width = np.minimum(width, np.maximum(1.0, rch - (EL if side > 0 else ER) - 3))
        if side < 0:   # pit wall on the right of the straight
            pw = -pitlat - 5.2 - ER
            m = ~np.isnan(pw)
            width[m] = np.minimum(width[m], np.maximum(0.4, pw[m] - 0.9))
        width = np.convolve(np.r_[width[-9:], width, width[:9]], np.ones(9) / 9, 'same')[9:-9]
        widths[side] = width
        straight = np.abs(KAPPA) < 1 / 600

        def offs(i, side=side):
            e = EL[i] if side > 0 else -ER[i]
            start = e + side * (KW if km[side][i] else 0.0)
            band = side * 1.6
            o = [start, start + band, e + side * (KW + width[i] if km[side][i] else width[i])]
            if abs(o[2] - start) < abs(band) + 0.2:
                o = [start, start + side * 0.1, start + side * max(0.3, abs(o[2] - start))]
            return sorted(o)

        def col(i, off, side=side):
            e = EL[i] if side > 0 else -ER[i]
            d = abs(off - e)
            if straight[i] and not km[side][i] and d <= 1.65:
                return blue if int(S[i] / 3.0) % 2 == 0 else white
            return maroon
        def colq(i, j, side=side):
            if j == 0 and straight[i] and not km[side][i]:
                return blue if int(S[i] / 4.0) % 2 == 0 else white
            return maroon
        for c0 in range(0, N_ST, CHUNK):
            v, f, uv, cl = flat_strip(c0, min(c0 + CHUNK, N_ST), offs, -0.01, (2.0, 2.0), colq)
            objs.append(mesh_obj(f'runoff.{"L" if side > 0 else "R"}{c0 // CHUNK:02d}', v, f, MATS['paint'], uv, cl, coll=coll))
    return objs, widths


def build_lines(coll, km):
    """White edge lines (0.2 m) on the asphalt edge where there is no kerb; start, control line, grid (measured
    slot stations), pit-exit blend line (reconstructed)."""
    white = (0.95, 0.95, 0.94)
    objs = []
    for side in (1, -1):
        m = ~km[side]
        for n_, (a, b) in enumerate(runs(m)):
            def offs(i, side=side):
                e = EL[i] if side > 0 else -ER[i]
                return sorted([e, e - side * 0.2])
            v, f, uv, cl = strip(a, b, offs, 0.006, (1.0, 1.0), lambda i, o: white)
            objs.append(mesh_obj(f'line.{"L" if side > 0 else "R"}{n_:02d}', v, f, MATS['paint'], uv, cl, coll=coll))
    # transverse lines + grid boxes as one mesh
    verts, faces, uvs, cols = [], [], [], []

    def quad(i, s_off0, s_off1, l0, l1, c, lift=0.008):
        """Rectangle between lap offsets (m, along) and laterals at station i (straight sections only)."""
        base = len(verts)
        for ds, l in ((s_off0, l0), (s_off1, l0), (s_off1, l1), (s_off0, l1)):
            x = C[i] + T[i] * ds + NL[i] * l
            verts.append((float(x[0]), float(x[1]), float(Z[i] + lift)))
            uvs.append((l, ds))
            cols.append(c)
        faces.append((base, base + 1, base + 2, base + 3))
    i_ctrl = st_of(LM['control_line'])
    for k in range(16):                         # chequered control line (2 rows)
        w = (EL[i_ctrl] + ER[i_ctrl]) / 16
        for r in range(2):
            c = (0.95, 0.95, 0.94) if (k + r) % 2 == 0 else (0.05, 0.05, 0.05)
            quad(i_ctrl, -0.4 + r * 0.4, r * 0.4, -ER[i_ctrl] + k * w, -ER[i_ctrl] + (k + 1) * w, c)
    i_st = st_of(LM['start_line'])
    quad(i_st, -0.15, 0.15, -ER[i_st] + 0.2, EL[i_st] - 0.2, white)
    for g in LM['grid']:                        # grid slots: stations measured, side estimated (pole on the right)
        i = st_of(g['station'])
        lat = -2.6 if g['slot'] % 2 == 1 else 2.6
        front = (LM['start_line'] - (g['slot'] - 1) * 8.0) - g['station'] - 1.0 if g['slot'] == 1 else 2.6
        # box: front bar + side brackets ahead of the car's centre
        quad(i, front - 0.1, front + 0.1, lat - 1.1, lat + 1.1, white)
        quad(i, front - 1.0, front + 0.1, lat - 1.1, lat - 0.95, white)
        quad(i, front - 1.0, front + 0.1, lat + 0.95, lat + 1.1, white)
    objs.append(mesh_obj('lines.transverse', verts, faces, MATS['paint'], uvs, cols, coll=coll))
    return objs


def poly_strip(pts, half, lift, uv=4.0):
    verts, faces, uvs = [], [], []
    d = 0.0
    for k, p in enumerate(pts):
        a, b = pts[max(0, k - 1)], pts[min(len(pts) - 1, k + 1)]
        t = np.array(b[:2]) - np.array(a[:2])
        t /= max(1e-9, np.linalg.norm(t))
        n = np.array([-t[1], t[0]])
        if k:
            d += float(np.hypot(*(np.array(p[:2]) - np.array(pts[k - 1][:2]))))
        for s_ in (-1, 1):
            q = np.array(p[:2]) + n * half * s_
            verts.append((float(q[0]), float(q[1]), float(p[2] + lift)))
            uvs.append((s_ * half / uv, d / uv))
    for k in range(len(pts) - 1):
        a = 2 * k
        faces.append((a, a + 2, a + 3, a + 1))
    return verts, faces, uvs


def wall_mesh(path, h0, h1, thick=0.0):
    """Vertical band along a polyline of (x, y, z): from z+h0 to z+h1 (both faces drawn by the material)."""
    verts, faces, uvs = [], [], []
    d = 0.0
    for k, p in enumerate(path):
        if k:
            d += float(np.hypot(p[0] - path[k - 1][0], p[1] - path[k - 1][1]))
        verts += [(p[0], p[1], p[2] + h0), (p[0], p[1], p[2] + h1)]
        uvs += [(d / 2.0, h0 / 2.0), (d / 2.0, h1 / 2.0)]
    for k in range(len(path) - 1):
        a = 2 * k
        faces.append((a, a + 2, a + 3, a + 1))
    return verts, faces, uvs


def build_barriers(coll, km, widths, pitlat):
    """Concrete wall (1.05 m) + debris fence (to 3.6 m) at the outer edge of the run-off on both sides, maroon board
    band on the wall face. Positions reconstructed (follow the run-off depth); the pit wall uses the OSM pit lane."""
    objs = []
    instances = dict(poles=[], tecpro=[])
    for side in (1, -1):
        e = EL if side > 0 else ER
        lat = side * (e + np.where(km[side], KW, 0) + widths[side] + 0.6)
        if side < 0:
            m = ~np.isnan(pitlat)
            lat[m] = np.maximum(lat[m], pitlat[m] + 5.6)   # pit wall: between track and pit fast lane
        lat = np.convolve(np.r_[lat[-7:], lat, lat[:7]], np.ones(7) / 7, 'same')[7:-7]
        for c0 in range(0, N_ST, CHUNK):
            path = [P(i, lat[wrap(i)]) for i in range(c0, min(c0 + CHUNK, N_ST) + 1)]
            v, f, uv = wall_mesh(path, -0.3, 1.05)
            objs.append(mesh_obj(f'wall.{"L" if side > 0 else "R"}{c0 // CHUNK:02d}', v, f, MATS['concrete'], uv, coll=coll))
            v, f, uv = wall_mesh([(x, y, z) for x, y, z in path], 0.15, 0.95)
            # board band slightly in front of the wall face (towards the track)
            path_b = [P(i, lat[wrap(i)] - side * 0.04) for i in range(c0, min(c0 + CHUNK, N_ST) + 1)]
            v, f, uv = wall_mesh(path_b, 0.18, 0.92)
            objs.append(mesh_obj(f'boards.{"L" if side > 0 else "R"}{c0 // CHUNK:02d}', v, f, MATS['boards'], uv, coll=coll))
            path_f = [P(i, lat[wrap(i)] + side * 0.1) for i in range(c0, min(c0 + CHUNK, N_ST) + 1)]
            for i in range(c0, min(c0 + CHUNK, N_ST), 2 if c0 % 2 == 0 else 2):
                if True:     # a post every 2 stations (~4 m)
                    x, y, z = P(i, lat[wrap(i)] + side * 0.12)
                    instances.setdefault('posts', []).append([round(x, 2), round(y, 2), round(z, 2), round(math.atan2(T[wrap(i), 1], T[wrap(i), 0]), 3)])
            v, f, uv = wall_mesh(path_f, 1.05, 3.6)
            uv = [(u * 4.0, w * 4.0) for u, w in uv]                       # fence tile 0.5 m
            objs.append(mesh_obj(f'fence.{"L" if side > 0 else "R"}{c0 // CHUNK:02d}', v, f, MATS['fence'], uv, coll=coll))
        # Floodlight poles: every 42 m on each side, staggered, 4 m behind the wall (spacing/height from photos).
        for s in np.arange(0 if side > 0 else 21, LEN, 42):
            i = st_of(s)
            o = lat[i] + side * 4.0
            x, y, z = P(i, o)
            if not np.isnan(pitlat[i]) and side < 0:
                continue                     # pit building side: lights are on the building
            instances['poles'].append([round(x, 2), round(y, 2), round(z, 2), round(math.atan2(-NL[i, 1] * side, -NL[i, 0] * side), 4)])
    return objs, instances


def build_pit(coll, pitlat):
    """Pit lane surface (OSM path, 10.5 m: fast lane + working lane, widths estimated), garage apron, lines."""
    pts = []
    for p in PIT:
        z, _ = ground_z(*p)
        pts.append((float(p[0]), float(p[1]), z))
    pts = pts[::2]
    # fast lane on the OSM line, working lane towards the garages (to the right of the direction of travel)
    v, f, uv = poly_strip(pts, 3.4, -0.005)
    objs = [mesh_obj('pit.fast_lane', v, f, MATS['asphalt'], uv, [(0.86, 0.86, 0.86)] * len(v), coll=coll)]
    work = []
    for k, p in enumerate(pts):
        a, b = pts[max(0, k - 1)], pts[min(len(pts) - 1, k + 1)]
        t = np.array(b[:2]) - np.array(a[:2])
        t /= max(1e-9, np.linalg.norm(t))
        n = np.array([-t[1], t[0]])
        q = np.array(p[:2]) - n * 5.2
        work.append((float(q[0]), float(q[1]), p[2]))
    v, f, uv = poly_strip(work, 1.9, -0.004)
    objs.append(mesh_obj('pit.work_lane', v, f, MATS['paint'], uv, [(0.32, 0.33, 0.35)] * len(v), coll=coll))
    return objs, pts


def extrude(name, ring, z0, h, mat, coll, top_mat=None):
    """Prism from a footprint ring (x, y) at base z0, height h."""
    bm = bmesh.new()
    if np.allclose(ring[0], ring[-1]):
        ring = ring[:-1]
    vs = [bm.verts.new((float(x), float(y), z0)) for x, y in ring]
    try:
        face = bm.faces.new(vs)
    except ValueError:
        bm.free()
        return None
    bmesh.ops.recalc_face_normals(bm, faces=[face])
    if face.normal.z < 0:
        face.normal_flip()
    r = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top, vec=(0, 0, h))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    coll.objects.link(ob)
    return ob


def along(i, ds, lat, dz=0.0):
    i = wrap(i)
    x = C[i] + T[i] * ds + NL[i] * lat
    return (float(x[0]), float(x[1]), float(Z[i] + dz))


def box_along(name, s0, s1, l0, l1, z0, z1, mat, coll, step=8.0):
    """A box following the circuit between lap metres s0..s1 and laterals l0..l1 (heights relative to the track)."""
    verts, faces = [], []
    ss = list(np.arange(s0, s1, step)) + [s1]
    for k, s in enumerate(ss):
        i = st_of(s)
        ds = s - S[i] if abs(s - S[i]) < 5 else 0
        for l, z in ((l0, z0), (l1, z0), (l1, z1), (l0, z1)):
            verts.append(along(i, ds, l, z))
    for k in range(len(ss) - 1):
        a, b = 4 * k, 4 * (k + 1)
        for q in range(4):
            faces.append((a + q, b + q, b + (q + 1) % 4, a + (q + 1) % 4))
    faces.append((0, 3, 2, 1))
    n = 4 * (len(ss) - 1)
    faces.append((n, n + 1, n + 2, n + 3))
    ob = mesh_obj(name, verts, faces, mat, coll=coll)
    me = ob.data
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return ob


def build_pit_building(coll):
    """Pit building from the OSM footprint (406 m vs the 402.1 m Guinness figure) along the straight, 22-52 m right of
    the centreline. Section (reconstructed from 2023-25 photos): 50 garages (8.0 m bays) under two glazed storeys with
    stepped terraces, purple LED soffits, a roof canopy cantilevered towards the track. Heights estimated."""
    s0, s1 = 5355.5 - LEN, 342.0      # footprint stations (from the OSM polygon), front at 22-25 m
    front, back = -23.0, -52.5
    objs = []
    objs.append(box_along('pit_building.garage_level', s0, s1, back, front - 0.3, -0.1, 6.0, MATS['white_clad'], coll))
    # garage openings: 50 bays, lit interiors, dark dividers
    verts, faces = [], []
    bay = (s1 - s0) / 50
    for g in range(50):
        a, b = s0 + g * bay + 0.45, s0 + (g + 1) * bay - 0.45
        for s_a, s_b in ((a, b),):
            i0, i1 = st_of(s_a), st_of(s_b)
            p0, p1 = along(i0, 0, front, 0.0), along(i1, 0, front, 0.0)
            base = len(verts)
            verts += [p0, p1, (p1[0], p1[1], p1[2] + 4.6), (p0[0], p0[1], p0[2] + 4.6)]
            faces.append((base, base + 1, base + 2, base + 3))
    objs.append(mesh_obj('pit_building.garage_doors', verts, faces, MATS['garage'], coll=coll))
    objs.append(box_along('pit_building.level1', s0, s1, back, front - 1.5, 6.0, 10.2, MATS['facade'], coll))
    objs.append(box_along('pit_building.terrace1', s0, s1, front - 1.5, front + 1.2, 6.0, 6.45, MATS['white_clad'], coll))
    objs.append(box_along('pit_building.led1', s0, s1, front - 1.2, front + 1.2, 5.85, 6.0, MATS['purple'], coll))
    objs.append(box_along('pit_building.level2', s0, s1, back, front - 4.5, 10.2, 14.4, MATS['facade'], coll))
    objs.append(box_along('pit_building.terrace2', s0, s1, front - 4.5, front - 1.5, 10.2, 10.6, MATS['white_clad'], coll))
    objs.append(box_along('pit_building.led2', s0, s1, front - 4.3, front - 1.6, 10.05, 10.2, MATS['purple'], coll))
    objs.append(box_along('pit_building.canopy', s0 - 2, s1 + 2, back + 2, front + 4.0, 16.2, 16.9, MATS['roof'], coll))
    objs.append(box_along('pit_building.led_canopy', s0 - 2, s1 + 2, front - 2.0, front + 4.0, 16.05, 16.2, MATS['purple'], coll))
    # canopy columns every 4 garages
    for g in range(0, 51, 4):
        s = s0 + g * bay
        i = st_of(s)
        x, y, z = along(i, 0, front + 3.2)
        objs.append(box_along(f'pit_building.column{g:02d}', s - 0.3, s + 0.3, front + 2.9, front + 3.5, 6.4, 16.2, MATS['white_clad'], coll, step=1))
    # paddock-end block (north extension in the OSM footprint, stations 132-146, to 115 m): race control (estimated)
    objs.append(box_along('pit_building.north_block', 132, 146, -114.7, -52.5, 0, 22, MATS['facade'], coll, step=2))
    return objs


def build_grandstand(coll):
    """Main grandstand from the OSM footprint (417 m long, 28-43 m left of the centreline): raked seating with crowd,
    white cantilever roof (section and height reconstructed from photos)."""
    s0, s1 = 5357.5 - LEN, 354.0
    objs = []
    rows = 22
    verts, faces, uvs = [], [], []
    ss = list(np.arange(s0, s1, 6.0)) + [s1]
    for k, s in enumerate(ss):
        i = st_of(s)
        for r in range(rows + 1):
            l = 27.7 + r * (15.3 / rows)
            h = 1.2 + r * (11.5 / rows)
            for step in (0, 1):
                verts.append(along(i, 0, l + step * (15.3 / rows) * 0.05, h + (0 if step == 0 else 0)))
                uvs.append((s / 8.0, (r + step * 0.5) / 5.0))
    k2 = (rows + 1) * 2
    for k in range(len(ss) - 1):
        for j in range(k2 - 1):
            a = k * k2 + j
            faces.append((a, a + 1, a + k2 + 1, a + k2))
    objs.append(mesh_obj('grandstand.seating', verts, faces, MATS['crowd'], uvs, coll=coll))
    objs.append(box_along('grandstand.back', s0, s1, 43.0, 44.0, 0, 15.5, MATS['white_clad'], coll))
    objs.append(box_along('grandstand.front_wall', s0, s1, 27.2, 27.7, 0, 1.4, MATS['concrete'], coll))
    objs.append(box_along('grandstand.roof', s0, s1, 22.0, 45.0, 19.2, 19.8, MATS['roof'], coll))
    for k, s in enumerate(np.arange(s0, s1 + 1, 24)):
        objs.append(box_along(f'grandstand.mast{k:02d}', s - 0.35, s + 0.35, 43.3, 44.0, 0, 19.2, MATS['metal'], coll, step=1))
    # temporary stand towards T1 (OSM bleachers 1567982803, 227 m, ~38 m left)
    objs.append(box_along('stand_t1.seating', 370, 590, 26.0, 50.0, 0, 9.0, MATS['crowd'], coll))
    return objs


def build_gantry(coll):
    """Start gantry over the start line (position from the measured grid; design generic, no branding)."""
    i = st_of(LM['start_line'])
    objs = []
    for side, l in (('L', EL[i] + 3.0), ('R', -ER[i] - 1.5)):
        objs.append(box_along(f'gantry.post{side}', LM['start_line'] - 0.4, LM['start_line'] + 0.4, l - 0.4, l + 0.4, 0, 8.8, MATS['dark_metal'], coll, step=1))
    objs.append(box_along('gantry.beam', LM['start_line'] - 0.7, LM['start_line'] + 0.7, -ER[i] - 1.9, EL[i] + 3.4, 7.2, 8.8, MATS['boards'], coll, step=1))
    objs.append(box_along('gantry.lights', LM['start_line'] - 0.75, LM['start_line'] - 0.68, -2.5, 2.5, 7.4, 8.0, MATS['dark_metal'], coll, step=1))
    return objs


def build_hill(coll):
    """Lusail Hill (spectator mound at Turn 1, from the 2023 venue news). Size and position estimated: outside T1,
    beyond the run-off, ~8 m high, 160 m long, turf with crowd on the face."""
    c = next(c for c in CORNERS if c['n'] == 1)
    i = st_of(c['station'])
    verts, faces, uvs = [], [], []
    ss = np.arange(c['station'] - 120, c['station'] + 60, 6.0)
    prof = [(32, 0.0), (40, 3.0), (48, 6.5), (58, 8.0), (70, 6.0), (84, 0.0)]
    for s in ss:
        k = st_of(s)
        fade = min(1, (s - ss[0]) / 30, (ss[-1] - s) / 30)
        for l, h in prof:
            verts.append(along(k, 0, l, h * max(0.15, fade) - 0.3))
            uvs.append((s / 6.0, l / 6.0))
    m = len(prof)
    for a in range(len(ss) - 1):
        for j in range(m - 1):
            q = a * m + j
            faces.append((q, q + m, q + m + 1, q + 1))
    return [mesh_obj('lusail_hill', verts, faces, MATS['turf'], uvs, coll=coll)]


def build_ground(coll):
    """Ground: sand everywhere (desert venue) on a grid following the circuit height, artificial turf polygons from
    OSM landuse=grass (measured footprints), lowered a few centimetres under the run-off."""
    xs = np.arange(C[:, 0].min() - 500, C[:, 0].max() + 500, 16.0)
    ys = np.arange(C[:, 1].min() - 500, C[:, 1].max() + 500, 16.0)
    sub = np.arange(0, N_ST, 4)
    verts, uvs = [], []
    for y in ys:
        for x in xs:
            d2 = (C[sub, 0] - x) ** 2 + (C[sub, 1] - y) ** 2
            j = int(np.argmin(d2))
            near = math.sqrt(d2[j])
            z = float(Z[sub[j]]) - 0.12 - min(1.5, max(0.0, near - 30) / 200)
            verts.append((float(x), float(y), z))
            uvs.append((x / 12.0, y / 12.0))
    nx = len(xs)
    faces = []
    for r in range(len(ys) - 1):
        for c in range(nx - 1):
            a = r * nx + c
            faces.append((a, a + 1, a + nx + 1, a + nx))
    objs = [mesh_obj('ground.sand', verts, faces, MATS['sand'], uvs, coll=coll)]
    # turf polygons
    for k, f in enumerate(D['features']['grass']):
        ring = np.array(f['pts']) - ORIGIN
        if len(ring) < 4:
            continue
        bm = bmesh.new()
        vs = []
        for x, y in ring[:-1] if np.allclose(ring[0], ring[-1]) else ring:
            z, _ = ground_z(x, y)
            vs.append(bm.verts.new((float(x), float(y), z - 0.06)))
        try:
            bm.faces.new(vs)
        except ValueError:
            bm.free()
            continue
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='EAR_CLIP')
        me = bpy.data.meshes.new(f'turf.{k:03d}')
        bm.to_mesh(me)
        bm.free()
        uv = me.uv_layers.new(name='UVMap')
        uv.data.foreach_set('uv', [c for li in me.loops for c in (me.vertices[li.vertex_index].co.x / 8.0, me.vertices[li.vertex_index].co.y / 8.0)])
        ob = bpy.data.objects.new(f'turf.{k:03d}', me)
        ob.data.materials.append(MATS['turf'])
        coll.objects.link(ob)
        objs.append(ob)
    return objs


def build_buildings(coll):
    """Other OSM buildings within 450 m: plain white prisms, 8-12 m (heights not in OSM: estimated)."""
    objs = []
    skip = {'152483597', '152483596'}
    for f in D['features']['buildings']:
        if f['id'] in skip:
            continue
        ring = np.array(f['pts']) - ORIGIN
        z, _ = ground_z(*ring.mean(0))
        h = float(f.get('height') or 0) or (4.0 * float(f.get('levels') or 0)) or (5.0 if f.get('kind') == 'carport' else 10.0)
        ob = extrude(f'building.{f["id"]}', ring, z - 0.2, h, MATS['white_clad'], coll)
        if ob:
            objs.append(ob)
    for f in D['features']['bleachers']:
        if f['id'] == '1567982803':
            continue
        ring = np.array(f['pts']) - ORIGIN
        z, _ = ground_z(*ring.mean(0))
        ob = extrude(f'bleachers.{f["id"]}', ring, z - 0.2, 7.0, MATS['crowd'], coll)
        if ob:
            objs.append(ob)
    return objs


def brake_boards(km):
    """100/200/300 m boards before the heavy braking zones (T1, T6, T10; positions reconstructed), outside the turn."""
    out = []
    for n in (1, 6, 10):
        c = next(c for c in CORNERS if c['n'] == n)
        outside = 1 if c['dir'] == 'R' else -1
        apex = c['station']
        brake = apex - (190 if n == 1 else 120)
        for k, m in enumerate((300, 200, 100)):
            s = brake - m + 100
            i = st_of(s)
            e = EL[i] if outside > 0 else ER[i]
            x, y, z = P(i, outside * (e + 2.8))
            out.append([round(x, 2), round(y, 2), round(z, 2), round(math.atan2(T[i, 1], T[i, 0]), 4), 3 - k])
    return out


def build_prototypes(coll):
    """Instanced in the browser: floodlight pole + head (5 x 2 lamps facing the track), brake board."""
    objs = []
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.32, radius2=0.18, depth=22.0,
                          matrix=__import__('mathutils').Matrix.Translation((0, 0, 11.0)))
    me = bpy.data.meshes.new('proto_pole')
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('proto_pole', me)
    ob.data.materials.append(MATS['metal'])
    coll.objects.link(ob)
    objs.append(ob)
    # head: frame + lamps, facing +X (rotated to face the track per instance)
    verts, faces = [], []

    def cube(cx, cy, cz, sx, sy, sz):
        b = len(verts)
        for dx in (-sx, sx):
            for dy in (-sy, sy):
                for dz in (-sz, sz):
                    verts.append((cx + dx, cy + dy, cz + dz))
        for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
            faces.append(tuple(b + i for i in q))
    cube(0.0, 0.0, 21.9, 0.25, 2.1, 0.9)
    ob = mesh_obj('proto_light_frame', verts, faces, MATS['dark_metal'], coll=coll)
    objs.append(ob)
    verts, faces = [], []
    for r in range(2):
        for k in range(5):
            cube(0.27, -1.6 + k * 0.8, 21.45 + r * 0.9, 0.03, 0.33, 0.33)
    objs.append(mesh_obj('proto_light_lamps', verts, faces, MATS['lamp'], coll=coll))
    verts, faces = [], []
    cube(0.0, 0.0, 1.6, 0.06, 0.9, 1.3)
    objs.append(mesh_obj('proto_brake_board', verts, faces, MATS['board_face'], coll=coll))
    verts, faces = [], []
    cube(0.0, 0.0, 2.35, 0.04, 0.04, 1.3)
    objs.append(mesh_obj('proto_fence_post', verts, faces, MATS['dark_metal'], coll=coll))
    for o in objs:
        o['instanced'] = True
    return objs


def empties(coll):
    def add(name, i, lat=0.0):
        e = bpy.data.objects.new(name, None)
        e.location = P(i, lat)
        e.empty_display_size = 3
        e.rotation_euler = (0, 0, math.atan2(T[wrap(i), 1], T[wrap(i), 0]))
        coll.objects.link(e)
    add('mark.control_line', st_of(0))
    add('mark.start_line', st_of(LM['start_line']))
    for c in CORNERS:
        add(f'mark.T{c["n"]:02d}', st_of(c['station']))
    for k, v in LM['approx'].items():
        if isinstance(v, (int, float)):
            add(f'mark.{k}', st_of(v))


def main():
    reset()
    mats()
    track = collection('track')
    venue = collection('venue')
    protos = collection('prototypes')
    marks = collection('marks')
    km = kerb_mask()
    pitlat = pit_lateral()
    build_road(track)
    build_kerbs(track, km)
    _, widths = build_runoff(track, km, pitlat)
    build_lines(track, km)
    _, inst = build_barriers(track, km, widths, pitlat)
    _, pit_pts = build_pit(track, pitlat)
    build_pit_building(venue)
    build_grandstand(venue)
    build_gantry(venue)
    build_hill(venue)
    build_ground(venue)
    build_buildings(venue)
    build_prototypes(protos)
    empties(marks)
    inst['boards'] = brake_boards(km)
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    GLB.parent.mkdir(parents=True, exist_ok=True)
    kw = dict(filepath=str(GLB), export_format='GLB', export_yup=True, export_apply=True, export_extras=True,
              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
              export_draco_position_quantization=16, export_draco_texcoord_quantization=12, export_draco_color_quantization=8,
              export_image_format='WEBP', export_image_quality=82, export_materials='EXPORT', export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(export_vertex_color='ACTIVE', **kw)
    except TypeError:
        bpy.ops.export_scene.gltf(**kw)
    sub = slice(None, None, 2)
    manifest = dict(
        version=1, venue='lusail', name='Lusail International Circuit', match=['qatar', 'lusail', 'losail'],
        glb='lusail.glb', origin=ORIGIN, frame=D['frame'], z_offset=D['z_offset'],
        length=LEN, step=STEP * 2,
        centre=dict(x=np.round(C[sub, 0], 2).tolist(), y=np.round(C[sub, 1], 2).tolist(), z=np.round(Z[sub], 3).tolist()),
        edges=dict(left=np.round(EL[sub], 2).tolist(), right=np.round(ER[sub], 2).tolist()),
        chunk_stations=CHUNK, chunk_m=CHUNK * STEP,
        landmarks=dict(control_line=0.0, start_line=LM['start_line'], corners=[dict(n=c['n'], station=c['station'], dir=c['dir']) for c in CORNERS],
                       approx=LM['approx']),
        instances=inst,
        pit=dict(x=[round(p[0], 2) for p in pit_pts], y=[round(p[1], 2) for p in pit_pts], z=[round(p[2], 3) for p in pit_pts]),
        sources=dict(D['sources'], landmarks=LM['sources'], grid_note=LM.get('grid_note')),
        fit=D['fit'],
        provenance=dict(
            measured=['centreline and asphalt edges (OSM polygon, 5419.5 m vs FIA 5419 m)', 'pit lane path (OSM)',
                      'pit building and main grandstand footprints (OSM)', 'turf areas (OSM)', 'elevation (OpenF1, 20 cars, 925 laps)',
                      'rubbered line position (OpenF1 median driven line)', 'grid slot stations, start line (OpenF1 parked cars)',
                      'corner apexes and directions (OSM curvature + FIA map)'],
            reconstructed=['kerb extents per corner and red/white pattern', 'run-off depth, maroon paint, blue/white bands',
                           'wall + debris fence line and height', 'floodlight pole spacing (42 m), height (22 m), lamp heads',
                           'pit building section, storey heights, LED soffits, canopy', 'grandstand rake, roof height',
                           'Lusail Hill size/position', 'brake board positions', 'grid stagger side', 'other building heights'],
            flat_assumptions=['no crossfall/camber on the asphalt', 'kerb profile 4.7 cm generic']))
    MANIFEST.write_text(json.dumps(manifest), encoding='utf-8')
    print(f'GLB {GLB.stat().st_size / 1e6:.2f} MB, manifest {MANIFEST.stat().st_size / 1e3:.0f} KB, blend {BLEND.stat().st_size / 1e6:.2f} MB')
    print('objects', len(bpy.data.objects), 'poles', len(inst['poles']))


main()
