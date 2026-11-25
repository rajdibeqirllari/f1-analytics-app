/** One owner for team-radio audio across the page: the Live commentary panel and the 3D broadcast's radio card both
 * go through here, so a clip plays at most once and never twice at the same time. */
let current: HTMLAudioElement | null = null;
let currentKey = '';
const played = new Map<string, number>();

const keyOf = (url: string) => { try { return decodeURIComponent(new URL(url, location.href).pathname.split('/').pop() || url); } catch { return url; } };

/** True (and marks it) if this clip has not been played in the last 10 minutes; false if someone already played it. */
export function claimRadio(url: string) {
  const k = keyOf(url), now = Date.now();
  for (const [x, t] of played) if (now - t > 600e3) played.delete(x);
  if (played.has(k)) return false;
  played.set(k, now);
  return true;
}

/** Plays a clip (stopping any other radio). Resolves when it ends or fails. */
export function playRadio(url: string): Promise<void> {
  stopRadio();
  const a = new Audio(url);
  current = a; currentKey = keyOf(url);
  return new Promise(res => {
    const done = () => { if (current === a) { current = null; currentKey = ''; } res(); };
    a.onended = done; a.onerror = done;
    a.play().catch(done);
  });
}
export function stopRadio() { if (current) { try { current.pause(); } catch { /* already stopped */ } } current = null; currentKey = ''; }
export function pauseRadio(on: boolean) { if (current) { if (on) current.pause(); else current.play().catch(() => {}); } }
export function radioPlaying(url?: string) { return !!current && (!url || keyOf(url) === currentKey); }
export function radioDuration() { return current && Number.isFinite(current.duration) ? current.duration : null; }
