"""Procedural Mexico City circuit dressing for the incident scene (imported by build_scene.py).

Everything is generated: textures are shader nodes, no image files or brand logos. The layout is
the real lap line from timing data; widths, kerbs, run-offs and buildings are stylised.
"""
import math

import bpy
import numpy as np


# ------------------------------------------------------------------ helpers
def hexrgb(h):
    h = h.lstrip('#')
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4))


class Nodes:
    """Tiny helper to write shader graphs without a page of boilerplate per material."""

    def __init__(self, name):
        self.m = bpy.data.materials.new(name)
        self.m.use_nodes = True
        self.t = self.m.node_tree
        self.bsdf = self.t.nodes['Principled BSDF']

    def n(self, kind, **props):
        node = self.t.nodes.new(kind)
        for k, v in props.items():
            if hasattr(node, k):
                setattr(node, k, v)
            else:
                node.inputs[k].default_value = v
        return node

    def link(self, a, b):
        self.t.links.new(a, b)

    def math(self, op, a, b=None, clamp=False):
        node = self.n('ShaderNodeMath', operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                node.inputs[i].default_value = v
            else:
                self.link(v, node.inputs[i])
        return node.outputs[0]

    def ramp(self, fac, stops):
        node = self.n('ShaderNodeValToRGB')
        els = node.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position = pos
            el.color = (*hexrgb(col), 1) if isinstance(col, str) else col
        self.link(fac, node.inputs['Fac'])
        return node.outputs['Color']

    def noise(self, vec, scale, detail=4., rough=.5):
        node = self.n('ShaderNodeTexNoise', Scale=scale, Detail=detail, Roughness=rough)
        if vec is not None:
            self.link(vec, node.inputs['Vector'])
        return node.outputs['Fac']

    def uv(self, name):
        node = self.n('ShaderNodeUVMap', uv_map=name)
        sep = self.n('ShaderNodeSeparateXYZ')
        self.link(node.outputs['UV'], sep.inputs[0])
        return node.outputs['UV'], sep.outputs['X'], sep.outputs['Y']

    def mix_color(self, fac, a, b):
        node = self.n('ShaderNodeMix', data_type='RGBA', clamp_factor=True)
        self.link(fac, node.inputs[0]) if not isinstance(fac, (int, float)) else setattr(node.inputs[0], 'default_value', fac)
        for idx, col in ((6, a), (7, b)):
            if isinstance(col, str):
                node.inputs[idx].default_value = (*hexrgb(col), 1)
            else:
                self.link(col, node.inputs[idx])
        return node.outputs[2]

    def bump(self, height, strength=.2, distance=.01):
        node = self.n('ShaderNodeBump', Strength=strength, Distance=distance)
        self.link(height, node.inputs['Height'])
        self.link(node.outputs['Normal'], self.bsdf.inputs['Normal'])


def simple(name, col, rough=.5, metal=0., coat=0.):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*hexrgb(col), 1) if isinstance(col, str) else (*col, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if coat:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = .05
    return m


# ------------------------------------------------------------------ materials
def asphalt():
    g = Nodes('Asphalt')
    _, lat, s = g.uv('uv')
    rl_uv, rl, brake = g.uv('rl')
    obj = g.n('ShaderNodeTexCoord').outputs['Object']
    mott = g.noise(obj, .05, 4)
    base = g.ramp(mott, [(.3, '#2C2D30'), (.5, '#343538'), (.72, '#3E3F42')])
    mid = g.noise(obj, 1.3, 6, .6)
    base = g.mix_color(g.math('MULTIPLY', mid, .35), base, '#26272A')
    agg = g.noise(obj, 55, 2, .9)
    base = g.mix_color(g.math('MULTIPLY', g.math('GREATER_THAN', agg, .6), .45), base, '#4E4F52')
    fine = g.noise(obj, 9, 3, .7)
    base = g.mix_color(g.math('MULTIPLY', fine, .3), base, '#232427')
    # Patches: resurfaced rectangles along the lap, slightly different shade, with sealed seams.
    # Occasional thin sealed cracks (sparse, low contrast).
    vor = g.n('ShaderNodeTexVoronoi', feature='DISTANCE_TO_EDGE', Scale=.18)
    comb = g.n('ShaderNodeCombineXYZ')
    g.link(lat, comb.inputs['X'])
    g.link(g.math('MULTIPLY', s, .5), comb.inputs['Y'])
    g.link(comb.outputs[0], vor.inputs['Vector'])
    crack = g.math('MULTIPLY', g.math('LESS_THAN', vor.outputs['Distance'], .006), g.math('GREATER_THAN', g.noise(obj, .08, 2), .6))
    base = g.mix_color(g.math('MULTIPLY', crack, .45), base, '#1A1B1D')
    # Rubbered racing line: darker and a little shinier where the cars run.
    d = g.math('ABSOLUTE', rl)
    mapr = g.n('ShaderNodeMapRange', clamp=True)
    mapr.inputs['From Min'].default_value = .4
    mapr.inputs['From Max'].default_value = 2.8
    mapr.inputs['To Min'].default_value = .7
    mapr.inputs['To Max'].default_value = 0.
    g.link(d, mapr.inputs['Value'])
    base = g.mix_color(mapr.outputs['Result'], base, '#18191A')
    # Braking-zone tyre streaks: noise stretched along the lap, only near the line in braking zones.
    st = g.n('ShaderNodeCombineXYZ')
    g.link(g.math('MULTIPLY', rl, 3.2), st.inputs['X'])
    g.link(g.math('MULTIPLY', s, .06), st.inputs['Y'])
    streak = g.noise(st.outputs[0], 6, 2)
    streak = g.math('GREATER_THAN', streak, .58)
    streak = g.math('MULTIPLY', g.math('MULTIPLY', streak, brake), mapr.outputs['Result'])
    base = g.mix_color(g.math('MULTIPLY', streak, 1.4), base, '#141415')
    g.link(base, g.bsdf.inputs['Base Color'])
    rough = g.math('SUBTRACT', .86, g.math('MULTIPLY', mapr.outputs['Result'], .28))
    g.link(rough, g.bsdf.inputs['Roughness'])
    g.bump(agg, .18, .003)
    return g.m


def paint(name, col, wear=.25, rough=.55):
    g = Nodes(name)
    obj = g.n('ShaderNodeTexCoord').outputs['Object']
    n = g.noise(obj, 3.5, 6)
    worn = g.math('MULTIPLY', g.math('GREATER_THAN', n, .63), wear)
    g.link(g.mix_color(worn, col, '#3A3B3E'), g.bsdf.inputs['Base Color'])
    g.bsdf.inputs['Roughness'].default_value = rough
    g.bump(g.noise(obj, 180, 2), .08, .002)
    return g.m


def kerb():
    g = Nodes('Kerb')
    _, lat, s = g.uv('uv')
    stripe = g.math('GREATER_THAN', g.math('FRACT', g.math('MULTIPLY', s, 1 / 2.2)), .5)
    col = g.mix_color(stripe, '#C1121F', '#F1F1EE')
    obj = g.n('ShaderNodeTexCoord').outputs['Object']
    dirt = g.math('MULTIPLY', g.noise(obj, 1.6, 5), .35)
    col = g.mix_color(g.math('MULTIPLY', g.math('GREATER_THAN', dirt, .2), .5), col, '#2B2B2D')
    g.link(col, g.bsdf.inputs['Base Color'])
    g.bsdf.inputs['Roughness'].default_value = .5
    ridges = g.math('SINE', g.math('MULTIPLY', s, 2 * math.pi / .55))
    g.bump(ridges, .35, .01)
    return g.m


def grass():
    g = Nodes('Grass')
    obj = g.n('ShaderNodeTexCoord').outputs['Object']
    big = g.noise(obj, .012, 3)
    mid = g.noise(obj, .09, 5)
    fine = g.noise(obj, 4.0, 3)
    col = g.ramp(big, [(.3, '#4E6A2B'), (.55, '#5B7431'), (.75, '#76803F')])  # drier patches, November
    col = g.mix_color(g.math('MULTIPLY', mid, .45), col, '#3F5A24')
    sep = g.n('ShaderNodeSeparateXYZ')
    g.link(obj, sep.inputs[0])
    mow = g.math('GREATER_THAN', g.math('FRACT', g.math('MULTIPLY', g.math('ADD', sep.outputs['X'], g.math('MULTIPLY', sep.outputs['Y'], .6)), 1 / 14.)), .5)
    col = g.mix_color(g.math('MULTIPLY', mow, .12), col, '#7E9147')
    col = g.mix_color(g.math('MULTIPLY', fine, .25), col, '#2E4219')
    g.link(col, g.bsdf.inputs['Base Color'])
    g.bsdf.inputs['Roughness'].default_value = .93
    g.bump(fine, .4, .02)
    return g.m


def foliage(seed):
    g = Nodes(f'Foliage {seed}')
    obj = g.n('ShaderNodeTexCoord').outputs['Object']
    n = g.noise(obj, 1.2, 6)
    tones = [('#2F4A1E', '#4C6A2A'), ('#3A5524', '#5E7A33'), ('#2B4320', '#3F6129'), ('#46582A', '#6C7C3A')][seed % 4]
    g.link(g.ramp(n, [(.35, tones[0]), (.7, tones[1])]), g.bsdf.inputs['Base Color'])
    g.bsdf.inputs['Roughness'].default_value = .85
    g.bump(g.noise(obj, 6, 3), .6, .15)
    return g.m


def wire_mesh():
    """Catch fence: mostly see-through, casts a light shadow."""
    g = Nodes('Catch fence')
    g.bsdf.inputs['Base Color'].default_value = (*hexrgb('#8A8E92'), 1)
    g.bsdf.inputs['Metallic'].default_value = .8
    g.bsdf.inputs['Alpha'].default_value = .22
    g.m.surface_render_method = 'DITHERED'
    return g.m


def car_paint(col):
    m = simple('Car paint', col, rough=.22, metal=.25, coat=1.)
    return m


# ------------------------------------------------------------------ geometry
def make_mesh(name, verts, faces, mats=(), face_mats=None, uvs=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(map(int, f)) for f in faces])
    me.update()
    for m in mats:
        me.materials.append(m)
    if face_mats is not None and len(me.polygons):
        me.polygons.foreach_set('material_index', np.asarray(face_mats, dtype=np.int32))
    if uvs:
        loops = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get('vertex_index', loops)
        for layer, per_vertex in uvs.items():
            uv = me.uv_layers.new(name=layer)
            uv.data.foreach_set('uv', np.asarray(per_vertex, dtype=np.float32)[loops].ravel())
    if smooth:
        me.polygons.foreach_set('use_smooth', np.ones(len(me.polygons), dtype=bool))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def box(name, xy, z0, yaw, size, material, scene=None):
    sx, sy, sz = size
    c, s = math.cos(yaw), math.sin(yaw)
    pts = []
    for z in (0, sz):
        for (x, y) in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)):
            pts.append((xy[0] + x * c - y * s, xy[1] + x * s + y * c, z0 + z))
    f = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return pts, f, material


class Batch:
    """Collects many boxes into one mesh per material (thousands of objects would be slow)."""

    def __init__(self):
        self.parts = {}

    def add(self, pts, faces, material):
        v, f = self.parts.setdefault(material.name, ([], [], material))[:2]
        base = len(v)
        v.extend(pts)
        f.extend([tuple(i + base for i in face) for face in faces])

    def build(self, prefix):
        for name, (v, f, m) in self.parts.items():
            if f:
                make_mesh(f'{prefix} {name}', v, f, mats=[m], smooth=False)


class Track:
    """Lap-distance frame along the stylised track centre."""

    def __init__(self, P):
        tr = P['track']
        self.L = tr['length']
        self.hw = tr['half_width']
        self.S = np.array(tr['s'])
        self.C = np.array(tr['centre'])
        self.LINE = np.array(tr['line'])
        self.Z = np.array(tr['z'])
        self.curv = np.array(tr['curv'])
        self.kerbs = {k: np.array(v, float) for k, v in tr['kerbs'].items()}

    def frame(self, ss):
        ss = np.mod(np.asarray(ss, float), self.L)
        p = np.column_stack([np.interp(ss, self.S, self.C[:, i], period=self.L) for i in (0, 1)])
        q = np.column_stack([np.interp(ss + 1, self.S, self.C[:, i], period=self.L) for i in (0, 1)])
        t = q - p
        t /= np.linalg.norm(t, axis=1, keepdims=True)
        n = np.column_stack([t[:, 1], -t[:, 0]])
        return p, t, n, np.interp(ss, self.S, self.Z, period=self.L)

    def line_offset(self, ss):
        """Racing line position relative to the centre (+ right), metres."""
        p, t, n, _ = self.frame(ss)
        ss = np.mod(ss, self.L)
        lp = np.column_stack([np.interp(ss, self.S, self.LINE[:, i], period=self.L) for i in (0, 1)])
        return np.einsum('ij,ij->i', lp - p, n)

    def mask(self, key, ss):
        return np.interp(np.mod(ss, self.L), self.S, self.kerbs[key], period=self.L) > .5

    def clear_of_track(self, xy, ss, margin):
        """True where a point is at least `margin` from any other part of the track."""
        dec = self.C[::3]
        decs = self.S[::3]
        out = np.ones(len(xy), bool)
        for i, (q, s0) in enumerate(zip(xy, ss)):
            d = np.linalg.norm(dec - q, axis=1)
            far = np.abs(((decs - s0 + self.L / 2) % self.L) - self.L / 2) > 60
            out[i] = not np.any(d[far] < margin)
        return out


def band(track, name, a, b, ss, dz, material, mask=None, lift_outer=0.):
    """Strip between lateral offsets a..b (from centre, + right) with UVs: uv=(lateral, s), rl=(to racing line, brake)."""
    p, t, n, z = track.frame(ss)
    lo = track.line_offset(ss)
    brake = braking_zones(track, ss)
    verts, uv, rl, faces = [], [], [], []
    for i in range(len(ss)):
        for off in (a, b):
            q = p[i] + n[i] * off
            lift = lift_outer * (abs(off) - min(abs(a), abs(b))) / max(abs(b - a), 1e-6)
            verts.append((q[0], q[1], z[i] + dz + lift))
            uv.append((off, ss[i]))
            rl.append((off - lo[i], brake[i]))
    N = len(ss)
    closed = (track.L - ss[-1] + ss[0]) < 1.6 * (ss[1] - ss[0])  # full lap: join the last slice to the first
    for i in range(N if closed else N - 1):
        k = (i + 1) % N
        if mask is not None and not (mask[i] and mask[k]):
            continue
        faces.append((2 * i, 2 * k, 2 * k + 1, 2 * i + 1))
    return make_mesh(name, verts, faces, mats=[material], uvs={'uv': uv, 'rl': rl})


def braking_zones(track, ss):
    """1.0 in the ~120 m before tight corners (where the tyre streaks are)."""
    tight = np.abs(track.curv) > .018
    out = np.zeros(len(ss))
    s_tight = track.S[tight]
    for i, s0 in enumerate(np.mod(ss, track.L)):
        ahead = (s_tight - s0) % track.L
        if len(ahead) and ahead.min() < 130:
            out[i] = 1 - ahead.min() / 130
    return out


# ------------------------------------------------------------------ build
def build(P, cfg, rng_seed=11):
    track = Track(P)
    hw = track.hw
    L = track.L
    ss = np.arange(0, L, 1.0)
    M = dict(asphalt=asphalt(), line=paint('Edge line', '#F2F2EE', .18), kerb=kerb(), grass=grass(),
             green=paint('Run-off green', '#1F7A4D', .35, .62), runoff=paint('Run-off asphalt', '#3B3D41', .1, .8),
             red=paint('Run-off red', '#C8102E', .3), white=paint('Run-off white', '#EDEDEA', .3),
             concrete=simple('Concrete', '#B9B6AE', .85), fence=simple('Fence', '#5E6266', .4, .7), mesh=wire_mesh(),
             tyres=simple('Tecpro', '#1C4E9A', .6), tyres2=simple('Tecpro red', '#C8102E', .6),
             stand=simple('Grandstand', '#9DA1A6', .7), seats=simple('Seats', '#E7E7E2', .7), seats2=simple('Seats blue', '#1D4F91', .6),
             roof=simple('Roof', '#E9EBEE', .35, .4), glass=simple('Glass', '#2C3E50', .08, .6), pit=simple('Pit building', '#D9DCE0', .5),
             board=simple('Boards', '#0E6E5C', .5), board2=simple('Boards white', '#F4F4F2', .5),
             city=simple('City haze', '#A8B6C6', .95), city2=simple('City haze dark', '#8A9AAD', .95), trunk=simple('Trunk', '#4B3A2B', .9))

    band(track, 'Asphalt', -hw, hw, ss, 0., M['asphalt'])
    band(track, 'Edge line L', -hw, -hw + .2, ss, .004, M['line'])
    band(track, 'Edge line R', hw - .2, hw, ss, .004, M['line'])
    corners = {}
    for side, keys in ((-1, ('left', 'left_out')), (1, ('right', 'right_out'))):
        m = track.mask(keys[0], ss) | track.mask(keys[1], ss)
        # widen kerb zones a little and add a green painted strip outside them (modern run-off look)
        m = np.convolve(m.astype(float), np.ones(9), 'same') > 0
        a, b = (-hw - 1.2, -hw) if side < 0 else (hw, hw + 1.2)
        band(track, f'Kerb {side}', a, b, ss, .0, M['kerb'], mask=m, lift_outer=.05)
        gm = np.convolve(m.astype(float), np.ones(61), 'same') > 0
        a2, b2 = (-hw - 4.2, -hw - 1.2) if side < 0 else (hw + 1.2, hw + 4.2)
        band(track, f'Green strip {side}', a2, b2, ss, -.01, M['green'], mask=gm)
        corners[side] = gm
    # Tarmac run-offs on the outside of the big stops (T1 and T4), painted in national colours.
    for s0, s1, side, width in ((930, 1010, -1, 22), (1790, 1850, 1, 18), (2000, 2050, -1, 16)):
        sub = np.arange(s0, s1, 1.0)
        a, b = (-hw - 4.2 - width, -hw - 4.2) if side < 0 else (hw + 4.2, hw + 4.2 + width)
        band(track, f'Run-off {s0}', a, b, sub, -.012, M['runoff'])
        third = width / 3
        for k, key in enumerate(('green', 'white', 'red')):
            aa = (-hw - 4.2 - third * (k + 1)) if side < 0 else (hw + 4.2 + third * k)
            sub2 = np.arange(s0 + 8, s0 + 26, 1.0)
            band(track, f'Run-off stripe {s0} {k}', aa, aa + third * .9, sub2, -.008, M[key])

    # Start line and grid.
    pole = float(P['cars'][cfg['lap_reference']]['s'][0])
    line_s = pole + 7.5
    for k in range(16):
        for row in range(2):
            p, t, n, z = track.frame([line_s + (row - .5) * .55])
            w = 2 * hw / 16
            q = p[0] + n[0] * (-hw + (k + .5) * w)
            pts = [q + t[0] * dx + n[0] * dy for dx, dy in ((-.27, -w / 2), (.27, -w / 2), (.27, w / 2), (-.27, w / 2))]
            make_mesh('Chequer', [(c[0], c[1], z[0] + .006) for c in pts], [(0, 1, 2, 3)],
                      mats=[M['white'] if (k + row) % 2 else simple('Black paint', '#0C0C0D', .6)], smooth=False)
    for slot in range(10):
        gs = line_s - 7.5 - slot * 8
        p, t, n, z = track.frame([gs])
        q = p[0] + n[0] * (-3.4 if slot % 2 == 0 else 3.4)
        for dx, dy, lx, ly in ((0, 0, .12, 2.6), (-.9, -1.3, 1.8, .12), (-.9, 1.3, 1.8, .12)):
            c0 = q + t[0] * dx + n[0] * dy
            pts = [c0 + t[0] * ax + n[0] * ay for ax, ay in ((-lx / 2, -ly / 2), (lx / 2, -ly / 2), (lx / 2, ly / 2), (-lx / 2, ly / 2))]
            make_mesh('Grid box', [(c[0], c[1], z[0] + .006) for c in pts], [(0, 1, 2, 3)], mats=[M['line']], smooth=False)

    # Terrain following the track height.
    xmin, ymin = track.C.min(0) - 340
    xmax, ymax = track.C.max(0) + 340
    gx, gy = np.arange(xmin, xmax, 8.), np.arange(ymin, ymax, 8.)
    GX, GY = np.meshgrid(gx, gy)
    pts = np.column_stack([GX.ravel(), GY.ravel()])
    dec, dz = track.C[::4], track.Z[::4]
    nearest = np.empty(len(pts), int)
    for i0 in range(0, len(pts), 3000):
        nearest[i0:i0 + 3000] = np.linalg.norm(pts[i0:i0 + 3000, None] - dec[None], axis=2).argmin(1)
    gz = dz[nearest] - .06
    nx, ny = len(gx), len(gy)
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    make_mesh('Terrain', np.column_stack([pts, gz]), faces, mats=[M['grass']])

    batch = Batch()
    rng = np.random.default_rng(rng_seed)

    # Barriers: concrete wall + catch fence wherever there is room (never across another part of the track).
    for side in (-1, 1):
        d = hw + 4.2 + np.where(np.abs(track.curv[np.searchsorted(track.S, ss) % len(track.S)]) > .012, 24, 9)
        d = np.convolve(d, np.ones(41) / 41, 'same')
        p, t, n, z = track.frame(ss)
        q = p + n * (side * d)[:, None]
        ok = track.clear_of_track(q, ss, 14)
        ok &= ~((ss > 1700) & (ss < 2100))  # keep the Turn 4-6 complex open (it is all run-off and grass)
        # drop short isolated pieces: walls only where at least 40 m in a row are clear
        run = np.convolve(ok.astype(float), np.ones(41), 'same') > 40.5
        ok = np.convolve(run.astype(float), np.ones(41), 'same') > .5
        ok &= track.clear_of_track(q, ss, 14)
        for i in range(0, len(ss) - 4, 4):
            if not (ok[i] and ok[i + 4]):
                continue
            yaw = math.atan2(t[i][1], t[i][0])
            mid = (q[i] + q[i + 4]) / 2
            batch.add(*box('wall', mid, z[i] - .05, yaw, (4.05, .5, 1.0), M['concrete']))
            batch.add(*box('post', mid, z[i] + .95, yaw, (.12, .12, 3.2), M['fence']))
            batch.add(*box('mesh', mid, z[i] + 1.0, yaw, (4.05, .03, 2.9), M['mesh']))
            if abs(track.curv[int(ss[i]) % len(track.curv)]) > .015:
                batch.add(*box('tecpro', mid - n[i] * side * .8, z[i], yaw, (4.0, .9, 1.0), M['tyres'] if (i // 4) % 2 else M['tyres2']))
            elif (i // 4) % 3 == 0:
                batch.add(*box('board', mid - n[i] * side * .3, z[i] + .2, yaw, (4.0, .08, .9), M['board'] if (i // 12) % 2 else M['board2']))

    # Pit building and pit wall on the inside of the main straight; grandstands opposite and at Turn 1.
    p, t, n, z = track.frame(np.arange(-300, 380, 10.))
    for i in range(len(p)):
        yaw = math.atan2(t[i][1], t[i][0])
        batch.add(*box('pitwall', p[i] + n[i] * (hw + 2.2), z[i], yaw, (10.05, .6, 1.3), M['concrete']))
        batch.add(*box('pitbox', p[i] + n[i] * (hw + 34), z[i], yaw, (10.05, 16, 9), M['pit']))
        batch.add(*box('pitglass', p[i] + n[i] * (hw + 25.9), z[i] + 3.5, yaw, (9.2, .2, 4.5), M['glass']))
        batch.add(*box('pitroof', p[i] + n[i] * (hw + 32), z[i] + 9, yaw, (10.05, 22, .6), M['roof']))

    def stand(s_from, s_to, side, dist, tiers, seats):
        p, t, n, z = track.frame(np.arange(s_from, s_to, 10.))
        for i in range(len(p)):
            yaw = math.atan2(t[i][1], t[i][0])
            for k in range(tiers):
                batch.add(*box('stand', p[i] + n[i] * side * (dist + k * 1.5), z[i] + k * .9, yaw, (10.05, 1.5, .9), M[seats] if k % 3 else M['stand']))
            batch.add(*box('back', p[i] + n[i] * side * (dist + tiers * 1.5 + .5), z[i], yaw, (10.05, 1.0, tiers * .9 + 5), M['stand']))
            batch.add(*box('roof', p[i] + n[i] * side * (dist + tiers * .75), z[i] + tiers * .9 + 5, yaw, (10.05, tiers * 1.5 + 4, .4), M['roof']))

    stand(-280, 380, -1, hw + 16, 14, 'seats2')
    stand(880, 1020, -1, hw + 34, 18, 'seats')
    # Foro Sol: the stadium section is wrapped in tall stands.
    stand(3380, 3780, -1, hw + 22, 30, 'seats')
    stand(3420, 3720, 1, hw + 24, 26, 'seats2')

    # Trees (Magdalena Mixhuca park), kept off the track and run-offs.
    tree_meshes = []
    for k in range(6):
        verts, faces = [], []
        blobs = rng.integers(3, 6)
        for b in range(blobs):
            cx, cy, cz = rng.normal(0, 1.6), rng.normal(0, 1.6), 5.5 + rng.uniform(-1, 1.8)
            r = rng.uniform(2.4, 3.6)
            bm_v, bm_f = icosphere(2)
            base = len(verts)
            jitter = 1 + rng.normal(0, .08, len(bm_v))
            verts.extend([(cx + v[0] * r * j, cy + v[1] * r * j, cz + v[2] * r * .85 * j) for v, j in zip(bm_v, jitter)])
            faces.extend([tuple(i + base for i in f) for f in bm_f])
        base = len(verts)
        tv, tf, _ = box('trunk', (0, 0), 0, 0, (.5, .5, 5), M['trunk'])
        verts.extend(tv)
        faces.extend([tuple(i + base for i in f) for f in tf])
        me = bpy.data.meshes.new(f'Tree {k}')
        me.from_pydata(verts, [], faces)
        me.materials.append(foliage(k))
        me.materials.append(M['trunk'])
        me.polygons.foreach_set('material_index', np.r_[np.zeros(len(faces) - 6, np.int32), np.ones(6, np.int32)])
        me.polygons.foreach_set('use_smooth', np.ones(len(faces), bool))
        tree_meshes.append(me)
    coll = bpy.context.scene.collection
    placed = 0
    tries = 0
    while placed < 1400 and tries < 40000:
        tries += 1
        q = np.array([rng.uniform(xmin + 20, xmax - 20), rng.uniform(ymin + 20, ymax - 20)])
        dd = np.linalg.norm(dec - q, axis=1)
        if dd.min() < 38:
            continue
        # clumps: prefer spots near other trees
        ob = bpy.data.objects.new('Tree', tree_meshes[int(rng.integers(0, 6))])
        coll.objects.link(ob)
        sc = rng.uniform(.75, 1.45)
        ob.location = (q[0], q[1], dz[dd.argmin()] - .1)
        ob.rotation_euler = (0, 0, rng.uniform(0, 6.3))
        ob.scale = (sc, sc, sc * rng.uniform(.85, 1.2))
        placed += 1

    # Mexico City on the horizon (hazy, far away).
    cx, cy = track.C.mean(0)
    for k in range(260):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(1300, 2600)
        h = rng.gamma(2.0, 14) + 8
        batch.add(*box('city', (cx + r * math.cos(a), cy + r * math.sin(a)), -2, a, (rng.uniform(25, 70), rng.uniform(25, 70), h),
                       M['city'] if k % 3 else M['city2']))
    batch.build('Scenery')
    return track, M


def icosphere(subdiv):
    t = (1 + 5 ** .5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    v = [tuple(np.array(p) / np.linalg.norm(p)) for p in v]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
         (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(subdiv):
        cache, nf = {}, []

        def mid(a, b):
            key = tuple(sorted((a, b)))
            if key not in cache:
                m = (np.array(v[a]) + np.array(v[b])) / 2
                v.append(tuple(m / np.linalg.norm(m)))
                cache[key] = len(v) - 1
            return cache[key]
        for a, b, c in f:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    return v, f
