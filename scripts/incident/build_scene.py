"""Blender: build the Turn 4 reconstruction scene, animate it and render the 3D frames.

Run through scripts/incident/make_video.py, or directly:
  blender --background --factory-startup --python-exit-code 1 --python scripts/incident/build_scene.py -- \
      --config scripts/incident/mexico2026_t4.json [--preview] [--frames 1,40,200] [--save-blend] [--no-render]

Writes <work>/frames/#####.png and <work>/frames.json (per-frame data time, shot, and where each car
and the track limits land on screen) for the overlay pass. Only mesh data is taken from car.blend;
nothing in it is executed.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).absolute().parents[2]
HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE))
import scenery  # noqa: E402
from scenery import hexrgb, simple, make_mesh  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


CFG = json.loads(Path(arg('--config', HERE / 'mexico2026_t4.json')).read_text(encoding='utf-8'))
WORK = ROOT / CFG['data_dir'] / 'work'
P = json.loads((WORK / 'prepared.json').read_text(encoding='utf-8'))
PREVIEW = '--preview' in argv
R = CFG['render']
W, H = R['size']
FPS = R['fps']
if PREVIEW:
    W, H, FPS = W // 2, H // 2, max(15, FPS // 2)
ENGINE = arg('--engine', R.get('engine', 'BLENDER_EEVEE_NEXT'))
STEP = P['step']
NCAR = list(CFG['drivers'])

# ---------------------------------------------------------------- render settings
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = ENGINE
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Punchy'
scene.render.use_motion_blur = not PREVIEW
scene.render.motion_blur_shutter = 0.5
if ENGINE == 'CYCLES':
    scene.cycles.samples = 24 if PREVIEW else R.get('samples', 64)
    scene.cycles.use_denoising = True
else:
    ee = scene.eevee
    ee.taa_render_samples = 12 if PREVIEW else R.get('samples', 48)
    for key, value in (('use_shadows', True), ('shadow_ray_count', 2), ('shadow_step_count', 8), ('use_raytracing', not PREVIEW),
                       ('use_fast_gi', True), ('fast_gi_method', 'GLOBAL_ILLUMINATION'), ('use_volumetric_shadows', False)):
        try:
            setattr(ee, key, value)
        except (AttributeError, TypeError):
            pass
    try:
        ee.ray_tracing_options.resolution_scale = '2'
    except Exception:
        pass

# Sky and sun: clear early afternoon at 2,240 m (race started 14:03 local).
world = bpy.data.worlds.new('Mexico afternoon')
scene.world = world
world.use_nodes = True
nt = world.node_tree
sky = nt.nodes.new('ShaderNodeTexSky')
sky.sky_type = 'NISHITA'
sky.sun_elevation = math.radians(50)
sky.sun_rotation = math.radians(215)
sky.altitude = 2240
sky.air_density = 1.0
sky.dust_density = 3.0
sky.sun_disc = False
nt.links.new(sky.outputs['Color'], nt.nodes['Background'].inputs['Color'])
nt.nodes['Background'].inputs['Strength'].default_value = 0.42
sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN'))
scene.collection.objects.link(sun)
sun.data.energy = 5.2
sun.data.angle = math.radians(1.2)
sun.data.color = (1.0, 0.94, 0.86)
sun.rotation_euler = (math.radians(40), 0, math.radians(215 + 90))

TRACK, MATS = scenery.build(P, CFG)
L = TRACK.L
HW = TRACK.hw


def frame_at(ss):
    return TRACK.frame(np.atleast_1d(ss))


# ---------------------------------------------------------------- cars
CAR = ROOT / 'assets' / '3d' / 'cars' / 'qvist' / 'car.blend'
LIV = CFG['livery']
FONT = bpy.data.fonts.load(str(HERE / 'fonts' / 'BigShoulders-900.ttf'))
cars = {}
for num in NCAR:
    d = CFG['drivers'][num]
    with bpy.data.libraries.load(str(CAR), link=False) as (src, dst):
        dst.objects = list(src.objects)
    root = bpy.data.objects.new(f'Car {num} {d["code"]}', None)
    scene.collection.objects.link(root)
    body = simple(f'{num} body', LIV['body'], rough=.2, metal=.3, coat=1.)
    carbon = simple(f'{num} carbon', LIV['carbon'], rough=.32, coat=.6)
    accent = simple(f'{num} accent', LIV['accent'], rough=.25, coat=.8)
    helmet = simple(f'{num} helmet', d['helmet'], rough=.2, coat=1.)
    tire = simple(f'{num} tyre', '#0D0D0F', rough=.8)
    rim = simple(f'{num} rim', '#1A1C1F', rough=.25, metal=.9)
    wheels, livery = [], None
    for ob in dst.objects:
        if ob is None or ob.type != 'MESH':
            continue
        scene.collection.objects.link(ob)
        ob.data = ob.data.copy()
        ob.parent = root
        if 'Wheel' in ob.name:
            vs = np.empty(len(ob.data.vertices) * 3)
            ob.data.vertices.foreach_get('co', vs)
            vs = vs.reshape(-1, 3)
            c = (vs.min(0) + vs.max(0)) / 2
            ob.data.transform(Matrix.Translation(-Vector(c)))
            ob.location = c
            ob.data.materials.clear()
            ob.data.materials.append(tire)
            ob.data.materials.append(rim)
            for poly in ob.data.polygons:
                poly.material_index = int(np.linalg.norm(np.array(poly.center)[1:]) < .22)
            wheels.append(ob)
        else:
            for slot, m in enumerate((body, carbon, accent, helmet)):
                if slot < len(ob.data.materials):
                    ob.data.materials[slot] = m
            if ob.name.startswith('Livery'):
                livery = ob
    vs = [v.co.copy() for v in livery.data.vertices]
    bvh = BVHTree.FromPolygons(vs, [tuple(p.vertices) for p in livery.data.polygons])

    def surface(x, y):
        hit = bvh.ray_cast(Vector((x, y, 3)), Vector((0, 0, -1)), 10)
        return hit[0].z if hit[0] else None

    for y_pos, size in ((-2.05, .30), (.95, .36)):
        z_top = surface(0, y_pos)
        if z_top is None:
            continue
        cu = bpy.data.curves.new(f'{num} number', 'FONT')
        cu.body = num
        cu.font = FONT
        cu.size = size
        cu.align_x = 'CENTER'
        cu.align_y = 'CENTER'
        cu.extrude = .002
        tx = bpy.data.objects.new(f'{num} number', cu)
        scene.collection.objects.link(tx)
        tx.parent = root
        tx.location = (0, y_pos, z_top + .012)
        tx.rotation_euler = (0, 0, math.pi)  # reads correctly from behind and above
        cu.materials.append(simple(f'{num} number', LIV['number'], rough=.35))
    zs = np.array([v.z for v in vs])
    ys = np.array([v.y for v in vs])
    top = int(np.argmax(np.where((ys > -.4) & (ys < .7), zs, -9)))
    pts, faces, _ = scenery.box('tcam', (0, 0), 0, 0, (.17, .30, .07), None)
    pod = make_mesh(f'{num} T-cam', pts, faces, mats=[simple(f'{num} tcam', d['tcam'], rough=.3, coat=.8)], smooth=False)
    pod.parent = root
    pod.location = (0, vs[top].y + .02, vs[top].z + .005)
    cars[num] = dict(root=root, wheels=wheels)


def sample(num, t):
    c = P['cars'][num]
    f = min(max(t / STEP, 0), len(c['x']) - 2)
    i = int(f)
    a = f - i
    g = lambda k: c[k][i] * (1 - a) + c[k][i + 1] * a
    return dict(x=g('x'), y=g('y'), z=g('z'), yaw=g('yaw'), s=g('s'), speed=g('speed'))


# ---------------------------------------------------------------- trails painted on the track
# One ribbon per car along its whole path; a per-frame "now" value reveals the last few seconds.
trail_now, trail_win = {}, {}
for num in NCAR:
    col = CFG['drivers'][num]['trail']
    ts = np.arange(0, 46, .04)
    pts = [sample(num, t) for t in ts]
    verts, uv, faces = [], [], []
    for k, (t, q) in enumerate(zip(ts, pts)):
        nx, ny = math.sin(q['yaw']), -math.cos(q['yaw'])
        for side in (-1, 1):
            verts.append((q['x'] + nx * side * .1, q['y'] + ny * side * .1, q['z'] + .035))
            uv.append((t, side))
        if k:
            faces.append((2 * k - 2, 2 * k, 2 * k + 1, 2 * k - 1))
    g = scenery.Nodes(f'Trail {num}')
    tex = g.n('ShaderNodeUVMap', uv_map='uv')
    sep = g.n('ShaderNodeSeparateXYZ')
    g.link(tex.outputs['UV'], sep.inputs[0])
    now = g.n('ShaderNodeValue', label='now')
    win = g.n('ShaderNodeValue', label='window')
    age = g.math('SUBTRACT', now.outputs[0], sep.outputs['X'])               # seconds ago
    visible = g.math('MULTIPLY', g.math('GREATER_THAN', age, -.001), g.math('LESS_THAN', age, win.outputs[0]))
    fade = g.math('SUBTRACT', 1, g.math('DIVIDE', age, g.math('MAXIMUM', win.outputs[0], .01)), clamp=True)
    alpha = g.math('MULTIPLY', visible, g.math('POWER', fade, .6))
    emit = g.n('ShaderNodeEmission', Strength=2.6)
    emit.inputs['Color'].default_value = (*hexrgb(col), 1)
    transp = g.n('ShaderNodeBsdfTransparent')
    mix = g.n('ShaderNodeMixShader')
    g.link(alpha, mix.inputs[0])
    g.link(transp.outputs[0], mix.inputs[1])
    g.link(emit.outputs[0], mix.inputs[2])
    g.link(mix.outputs[0], g.t.nodes['Material Output'].inputs['Surface'])
    g.m.surface_render_method = 'BLENDED'
    make_mesh(f'Trail {num}', verts, faces, mats=[g.m], uvs={'uv': uv}, smooth=False)
    trail_now[num], trail_win[num] = now.outputs[0], win.outputs[0]


# ---------------------------------------------------------------- timeline
frames = []  # (shot index, data time, shot progress 0..1)
for si, shot in enumerate(CFG['shots']):
    t0, t1 = shot['t']
    if shot.get('hold'):
        n = int(round(shot['hold'] * FPS))
        frames += [(si, t0, k / max(n - 1, 1)) for k in range(n)]
    else:
        n = int(round((t1 - t0) / shot['speed'] * FPS))
        frames += [(si, t0 + k * shot['speed'] / FPS, k / max(n - 1, 1)) for k in range(n)]
scene.frame_start, scene.frame_end = 1, len(frames)
print('FRAMES', len(frames), 'at', FPS, 'fps =', round(len(frames) / FPS, 1), 's', flush=True)

WHEEL_R = .36
for f, (si, t, u) in enumerate(frames, start=1):
    shot = CFG['shots'][si]
    for num, car in cars.items():
        q, qp, qn = sample(num, t), sample(num, t - .1), sample(num, t + .1)
        root = car['root']
        yaw_rate = (qn['yaw'] - qp['yaw']) / .2
        v = q['speed'] / 3.6
        accel = (qn['speed'] - qp['speed']) / 3.6 / .2
        pitch = max(-.018, min(.018, -accel * .0016))      # nose dives under braking
        roll = max(-.03, min(.03, -v * yaw_rate * .0016))   # body leans to the outside
        root.location = (q['x'], q['y'], q['z'])
        root.rotation_euler = (pitch, roll, q['yaw'] + math.pi / 2)
        root.keyframe_insert('location', frame=f)
        root.keyframe_insert('rotation_euler', frame=f)
        steer = max(-.35, min(.35, math.atan(3.6 * yaw_rate / max(v, .5))))
        for w in car['wheels']:
            w.rotation_euler = (-(q['s'] / WHEEL_R), 0, steer if w.name[0] == 'F' else 0)
            w.keyframe_insert('rotation_euler', frame=f)
        trail_now[num].default_value = t
        trail_now[num].keyframe_insert('default_value', frame=f)
        trail_win[num].default_value = float(shot.get('trail', 0))
        trail_win[num].keyframe_insert('default_value', frame=f)


# ---------------------------------------------------------------- cameras
def look_matrix(pos, target, up_hint, prev=None):
    """Camera rotation with view direction pos->target and up as close as possible to up_hint."""
    fwd = np.asarray(target, float) - np.asarray(pos, float)
    fwd /= np.linalg.norm(fwd)
    up = np.asarray(up_hint, float) - np.dot(up_hint, fwd) * fwd
    if np.linalg.norm(up) < 1e-6:
        up = np.array([0, 0, 1.0]) - fwd[2] * fwd
    up /= np.linalg.norm(up)
    right = np.cross(fwd, up)
    m = Matrix(((right[0], up[0], -fwd[0]), (right[1], up[1], -fwd[1]), (right[2], up[2], -fwd[2])))
    return m.to_euler('XYZ', prev) if prev is not None else m.to_euler()


cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
scene.collection.objects.link(cam)
cam.data.sensor_width = 36
cam.data.clip_start = .3
cam.data.clip_end = 6000
top = bpy.data.objects.new('Top camera', bpy.data.cameras.new('Top camera'))
scene.collection.objects.link(top)
top.data.type = 'ORTHO'
top.data.clip_end = 6000

# Top view frames the Turn 4-5 complex, rotated so the cars run up the screen.
S, CENTRE = TRACK.S, TRACK.C
zone = (S > 1770) & (S < 1960)
zc = CENTRE[zone]
mid = (zc.min(0) + zc.max(0)) / 2
entry, exit_ = CENTRE[np.argmin(np.abs(S - 1770))], CENTRE[np.argmin(np.abs(S - 1960))]
ang = math.atan2(*(exit_ - entry)[::-1])
top.location = (mid[0], mid[1], 300)
top.rotation_euler = (0, 0, ang - math.pi / 2)  # screen-up = travel direction
th = -(ang - math.pi / 2)
ext = (zc - mid) @ np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]]).T
vis_w = max(np.ptp(ext[:, 0]) * 1.45, np.ptp(ext[:, 1]) * 1.2 * W / H)
top.data.ortho_scale = vis_w * max(W, H) / W

poses = []
prev_up = None
for f, (si, t, u) in enumerate(frames, start=1):
    shot = CFG['shots'][si]
    kind = shot['camera']
    a, b = sample(NCAR[0], t), sample(NCAR[1], t)
    tgt = np.array([(a['x'] + b['x']) / 2, (a['y'] + b['y']) / 2, (a['z'] + b['z']) / 2 + .6])
    pair = tgt.copy()
    hd = float(np.arctan2(*frame_at((a['s'] + b['s']) / 2)[1][0][::-1]))
    if shot.get('follow'):
        fo = sample(shot['follow'], t)
        tgt = np.array([fo['x'], fo['y'], fo['z'] + .6])
        hd = fo['yaw']
    fwd = np.array([math.cos(hd), math.sin(hd), 0])
    right = np.array([fwd[1], -fwd[0], 0])
    up = np.array([0, 0, 1.0])
    lens = shot.get('lens', 35)
    look, up_hint = tgt.copy(), up
    if kind in ('heli', 'chase'):
        back = shot.get('back', 20) + shot.get('pull_back', 0) * u
        pos = tgt - fwd * back + right * shot.get('side', 0) + up * shot.get('height', 3)
        look = tgt + fwd * (6 if kind == 'chase' else 0)
        if shot.get('follow'):
            look = (tgt + fwd * 8) * .5 + pair * .5
    elif kind == 'drone':
        # High tracking shot looking (almost) straight down, cars driving up the screen.
        h = shot.get('height', 28) + (shot.get('height_end', shot.get('height', 28)) - shot.get('height', 28)) * u
        tilt = math.radians(shot.get('tilt', 15))
        lead = fwd * shot.get('lead', 4)
        look = pair + lead
        pos = look - fwd * h * math.tan(tilt) + right * shot.get('side', 0) + up * h
        up_hint = fwd
    elif kind == 'trackside':
        p, t_, n_, z_ = frame_at(shot['anchor_s'])
        pos = np.array([*(p[0] + n_[0] * shot['anchor_side']), z_[0] + shot.get('height', 6)])
    elif kind in ('orbit',):
        fo = sample(shot.get('focus', '16'), t)
        tgt = np.array([(fo['x'] + a['x'] + b['x']) / 3, (fo['y'] + a['y'] + b['y']) / 3, fo['z'] + .5])
        look = tgt
        a0, a1 = shot.get('orbit_deg', [0, 0])
        ang_o = hd + math.radians(a0 + (a1 - a0) * (u * u * (3 - 2 * u)))
        pos = tgt + np.array([math.cos(ang_o), math.sin(ang_o), 0]) * shot.get('radius', 40) + up * shot.get('height', 20)
    else:  # top (orthographic, fixed)
        pos = None
    poses.append([si, kind, pos, look, lens, np.asarray(up_hint, float)])

# Smooth each shot's camera path (never across a cut): position, target and up.
sid = np.array([p[0] for p in poses])
for key in (2, 3, 5):
    arr = np.array([p[key] if p[key] is not None else np.zeros(3) for p in poses], float)
    for si in set(sid):
        m = np.where(sid == si)[0]
        k = max(1, int(.35 * FPS))
        pad = np.pad(arr[m], ((k, k), (0, 0)), mode='edge')
        ker = np.hanning(2 * k + 3)[1:-1]
        ker /= ker.sum()
        arr[m] = np.column_stack([np.convolve(pad[:, i], ker, mode='valid') for i in range(3)])
    for p, v in zip(poses, arr):
        if p[key] is not None:
            p[key] = v

last = None
prev_rot = None
for f, (si, kind, pos, look, lens, up_hint) in enumerate(poses, start=1):
    active = top if kind == 'top' else cam
    if active is not last:
        scene.timeline_markers.new(f'shot{si}', frame=f).camera = active
        last = active
    if kind != 'top':
        cam.location = Vector(pos)
        prev_rot = look_matrix(pos, look, up_hint, prev_rot)  # Euler kept continuous: no spins between frames
        cam.rotation_euler = prev_rot
        cam.data.lens = lens
        cam.keyframe_insert('location', frame=f)
        cam.keyframe_insert('rotation_euler', frame=f)
        cam.data.keyframe_insert('lens', frame=f)
scene.camera = cam

cam.data.dof.use_dof = not PREVIEW
cam.data.dof.aperture_fstop = 5.6
focus_empty = bpy.data.objects.new('Focus', None)
scene.collection.objects.link(focus_empty)
cam.data.dof.focus_object = focus_empty
for f, p in enumerate(poses, start=1):
    focus_empty.location = Vector(p[3])
    focus_empty.keyframe_insert('location', frame=f)


# ---------------------------------------------------------------- per-frame screen data
def project(camobj, xyz):
    co = world_to_camera_view(scene, camobj, Vector(xyz))
    return [round(co.x * W, 1), round((1 - co.y) * H, 1), round(co.z, 2)]


edge_zone = np.arange(1760, 1965, 2.0)
ep, et, en, ez = frame_at(edge_zone)
edges = {'left': [(*(ep[i] - en[i] * HW), ez[i] + .05) for i in range(len(edge_zone))],
         'right': [(*(ep[i] + en[i] * HW), ez[i] + .05) for i in range(len(edge_zone))]}
meta = dict(fps=FPS, size=[W, H], preview=PREVIEW, facts=P['facts'], frames=[])
wanted = sorted({int(x) for x in arg('--frames').split(',') if 0 < int(x) <= len(frames)}) if arg('--frames') else None
for f, (si, t, u) in enumerate(frames, start=1):
    if wanted and f not in wanted:
        continue
    scene.frame_set(f)
    shot = CFG['shots'][si]
    camobj = top if shot['camera'] == 'top' else cam
    scene.camera = camobj
    entry_ = dict(frame=f, shot=shot['id'], t=round(t, 3), u=round(u, 4), cars={})
    for num in NCAR:
        q = sample(num, t)
        c = P['cars'][num]
        i = min(int(t / STEP), len(c['speed']) - 1)
        entry_['cars'][num] = dict(screen=project(camobj, (q['x'], q['y'], q['z'] + 1.25)), speed=c['speed'][i], gear=c['gear'][i],
                                   throttle=c['throttle'][i], brake=c['brake'][i], s=round(q['s'] % L, 1))
    if shot.get('limits'):
        entry_['limits'] = {k: [project(camobj, v)[:2] for v in pts] for k, pts in edges.items()}
    meta['frames'].append(entry_)

out = WORK / ('frames_preview' if PREVIEW else 'frames')
out.mkdir(parents=True, exist_ok=True)
(WORK / ('frames_preview.json' if PREVIEW else 'frames.json')).write_text(json.dumps(meta), encoding='utf-8')
if '--save-blend' in argv:
    bpy.ops.wm.save_as_mainfile(filepath=str(WORK / 'mexico2026_t4.blend'))
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.compression = 15
if '--no-render' not in argv:
    for f in (wanted or range(1, len(frames) + 1)):
        scene.frame_set(f)
        scene.camera = top if CFG['shots'][frames[f - 1][0]]['camera'] == 'top' else cam
        scene.render.filepath = str(out / f'{f:05d}.png')
        bpy.ops.render.render(write_still=True)
        print('RENDERED', f, len(frames), flush=True)
print('DONE', flush=True)
