"""Measured time sculpture and editorial beats; never changes lap outcomes.

Height is signed elapsed-time advantage, NOT circuit elevation. Geometry is
sampled from the same world-space driving route supplied to Blender.
"""
import numpy as np

INTRO_SECONDS = 3.2


def limit_timeline(timeline):
    """Add an animated establishing sequence without skipping any lap action."""
    result = dict(timeline)
    count = round(INTRO_SECONDS * timeline['fps'])
    for key in ('source_times', 'trail_times'):
        result[key] = [timeline[key][0]] * count + list(timeline[key])
    result['limit_intro_seconds'] = count / timeline['fps']
    result['output_seconds'] = len(result['source_times']) / timeline['fps']
    return result


class LimitStory:
    def __init__(self, comparison, path):
        self.progress = np.linspace(0, 1, 601)
        route = np.asarray(path['xy'], float)
        knots = np.asarray(path['progress'], float)
        if route.ndim != 2 or route.shape != (len(knots), 2) or not np.isfinite(route).all():
            raise ValueError('The Limit needs a finite world-space circuit route.')
        if len(knots) < 2 or not np.all(np.diff(knots) > 0):
            raise ValueError('The Limit needs strictly ordered route progress.')
        xy = np.column_stack([np.interp(self.progress, knots, route[:, i]) for i in (0, 1)])
        self.xy = (xy - (xy.min(0) + xy.max(0)) / 2) / max(np.ptp(xy, axis=0).max(), 1)
        self.delta = np.asarray([comparison.delta_at(p) for p in self.progress])
        if not np.isfinite(self.delta).all():
            raise ValueError('The Limit needs finite matched-distance timing.')
        self.limit = max(.05, float(np.abs(self.delta).max()))
        self.height = self.delta / self.limit * .30
        # Strongest measured swing over 6% of lap distance, not a claimed
        # physical cause or an invented corner label. Keep beats well spaced.
        window = 36
        swings = self.delta[window:] - self.delta[:-window]
        self.beats = []
        for index in np.argsort(-np.abs(swings)):
            lo, hi = self.progress[index], self.progress[index + window]
            if abs(swings[index]) < .005:
                break
            if any(abs((lo + hi) / 2 - b['progress']) < .16 for b in self.beats):
                continue
            self.beats.append(dict(start=float(lo), end=float(hi), progress=float((lo + hi) / 2),
                                   gain=float(abs(swings[index])), driver=0 if swings[index] > 0 else 1))
            if len(self.beats) == 3:
                break
        self.strongest = self.beats[0] if self.beats else None

    def project(self, yaw, growth=1., zoom=1., focus=None):
        """Single perspective projector for floor, curtain and time ridge."""
        c, s = np.cos(yaw), np.sin(yaw)
        x, y = self.xy.T
        xx, yy = c*x-s*y, s*x+c*y
        def projection(z):
            depth = yy * .62 - z * .78
            vertical = yy * .78 + z * .62
            factor = 2.7 / (2.7 + depth)
            return np.column_stack([xx * factor, -vertical * factor])
        base = projection(np.zeros(len(x)))
        ridge = projection(self.height * growth)
        origin = base[int(np.clip(focus, 0, 1) * 600)] if focus is not None else np.zeros(2)
        return (base-origin)*zoom, (ridge-origin)*zoom
