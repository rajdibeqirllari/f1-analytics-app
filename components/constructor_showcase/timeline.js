/* Pure, deterministic scroll math. Also exercised directly by Node tests. */
const ConstructorTimeline = (() => {
  const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));
  const smooth = value => { const t = clamp(value); return t * t * (3 - 2 * t); };
  function segmentLength(settings, viewportHeight) {
    return Math.max(1, viewportHeight * settings.scrollPerConstructorVh / 100);
  }
  function duration(count, settings, viewportHeight) {
    return count * segmentLength(settings, viewportHeight);
  }
  function wheelStep(distance, total, deltaY, deltaMode, viewportHeight) {
    const unit = deltaMode === 1 ? 16 : deltaMode === 2 ? viewportHeight : 1;
    return clamp(distance + deltaY * unit, 0, total);
  }
  function blend(from, to, progress) {
    const t = smooth(progress);
    const keys = ["opacity", "x", "y", "scale", "rotation"];
    return from.map((state, i) => Object.fromEntries(keys.map(key =>
      [key, state[key] + (to[i][key] - state[key]) * t])));
  }
  function sample(distance, count, settings, viewportHeight, reduced = false, compact = false) {
    const total = duration(count, settings, viewportHeight);
    const progress = clamp(distance / total);
    const phase = progress * count;
    const index = Math.min(count - 1, Math.floor(phase));
    const local = phase - index;
    const mix = smooth((local - settings.transitionStart) / (settings.transitionEnd - settings.transitionStart));
    const exit = index === count - 1 ? smooth((local - settings.finalExitStart) / (1 - settings.finalExitStart)) : 0;
    const movement = reduced ? 0 : compact ? 0.45 : 1;
    const states = Array.from({length: count}, () => ({opacity: 0, x: 0, y: 0, scale: 1, rotation: 0}));
    const outgoing = index === count - 1 ? exit * 0.5 : mix;
    states[index] = {
      // The last car never fades to an empty scanner. It stays present while
      // the user continues scrolling to the rest of the page.
      opacity: index === count - 1 ? 1 - (1 - settings.finalExitOpacity) * exit : 1 - mix,
      x: (-settings.transitionDistance * outgoing - Math.sin(local * Math.PI) * settings.settleDistance) * movement,
      y: settings.verticalDistance * outgoing * movement,
      scale: 1 - settings.scaleDrift * outgoing * movement,
      rotation: -settings.rotationDegrees * outgoing * movement,
    };
    if (index < count - 1) {
      states[index + 1] = {
        opacity: mix,
        x: settings.transitionDistance * (1 - mix) * movement,
        y: -settings.verticalDistance * (1 - mix) * movement,
        scale: 1 + settings.scaleDrift * (1 - mix) * movement,
        rotation: settings.rotationDegrees * (1 - mix) * movement,
      };
    }
    return {states, index: Math.min(count - 1, index + (mix >= 0.5 ? 1 : 0)), local, phase, exit,
      progress};
  }
  return {segmentLength, duration, wheelStep, blend, sample};
})();
if (typeof module !== "undefined") module.exports = ConstructorTimeline;
